from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api import portfolios as portfolio_api
from app.database import Base
from app.models import Portfolio, RecommendationSnapshot, RiskProfile, UserProfile
from app.services.recommendation import (
    Recommendation,
    RecommendationConstraints,
    RecommendedAllocation,
    get_recommendation_snapshot,
    list_recommendation_snapshots,
    persist_recommendation_snapshot,
)
from app.services.universe import ExcludedTicker


@pytest.fixture
def history_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user_id = uuid4()
    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category="moderate",
        max_position_weight=Decimal("0.2"),
        max_sector_weight=Decimal("0.4"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(UserProfile(id=user_id))
    session.add(risk_profile)
    session.flush()
    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="History test portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("100000"),
        cash_balance=Decimal("100000"),
    )
    session.add(portfolio)
    session.commit()
    yield session, user_id, portfolio
    session.close()
    engine.dispose()


def _recommendation(capital: Decimal = Decimal("100000")) -> Recommendation:
    return Recommendation(
        universe="CUSTOM",
        universe_as_of=date(2026, 9, 1),
        return_model="ml",
        model_version="test-model-v1",
        forecast_as_of=date(2026, 9, 2),
        capital=capital,
        allocations=[
            RecommendedAllocation(
                ticker="TEST",
                expected_return=Decimal("0.12"),
                target_weight=Decimal("0.4"),
                amount=capital * Decimal("0.4"),
                at_position_limit=True,
                source="ml",
            )
        ],
        cash_weight=Decimal("0.6"),
        cash_amount=capital * Decimal("0.6"),
        expected_portfolio_return=Decimal("0.048"),
        expected_portfolio_volatility=Decimal("0.1"),
        constraints=RecommendationConstraints(
            max_position_weight=Decimal("0.4"),
            target_volatility=Decimal("0.15"),
        ),
        excluded=[ExcludedTicker("EXCLUDED", "insufficient history")],
    )


def test_empty_recommendation_history(history_db):
    session, user_id, portfolio = history_db

    assert list_recommendation_snapshots(session, user_id, portfolio.id) == []
    assert portfolio_api.read_portfolio_recommendations(
        portfolio_id=portfolio.id,
        user_id=user_id,
        db=session,
    ) == []


def test_recommendation_snapshot_persists_complete_data(history_db):
    session, user_id, portfolio = history_db
    recommendation = _recommendation()

    snapshot = persist_recommendation_snapshot(session, portfolio.id, recommendation)

    stored = get_recommendation_snapshot(session, user_id, portfolio.id, snapshot.id)
    assert stored.portfolio_id == portfolio.id
    assert stored.capital == Decimal("100000")
    assert stored.universe == "CUSTOM"
    assert stored.universe_as_of == date(2026, 9, 1)
    assert stored.return_model == "ml"
    assert stored.model_version == "test-model-v1"
    assert stored.forecast_as_of == date(2026, 9, 2)
    assert stored.allocations[0]["ticker"] == "TEST"
    assert stored.allocations[0]["source"] == "ml"
    assert stored.excluded == [{"ticker": "EXCLUDED", "reason": "insufficient history"}]


def test_saved_recommendation_is_immutable_and_detail_uses_snapshot(history_db, monkeypatch):
    session, user_id, portfolio = history_db
    recommendation = _recommendation()
    snapshot = persist_recommendation_snapshot(session, portfolio.id, recommendation)
    original_allocation = dict(snapshot.allocations[0])
    recommendation.allocations[0].target_weight = Decimal("0.9")
    recommendation.allocations[0].amount = Decimal("90000")

    def unexpected_regeneration(*_args, **_kwargs):
        pytest.fail("Opening history must not regenerate a recommendation")

    monkeypatch.setattr(portfolio_api, "get_portfolio_recommendation", unexpected_regeneration)
    detail = portfolio_api.read_portfolio_recommendation(
        portfolio_id=portfolio.id,
        recommendation_id=snapshot.id,
        user_id=user_id,
        db=session,
    )

    assert detail.id == snapshot.id
    assert detail.created_at == snapshot.created_at
    assert detail.allocations[0].target_weight == Decimal(original_allocation["target_weight"])
    assert detail.allocations[0].amount == Decimal(original_allocation["amount"])
    assert detail.excluded[0].reason == "insufficient history"


