import json
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.ml import read_model_evaluation
from app.api.portfolios import router as portfolios_router
from app.api.universes import read_universes
from app.main import app
from app.models import Holding
from app.schemas.recommendation import RecommendationRead
from app.services import universe as universe_module
from app.services.optimization import optimize_target_weights
from app.services.recommendation import size_allocation
from app.services.universe import list_universes

# --- OpenAPI / routing (no DB) -----------------------------------------------


def test_openapi_exposes_contract_endpoints():
    paths = app.openapi()["paths"]
    expected = {
        ("/universes", "get"),
        ("/ml/evaluation", "get"),
        ("/portfolios/overview", "get"),
        ("/portfolios/{portfolio_id}/recommendation", "post"),
        ("/portfolios/{portfolio_id}/recommendations", "get"),
        ("/portfolios/{portfolio_id}/recommendations/{recommendation_id}", "get"),
        ("/portfolios/{portfolio_id}/drift", "get"),
        ("/portfolios/{portfolio_id}/rebalance-proposals", "post"),
        ("/portfolios/{portfolio_id}/rebalance-proposals/{proposal_id}/execute", "post"),
        ("/stocks/{ticker}/analysis", "get"),
        ("/backtests", "post"),
    }
    assert expected <= {(p, m) for p, ops in paths.items() for m in ops}


def test_overview_route_is_matched_before_portfolio_id_route():
    get_paths = [r.path for r in portfolios_router.routes if "GET" in getattr(r, "methods", ())]
    assert get_paths.index("/portfolios/overview") < get_paths.index("/portfolios/{portfolio_id}")


def test_recommendation_read_optional_contract_fields_default_to_none():
    minimal = RecommendationRead(
        portfolio_id=uuid4(),
        universe="custom",
        universe_as_of=None,
        return_model="historical",
        capital=Decimal("0.00"),
        allocations=[],
        cash_weight=Decimal("1"),
        cash_amount=Decimal("0.00"),
        expected_portfolio_return=Decimal("0"),
        expected_portfolio_volatility=Decimal("0"),
        constraints={"max_position_weight": Decimal("0.1"), "target_volatility": Decimal("0.15")},
        excluded=[],
    )
    assert (minimal.id, minimal.created_at, minimal.model_version, minimal.forecast_as_of) == (
        None,
        None,
        None,
        None,
    )


def test_recommendation_allocation_requires_at_position_limit():
    schema = RecommendationRead.model_json_schema()
    assert "at_position_limit" in schema["$defs"]["RecommendedAllocationItem"]["required"]


# --- at_position_limit (pure) ------------------------------------------------


def test_size_allocation_flags_positions_at_the_limit():
    tickers = ["A", "B", "C"]
    returns = [Decimal("0.15"), Decimal("0.10"), Decimal("0.02")]
    cov = [
        [Decimal("0.04"), Decimal("0"), Decimal("0")],
        [Decimal("0"), Decimal("0.04"), Decimal("0")],
        [Decimal("0"), Decimal("0"), Decimal("0.04")],
    ]
    max_pos = Decimal("0.3")
    # Tight vol budget: A and B hit the cap first, C gets what is left.
    target = optimize_target_weights(tickers, returns, cov, max_pos, target_volatility=Decimal("0.09"))
    sized = size_allocation(target, returns, cov, Decimal("100000"), max_pos)

    flags = {a.ticker: a.at_position_limit for a in sized.allocations}
    weights = {a.ticker: a.target_weight for a in sized.allocations}
    for ticker, flag in flags.items():
        assert flag == (abs(weights[ticker] - max_pos) <= Decimal("0.0001"))
    assert flags["A"] is True
    assert any(flag is False for flag in flags.values())


# --- universes / ml evaluation (no DB) ---------------------------------------


def _write_universe(tmp_path, monkeypatch, tickers, as_of):
    (tmp_path / "nifty50.json").write_text(
        json.dumps({"name": "NIFTY50", "as_of": as_of, "source": "test", "tickers": tickers}),
        encoding="utf-8",
    )
    monkeypatch.setattr(universe_module, "DATA_DIR", tmp_path)


def test_list_universes_flags_unconfigured(tmp_path, monkeypatch):
    _write_universe(tmp_path, monkeypatch, [], None)
    assert [tuple(u) for u in list_universes()] == [("NIFTY50", None, [], False)]


def test_universes_route_lists_configured_universe(tmp_path, monkeypatch):
    _write_universe(tmp_path, monkeypatch, ["zztest_a", "ZZTEST_B"], "2026-01-01")
    [universe] = read_universes(user_id=uuid4())
    assert universe.name == "NIFTY50"
    assert universe.configured is True
    assert universe.tickers == ["ZZTEST_A", "ZZTEST_B"]
    assert str(universe.as_of) == "2026-01-01"


def test_ml_evaluation_route_returns_saved_report(monkeypatch):
    saved_report = {"source": "offline artifact"}
    monkeypatch.setattr("app.api.ml.load_latest_evaluation_report", lambda: saved_report)

    assert read_model_evaluation(user_id=uuid4()) is saved_report


