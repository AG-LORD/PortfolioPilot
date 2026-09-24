import json
import math
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import numpy as np
import pytest
from price_fakes import make_series
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Holding, Portfolio, Transaction
from app.schemas.recommendation import RecommendationRequest
from app.services import universe as universe_module
from app.services.expected_returns import (
    MIN_HISTORY_OBSERVATIONS,
    InsufficientHistoryError,
    _estimate_from_price_series,
    get_expected_returns_and_covariance,
    get_expected_returns_for_universe,
)
from app.services.market_data import MarketDataUnavailableError
from app.services.optimization import optimize_target_weights
from app.services.recommendation import size_allocation
from app.services.universe import UniverseError, get_universe, normalize_tickers

# Placeholder tickers for tests only — NOT the real NIFTY 50 constituents.
PLACEHOLDER_UNIVERSE = ["ZZTEST_A", "ZZTEST_B", "ZZTEST_C", "ZZTEST_D", "ZZTEST_E"]


def _good_universe_series():
    return {t: make_series(seed=i) for i, t in enumerate(PLACEHOLDER_UNIVERSE)}


def _write_universe_file(tmp_path, monkeypatch, tickers, as_of="2026-09-01"):
    (tmp_path / "nifty50.json").write_text(
        json.dumps({"name": "NIFTY50", "as_of": as_of, "source": "test placeholder", "tickers": tickers}),
        encoding="utf-8",
    )
    monkeypatch.setattr(universe_module, "DATA_DIR", tmp_path)


# --- universe loading / normalization ---------------------------------------


def test_normalize_tickers_uppercases_strips_and_dedupes():
    assert normalize_tickers([" reliance ", "TCS", "tcs", "infy.ns", "INFY"]) == [
        "RELIANCE",
        "TCS",
        "INFY",
    ]


def test_normalize_tickers_rejects_empty():
    with pytest.raises(UniverseError):
        normalize_tickers([])
    with pytest.raises(UniverseError):
        normalize_tickers(["", "   "])


def test_normalize_tickers_rejects_too_many():
    with pytest.raises(UniverseError):
        normalize_tickers([f"T{i}" for i in range(universe_module.MAX_CUSTOM_TICKERS + 1)])


def test_get_universe_loads_and_normalizes(tmp_path, monkeypatch):
    _write_universe_file(tmp_path, monkeypatch, [" aaa", "BBB", "bbb"])
    name, as_of, tickers = get_universe("nifty50")
    assert name == "NIFTY50"
    assert as_of == date(2026, 9, 1)
    assert tickers == ["AAA", "BBB"]


def test_get_universe_unknown_raises():
    with pytest.raises(UniverseError):
        get_universe("SENSEX_NOT_CONFIGURED")


def test_get_universe_unconfigured_raises(tmp_path, monkeypatch):
    _write_universe_file(tmp_path, monkeypatch, [], as_of=None)
    with pytest.raises(UniverseError):
        get_universe("NIFTY50")


# --- eligibility filtering (through the price cache) --------------------------


@pytest.mark.db
def test_universe_returns_excludes_missing_and_short_history(db_session, fake_market):
    fake_market.series = {
        "ZZTEST_A": make_series(1),
        "ZZTEST_B": make_series(2),
        "ZZTEST_SHORT": make_series(3, n_days=10),
    }

    result = get_expected_returns_for_universe(
        db_session, ["ZZTEST_A", "ZZTEST_MISSING", "ZZTEST_B", "ZZTEST_SHORT"]
    )

    assert result.inputs.tickers == ["ZZTEST_A", "ZZTEST_B"]
    assert len(result.inputs.expected_returns) == 2
    assert len(result.inputs.covariance) == 2
    reasons = {e.ticker: e.reason for e in result.excluded}
    assert reasons == {
        "ZZTEST_MISSING": "no historical data returned",
        "ZZTEST_SHORT": "only 10 trading day(s) of history; at least 31 are needed",
    }


@pytest.mark.db
def test_universe_returns_batch_failure_excludes_with_request_failed_reason(db_session, fake_market):
    fake_market.fail = MarketDataUnavailableError("ZZTEST_A, ZZTEST_B", "history request failed: boom")
    with pytest.raises(InsufficientHistoryError):
        get_expected_returns_for_universe(db_session, ["ZZTEST_A", "ZZTEST_B"])


@pytest.mark.db
def test_universe_returns_all_ineligible_raises(db_session, fake_market):
    fake_market.series = {"ZZTEST_SHORT": make_series(1, n_days=5)}
    with pytest.raises(InsufficientHistoryError):
        get_expected_returns_for_universe(db_session, ["ZZTEST_MISSING", "ZZTEST_SHORT"])