def test_recommendation_history_orders_newest_first(history_db):
    session, user_id, portfolio = history_db
    first = persist_recommendation_snapshot(session, portfolio.id, _recommendation())
    second = persist_recommendation_snapshot(
        session,
        portfolio.id,
        _recommendation(Decimal("120000")),
    )
    first.created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    second.created_at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    session.commit()

    history = list_recommendation_snapshots(session, user_id, portfolio.id)

    assert [item.id for item in history] == [second.id, first.id]


def test_recommendation_history_isolated_by_portfolio(history_db):
    session, user_id, portfolio = history_db
    snapshot = persist_recommendation_snapshot(session, portfolio.id, _recommendation())
    other_portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=portfolio.risk_profile_id,
        name="Other portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("50000"),
        cash_balance=Decimal("50000"),
    )
    session.add(other_portfolio)
    session.commit()

    assert list_recommendation_snapshots(session, user_id, other_portfolio.id) == []
    with pytest.raises(ValueError, match="Recommendation not found"):
        get_recommendation_snapshot(session, user_id, other_portfolio.id, snapshot.id)


def test_invalid_portfolio_access_is_rejected(history_db):
    session, _, portfolio = history_db
    with pytest.raises(HTTPException) as exc_info:
        list_recommendation_snapshots(session, uuid4(), portfolio.id)
    assert exc_info.value.status_code == 404


def test_detail_returns_persisted_clipping_and_drivers(history_db):
    from app.services.return_providers import Driver

    session, user_id, portfolio = history_db
    recommendation = _recommendation()
    allocation = recommendation.allocations[0]
    allocation.clipped = True
    allocation.drivers = [
        Driver(feature="momentum_20", value=Decimal("0.08"), contribution=Decimal("0.031")),
        Driver(feature="rsi_14", value=Decimal("61.2"), contribution=Decimal("-0.004")),
    ]
    allocation.typical_estimate = Decimal("0.095")
    snapshot = persist_recommendation_snapshot(session, portfolio.id, recommendation)

    detail = portfolio_api.read_portfolio_recommendation(
        portfolio_id=portfolio.id, recommendation_id=snapshot.id, user_id=user_id, db=session
    )

    [item] = detail.allocations
    assert item.clipped is True
    assert item.typical_estimate == Decimal("0.095")
    assert [(d.feature, d.value, d.contribution) for d in item.drivers] == [
        ("momentum_20", Decimal("0.08"), Decimal("0.031")),
        ("rsi_14", Decimal("61.2"), Decimal("-0.004")),
    ]


def test_detail_of_a_snapshot_saved_before_drivers_existed_uses_defaults(history_db):
    session, user_id, portfolio = history_db
    snapshot = persist_recommendation_snapshot(session, portfolio.id, _recommendation())
    snapshot.allocations = [
        {k: v for k, v in item.items() if k not in {"clipped", "drivers", "typical_estimate"}}
        for item in snapshot.allocations
    ]
    session.commit()

    detail = portfolio_api.read_portfolio_recommendation(
        portfolio_id=portfolio.id, recommendation_id=snapshot.id, user_id=user_id, db=session
    )
    [item] = detail.allocations
    assert (item.clipped, item.drivers, item.typical_estimate) == (False, [], None)


@pytest.mark.parametrize("source", ["precomputed", "on_request", None])
def test_detail_returns_persisted_forecast_source(history_db, source):
    session, user_id, portfolio = history_db
    recommendation = _recommendation()
    recommendation.forecast_source = source
    snapshot = persist_recommendation_snapshot(session, portfolio.id, recommendation)

    detail = portfolio_api.read_portfolio_recommendation(
        portfolio_id=portfolio.id, recommendation_id=snapshot.id, user_id=user_id, db=session
    )
    assert detail.forecast_source == source
