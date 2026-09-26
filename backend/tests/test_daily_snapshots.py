"""scripts/take_daily_snapshots.py with mocked prices."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Holding, Portfolio, PortfolioSnapshot, RiskProfile, UserProfile
from app.services import market_data
from app.services.market_calendar import MARKET_TIMEZONE
from app.services.market_data import MarketDataUnavailableError
from scripts import take_daily_snapshots as script

AFTER_CLOSE = datetime(2026, 9, 25, 16, 30, tzinfo=MARKET_TIMEZONE)  # a Friday
BEFORE_CLOSE = datetime(2026, 9, 25, 15, 45, tzinfo=MARKET_TIMEZONE)
SATURDAY_EVENING = datetime(2026, 9, 26, 18, 0, tzinfo=MARKET_TIMEZONE)


@pytest.fixture
def sqlite_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _portfolios(session, count):
    user_id = uuid4()
    session.add(UserProfile(id=user_id))
    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category="moderate",
        max_position_weight=Decimal("0.2"),
        max_sector_weight=Decimal("0.4"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(risk_profile)
    session.flush()
    portfolios = [
        Portfolio(
            user_id=user_id,
            risk_profile_id=risk_profile.id,
            name=f"P{i}",
            purpose=None,
            base_currency="INR",
            initial_capital=Decimal("1000"),
            cash_balance=Decimal("1000"),
        )
        for i in range(count)
    ]
    session.add_all(portfolios)
    session.commit()
    return portfolios


def test_nothing_runs_before_the_market_session_is_complete():
    # The early exit happens before any database access.
    summary = script.take_daily_snapshots(None, BEFORE_CLOSE)
    assert (summary.ran, summary.not_run_exit_code) == (False, script.EXIT_TOO_EARLY)
    assert script.market_closed_today(AFTER_CLOSE) is True


def test_weekend_exits_with_the_non_trading_day_code():
    summary = script.take_daily_snapshots(None, SATURDAY_EVENING)
    assert (summary.ran, summary.not_run_exit_code) == (False, script.EXIT_NON_TRADING_DAY)
    assert script.run_gate(AFTER_CLOSE) is None


def test_one_failure_does_not_stop_the_others(sqlite_db, monkeypatch):
    created, duplicate, broken, crashing = _portfolios(sqlite_db, 4)

    def fake_snapshot(db, user_id, portfolio_id):
        if portfolio_id == duplicate.id:
            raise HTTPException(status_code=409, detail="A snapshot already exists for this portfolio today")
        if portfolio_id == broken.id:
            raise MarketDataUnavailableError("ZZTEST_A", "no quote")
        if portfolio_id == crashing.id:
            raise RuntimeError("boom")
        return object()

    monkeypatch.setattr(script, "create_portfolio_snapshot", fake_snapshot)
    summary = script.take_daily_snapshots(sqlite_db, AFTER_CLOSE)

    assert summary.ran is True
    assert summary.created == [created.id]
    assert summary.skipped == [duplicate.id]
    assert set(summary.failed) == {broken.id, crashing.id}
    assert "no quote" in summary.failed[broken.id]
    assert "boom" in summary.failed[crashing.id]


@pytest.mark.db
def test_creates_then_skips_todays_snapshot(db_session, test_portfolio, monkeypatch):
    user_id, portfolio = test_portfolio
    db_session.add(
        Holding(portfolio_id=portfolio.id, ticker="ZZTEST_A", quantity=Decimal("2"), average_cost=Decimal("100"))
    )
    db_session.commit()
    monkeypatch.setattr(market_data, "get_current_price", lambda ticker: Decimal("110"))
    # The service keys by the real current IST date; open the gate so this runs any day.
    monkeypatch.setattr(script, "run_gate", lambda now: None)
    now = datetime.now(MARKET_TIMEZONE)

    first = script.take_daily_snapshots(db_session, now, portfolio_ids=[portfolio.id])
    second = script.take_daily_snapshots(db_session, now, portfolio_ids=[portfolio.id])

    assert (first.created, first.skipped, first.failed) == ([portfolio.id], [], {})
    assert (second.created, second.skipped, second.failed) == ([], [portfolio.id], {})
    [snapshot] = db_session.query(PortfolioSnapshot).filter(PortfolioSnapshot.portfolio_id == portfolio.id).all()
    assert snapshot.total_value == Decimal("50220")  # 50000 cash + 2 x 110
