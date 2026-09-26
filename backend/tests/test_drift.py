from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Holding, Portfolio, RecommendationSnapshot, RiskProfile, UserProfile
from app.services import drift as drift_service
from app.services.market_data import MarketDataUnavailableError
from app.services.drift import get_portfolio_drift


@pytest.fixture
def drift_db():
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
        drift_threshold=Decimal("0.02"),
        target_volatility=Decimal("0.15"),
    )
    session.add(UserProfile(id=user_id))
    session.add(risk_profile)
    session.flush()
    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="Drift test portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("100000"),
        cash_balance=Decimal("10000"),
    )
    session.add(portfolio)
    session.commit()
    yield session, user_id, portfolio
    session.close()
    engine.dispose()


def _add_target(session, portfolio, allocations, cash_weight, excluded=None, created_at=None):
    target = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        created_at=created_at or datetime.now(timezone.utc),
        capital=Decimal("100000"),
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        model_version=None,
        forecast_as_of=None,
        expected_portfolio_return=Decimal("0.08"),
        expected_portfolio_volatility=Decimal("0.12"),
        cash_weight=cash_weight,
        cash_amount=Decimal("10000"),
        max_position_weight=Decimal("0.2"),
        target_volatility=Decimal("0.15"),
        allocations=allocations,
        excluded=excluded or [],
    )
    session.add(target)
    session.commit()
    return target


def test_drift_calculates_current_and_target_weights(drift_db, monkeypatch):
    session, user_id, portfolio = drift_db
    portfolio.cash_balance = Decimal("10000")
    for ticker, quantity in (("A", "45"), ("B", "25"), ("C", "20")):
        session.add(
            Holding(
                portfolio_id=portfolio.id,
                ticker=ticker,
                quantity=Decimal(quantity),
                average_cost=Decimal("900"),
            )
        )
    target = _add_target(
        session,
        portfolio,
        [
            {"ticker": "A", "target_weight": "0.40"},
            {"ticker": "B", "target_weight": "0.30"},
            {"ticker": "C", "target_weight": "0.20"},
        ],
        Decimal("0.10"),
    )
    monkeypatch.setattr(
        drift_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("1000"),
    )

    result = get_portfolio_drift(session, user_id, portfolio.id)

    positions = {item.ticker: item for item in result.positions}
    assert result.portfolio_value == Decimal("100000")
    assert result.valuation_complete is True
    assert result.target_recommendation_id == target.id
    assert result.target_status == "current"
    assert positions["A"].current_weight == Decimal("0.45")
    assert positions["A"].target_weight == Decimal("0.40")
    assert positions["A"].status == "overweight"
    assert positions["B"].status == "underweight"
    assert positions["C"].status == "at_target"
    assert positions["CASH"].current_weight == Decimal("0.10")
    assert positions["CASH"].status == "at_target"
    assert result.attention_count == 2


def test_missing_target_and_empty_holdings_are_reported(drift_db):
    session, user_id, portfolio = drift_db

    result = get_portfolio_drift(session, user_id, portfolio.id)

    assert result.target_status == "missing"
    assert result.target_recommendation_id is None
    assert result.positions[0].ticker == "CASH"
    assert result.positions[0].current_weight == Decimal("1")
    assert result.positions[0].status == "no_target"
    assert result.attention_count == 0


def test_zero_portfolio_value_has_no_division_or_false_weight(drift_db):
    session, user_id, portfolio = drift_db
    portfolio.cash_balance = Decimal("0")
    session.commit()

    result = get_portfolio_drift(session, user_id, portfolio.id)

    assert result.portfolio_value == Decimal("0")
    assert result.positions[0].current_weight is None
    assert result.positions[0].status == "no_target"


def test_missing_holding_price_marks_weights_unavailable(drift_db, monkeypatch):
    session, user_id, portfolio = drift_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="NOQUOTE",
            quantity=Decimal("2"),
            average_cost=Decimal("10"),
        )
    )
    _add_target(
        session,
        portfolio,
        [{"ticker": "NOQUOTE", "target_weight": "0.5"}],
        Decimal("0.5"),
    )

    def missing_price(ticker):
        raise MarketDataUnavailableError(ticker, "not available")

    monkeypatch.setattr(drift_service.market_data, "get_current_price", missing_price)
    result = get_portfolio_drift(session, user_id, portfolio.id)
    position = next(item for item in result.positions if item.ticker == "NOQUOTE")

    assert result.valuation_complete is False
    assert result.portfolio_value is None
    assert result.missing_prices == ["NOQUOTE"]
    assert position.current_value is None
    assert position.current_weight is None
    assert position.status == "unavailable"


def test_excluded_holding_is_exposed_as_zero_target(drift_db, monkeypatch):
    session, user_id, portfolio = drift_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="EXCLUDED",
            quantity=Decimal("5"),
            average_cost=Decimal("100"),
        )
    )
    _add_target(
        session,
        portfolio,
        [],
        Decimal("1"),
        excluded=[{"ticker": "EXCLUDED", "reason": "insufficient history"}],
    )
    monkeypatch.setattr(
        drift_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )

    result = get_portfolio_drift(session, user_id, portfolio.id)
    excluded = next(item for item in result.positions if item.ticker == "EXCLUDED")

    assert excluded.target_weight == Decimal("0")
    assert excluded.excluded is True
    assert excluded.exclusion_reason == "insufficient history"
    assert excluded.status == "overweight"


def test_target_is_stale_after_portfolio_changes(drift_db, monkeypatch):
    session, user_id, portfolio = drift_db
    now = datetime.now(timezone.utc)
    portfolio.updated_at = now
    _add_target(
        session,
        portfolio,
        [],
        Decimal("1"),
        created_at=now - timedelta(days=1),
    )
    monkeypatch.setattr(
        drift_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("1"),
    )

    result = get_portfolio_drift(session, user_id, portfolio.id)

    assert result.target_status == "stale"


def test_drift_rejects_another_users_portfolio(drift_db):
    session, _, portfolio = drift_db

    with pytest.raises(HTTPException) as exc_info:
        get_portfolio_drift(session, uuid4(), portfolio.id)

    assert exc_info.value.status_code == 404