@pytest.mark.db
def test_portfolio_routes_hide_other_users_portfolio(db_session, test_portfolio):
    from app.api.portfolios import (
        add_portfolio_capital,
        read_own_portfolio,
        read_portfolio_recommendations,
    )
    from app.schemas.portfolio import PortfolioCapitalAddRequest

    _, portfolio = test_portfolio
    stranger = uuid4()

    with pytest.raises(HTTPException) as read_error:
        read_own_portfolio(portfolio_id=portfolio.id, user_id=stranger, db=db_session)
    assert read_error.value.status_code == 404

    with pytest.raises(HTTPException) as history_error:
        read_portfolio_recommendations(portfolio_id=portfolio.id, user_id=stranger, db=db_session)
    assert history_error.value.status_code == 404

    with pytest.raises(HTTPException) as capital_error:
        add_portfolio_capital(
            portfolio_id=portfolio.id,
            data=PortfolioCapitalAddRequest(amount=Decimal("10")),
            user_id=stranger,
            db=db_session,
        )
    assert capital_error.value.status_code == 404
    assert db_session.get(Portfolio, portfolio.id).cash_balance == Decimal("50000")


# --- overview and saved recommendations (DB) ----------------------------------


@pytest.mark.db
def test_overview_summarizes_own_portfolios(db_session, test_portfolio):
    from app.api.portfolios import read_portfolios_overview

    user_id, portfolio = test_portfolio
    holding = Holding(
        portfolio_id=portfolio.id, ticker="ZZTEST_A", quantity=Decimal("1"), average_cost=Decimal("1")
    )
    db_session.add(holding)
    db_session.commit()

    overview = read_portfolios_overview(user_id=user_id, db=db_session)

    [item] = overview.portfolios
    assert item.id == portfolio.id
    assert item.name == portfolio.name
    assert item.risk_category == "moderate"
    assert item.initial_capital == portfolio.initial_capital
    assert item.cash_balance == portfolio.cash_balance
    assert item.holdings_count == 1
    assert item.valuation_status == "unavailable"
    assert (item.market_value, item.total_value, item.unrealized_pnl, item.unrealized_pnl_pct) == (
        None,
        None,
        None,
        None,
    )
    assert item.latest_recommendation is None
    assert overview.totals.portfolio_count == 1
    assert overview.totals.initial_capital == portfolio.initial_capital
    assert overview.totals.cash_balance == portfolio.cash_balance

    db_session.delete(holding)
    db_session.commit()


@pytest.mark.db
def test_overview_excludes_other_users_portfolios(db_session, test_portfolio):
    from app.api.portfolios import read_portfolios_overview

    overview = read_portfolios_overview(user_id=uuid4(), db=db_session)
    assert overview.portfolios == []
    assert overview.totals.portfolio_count == 0
    assert overview.totals.cash_balance == Decimal("0")


@pytest.mark.db
def test_saved_recommendations_list_is_empty_for_owner(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_recommendations

    user_id, portfolio = test_portfolio
    assert read_portfolio_recommendations(portfolio_id=portfolio.id, user_id=user_id, db=db_session) == []


@pytest.mark.db
def test_saved_recommendation_detail_is_404_for_owner(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_recommendation

    user_id, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        read_portfolio_recommendation(
            portfolio_id=portfolio.id, recommendation_id=uuid4(), user_id=user_id, db=db_session
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Recommendation not found"


@pytest.mark.db
def test_saved_recommendations_other_users_portfolio_is_404(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_recommendation, read_portfolio_recommendations

    _, portfolio = test_portfolio
    with pytest.raises(HTTPException) as list_exc:
        read_portfolio_recommendations(portfolio_id=portfolio.id, user_id=uuid4(), db=db_session)
    with pytest.raises(HTTPException) as detail_exc:
        read_portfolio_recommendation(
            portfolio_id=portfolio.id, recommendation_id=uuid4(), user_id=uuid4(), db=db_session
        )
    assert list_exc.value.status_code == 404
    assert detail_exc.value.detail == "Portfolio not found"


def test_recommendation_response_exposes_every_field_the_frontend_needs():
    schema = RecommendationRead.model_json_schema()
    top_level = set(schema["properties"])
    assert {
        "capital",
        "allocations",
        "cash_weight",
        "cash_amount",
        "expected_portfolio_return",
        "expected_portfolio_volatility",
        "return_model",
        "model_version",
        "forecast_as_of",
        "excluded",
        "constraints",
        "universe",
        "universe_as_of",
    } <= top_level
    allocation = schema["$defs"]["RecommendedAllocationItem"]
    assert set(allocation["required"]) == {
        "ticker",
        "expected_return",
        "target_weight",
        "amount",
        "at_position_limit",
        "source",
    }
    assert allocation["properties"]["source"]["enum"] == ["historical", "ml"]


def test_recommendation_request_accepts_both_return_models():
    from app.schemas.recommendation import RecommendationRequest

    schema = RecommendationRequest.model_json_schema()
    assert schema["properties"]["return_model"]["enum"] == ["historical", "ml"]
    assert schema["properties"]["return_model"]["default"] == "historical"