@pytest.mark.db
def test_universe_returns_insufficient_common_dates_raises(db_session, fake_market):
    # Each ticker alone has enough history, but their overlap is too short.
    n = MIN_HISTORY_OBSERVATIONS + 10
    end = date.today() - timedelta(days=2)
    fake_market.series = {
        "ZZTEST_A": make_series(1, n_days=n, end=end),
        "ZZTEST_B": make_series(2, n_days=n, end=end - timedelta(days=n - 15)),
    }
    with pytest.raises(InsufficientHistoryError):
        get_expected_returns_for_universe(db_session, ["ZZTEST_A", "ZZTEST_B"])


@pytest.mark.db
def test_expected_returns_identical_with_and_without_cache(db_session, fake_market):
    series = _good_universe_series()
    fake_market.series = series
    without_cache = _estimate_from_price_series(PLACEHOLDER_UNIVERSE, series)

    cold = get_expected_returns_for_universe(db_session, PLACEHOLDER_UNIVERSE)
    calls_after_cold = len(fake_market.calls)
    warm = get_expected_returns_for_universe(db_session, PLACEHOLDER_UNIVERSE)
    holdings_path = get_expected_returns_and_covariance(db_session, PLACEHOLDER_UNIVERSE)

    assert calls_after_cold == 1
    assert len(fake_market.calls) == 1
    assert cold.excluded == [] and warm.excluded == []
    assert cold.inputs == without_cache
    assert warm.inputs == without_cache
    assert holdings_path == without_cache


# --- sizing: amounts and portfolio metrics ------------------------------------


def _diag_cov(variances):
    n = len(variances)
    return [[variances[i] if i == j else Decimal("0") for j in range(n)] for i in range(n)]


def _sized_example(capital):
    tickers = ["A", "B", "C", "D"]
    returns = [Decimal("0.15"), Decimal("0.11"), Decimal("0.07"), Decimal("-0.05")]
    cov = _diag_cov([Decimal("0.04"), Decimal("0.03"), Decimal("0.02"), Decimal("0.05")])
    target = optimize_target_weights(
        tickers, returns, cov, max_position_weight=Decimal("0.3"), target_volatility=Decimal("0.15")
    )
    return target, returns, cov, size_allocation(target, returns, cov, capital)


def test_size_allocation_amounts_sum_exactly_to_capital():
    _, _, _, sized = _sized_example(Decimal("123456.78"))

    assert sized.capital == Decimal("123456.78")
    assert sum(a.amount for a in sized.allocations) + sized.cash_amount == sized.capital
    assert sized.cash_amount >= 0
    for a in sized.allocations:
        assert a.amount == a.amount.quantize(Decimal("0.01"))
        assert a.target_weight > 0
    assert sum(a.target_weight for a in sized.allocations) + sized.cash_weight == Decimal("1")
    # Negative-return D gets zero weight and is omitted.
    assert "D" not in {a.ticker for a in sized.allocations}


def test_size_allocation_rounds_sub_paisa_capital_down_to_two_decimals():
    _, _, _, sized = _sized_example(Decimal("123456.7891"))

    assert sized.capital == Decimal("123456.78")
    assert sized.capital.as_tuple().exponent == -2
    assert sized.cash_amount.as_tuple().exponent == -2
    assert sum(a.amount for a in sized.allocations) + sized.cash_amount == sized.capital


def test_size_allocation_metrics_match_numpy():
    target, returns, cov, sized = _sized_example(Decimal("100000"))
    w = np.array([float(a.target_weight) for a in target.allocations])
    mu = np.array([float(r) for r in returns])
    sigma = np.array([[float(v) for v in row] for row in cov])

    assert abs(float(sized.expected_portfolio_return) - float(w @ mu)) < 1e-6
    expected_vol = math.sqrt(float(w @ sigma @ w))
    assert abs(float(sized.expected_portfolio_volatility) - expected_vol) < 1e-6
    assert float(sized.expected_portfolio_volatility) <= 0.15 + 1e-3


# --- request validation --------------------------------------------------------


def test_request_requires_exactly_one_source():
    with pytest.raises(ValidationError):
        RecommendationRequest()
    with pytest.raises(ValidationError):
        RecommendationRequest(universe="NIFTY50", tickers=["AAA"])
    with pytest.raises(ValidationError):
        RecommendationRequest(universe="NIFTY50", return_model="ml")
    assert RecommendationRequest(tickers=["AAA"]).return_model == "historical"


# --- API route (DB-backed) --------------------------------------------------------


@pytest.mark.db
def test_recommendation_for_portfolio_without_holdings(db_session, test_portfolio, fake_market):
    from app.api.portfolios import create_portfolio_recommendation

    user_id, portfolio = test_portfolio
    assert db_session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count() == 0
    fake_market.series = _good_universe_series()

    response = create_portfolio_recommendation(
        portfolio_id=portfolio.id,
        data=RecommendationRequest(tickers=PLACEHOLDER_UNIVERSE + ["ZZTEST_MISSING"]),
        user_id=user_id,
        db=db_session,
    )

    max_pos = response.constraints.max_position_weight
    assert response.universe == "custom"
    assert response.universe_as_of is None
    assert response.return_model == "historical"
    assert response.capital == portfolio.cash_balance
    assert response.cash_amount.as_tuple().exponent == -2
    assert len(response.allocations) > 0
    for a in response.allocations:
        assert Decimal("0") < a.target_weight <= max_pos + Decimal("0.001")
    assert sum(a.target_weight for a in response.allocations) + response.cash_weight == Decimal("1")
    assert sum(a.amount for a in response.allocations) + response.cash_amount == response.capital
    assert response.expected_portfolio_volatility <= response.constraints.target_volatility + Decimal("0.001")
    assert [e.ticker for e in response.excluded] == ["ZZTEST_MISSING"]


@pytest.mark.db
def test_recommendation_route_named_universe(db_session, test_portfolio, fake_market, monkeypatch, tmp_path):
    from app.api.portfolios import create_portfolio_recommendation

    user_id, portfolio = test_portfolio
    _write_universe_file(tmp_path, monkeypatch, PLACEHOLDER_UNIVERSE)
    fake_market.series = _good_universe_series()

    response = create_portfolio_recommendation(
        portfolio_id=portfolio.id,
        data=RecommendationRequest(universe="NIFTY50"),
        user_id=user_id,
        db=db_session,
    )
    assert response.universe == "NIFTY50"
    assert response.universe_as_of == date(2026, 9, 1)
    assert response.excluded == []


@pytest.mark.db
def test_recommendation_route_all_ineligible_returns_422(db_session, test_portfolio, fake_market):
    from app.api.portfolios import create_portfolio_recommendation

    user_id, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        create_portfolio_recommendation(
            portfolio_id=portfolio.id,
            data=RecommendationRequest(tickers=["ZZTEST_MISSING1", "ZZTEST_MISSING2"]),
            user_id=user_id,
            db=db_session,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.db
def test_recommendation_route_unknown_universe_returns_422(db_session, test_portfolio):
    from app.api.portfolios import create_portfolio_recommendation

    user_id, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        create_portfolio_recommendation(
            portfolio_id=portfolio.id,
            data=RecommendationRequest(universe="NOT_A_UNIVERSE"),
            user_id=user_id,
            db=db_session,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.db
def test_recommendation_route_unauthorized_returns_404(db_session, test_portfolio):
    from app.api.portfolios import create_portfolio_recommendation

    _, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        create_portfolio_recommendation(
            portfolio_id=portfolio.id,
            data=RecommendationRequest(tickers=["ZZTEST_A"]),
            user_id=uuid4(),
            db=db_session,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.db
def test_recommendation_does_not_mutate_portfolio_state(db_session, test_portfolio, fake_market):
    from app.api.portfolios import create_portfolio_recommendation

    user_id, portfolio = test_portfolio
    holding = Holding(
        portfolio_id=portfolio.id, ticker="ZZTEST_A", quantity=Decimal("10"), average_cost=Decimal("100")
    )
    db_session.add(holding)
    db_session.commit()

    before_cash = db_session.get(Portfolio, portfolio.id).cash_balance
    before_holdings = db_session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count()
    before_txns = db_session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count()

    fake_market.series = _good_universe_series()
    create_portfolio_recommendation(
        portfolio_id=portfolio.id,
        data=RecommendationRequest(tickers=PLACEHOLDER_UNIVERSE),
        user_id=user_id,
        db=db_session,
    )

    db_session.expire_all()
    refreshed_holding = db_session.get(Holding, holding.id)
    assert refreshed_holding.quantity == Decimal("10")
    assert refreshed_holding.average_cost == Decimal("100")
    assert db_session.get(Portfolio, portfolio.id).cash_balance == before_cash
    assert db_session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count() == before_holdings
    assert (
        db_session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count()
        == before_txns
    )

    db_session.query(Holding).filter(Holding.id == holding.id).delete()
    db_session.commit()
