"""GET /portfolios/overview on an in-memory SQLite database with mocked prices."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api import portfolios as portfolio_api
from app.database import Base
from app.models import Holding, Portfolio, RiskProfile, UserProfile
from app.services import market_data
from app.services.market_data import MarketDataUnavailableError
from app.services.recommendation import (
    Recommendation,
    RecommendationConstraints,
    persist_recommendation_snapshot,
)


@pytest.fixture
def overview_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _user_with_portfolios(session, names, category="moderate"):
    user_id = uuid4()
    session.add(UserProfile(id=user_id))
    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category=category,
        max_position_weight=Decimal("0.2"),
        max_sector_weight=Decimal("0.4"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(risk_profile)
    session.flush()
    portfolios = []
    for i, name in enumerate(names):
        portfolio = Portfolio(
            user_id=user_id,
            risk_profile_id=risk_profile.id,
            name=name,
            purpose=None,
            base_currency="INR",
            initial_capital=Decimal("100000"),
            cash_balance=Decimal("40000"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        )
        session.add(portfolio)
        portfolios.append(portfolio)
    session.commit()
    return user_id, portfolios


def _hold(session, portfolio, ticker, quantity="10", cost="100"):
    session.add(
        Holding(portfolio_id=portfolio.id, ticker=ticker, quantity=Decimal(quantity), average_cost=Decimal(cost))
    )
    session.commit()


def _prices(monkeypatch, prices):
    def fake_price(ticker):
        if ticker not in prices:
            raise MarketDataUnavailableError(ticker, "no quote")
        return prices[ticker]

    monkeypatch.setattr(market_data, "get_current_price", fake_price)


def _recommendation(capital=Decimal("40000")):
    return Recommendation(
        universe="NIFTY50",
        universe_as_of=date(2026, 9, 1),
        return_model="ml",
        capital=capital,
        allocations=[],
        cash_weight=Decimal("1"),
        cash_amount=capital,
        expected_portfolio_return=Decimal("0"),
        expected_portfolio_volatility=Decimal("0"),
        constraints=RecommendationConstraints(max_position_weight=Decimal("0.2"), target_volatility=Decimal("0.15")),
        excluded=[],
        model_version="test-v1",
    )


def test_one_portfolios_price_failure_does_not_fail_the_others(overview_db, monkeypatch):
    user_id, (good, broken) = _user_with_portfolios(overview_db, ["Good", "Broken"])
    _hold(overview_db, good, "ZZTEST_A", quantity="10", cost="100")
    _hold(overview_db, broken, "ZZTEST_MISSING")
    _prices(monkeypatch, {"ZZTEST_A": Decimal("120")})

    overview = portfolio_api.read_portfolios_overview(user_id=user_id, db=overview_db)

    by_name = {p.name: p for p in overview.portfolios}
    ok = by_name["Good"]
    assert ok.valuation_status == "ok"
    assert ok.market_value == Decimal("1200")
    assert ok.total_value == Decimal("41200")
    assert ok.unrealized_pnl == Decimal("200")
    assert ok.unrealized_pnl_pct == Decimal("0.2")

    failed = by_name["Broken"]
    assert failed.valuation_status == "unavailable"
    assert (failed.market_value, failed.total_value, failed.unrealized_pnl, failed.unrealized_pnl_pct) == (
        None,
        None,
        None,
        None,
    )

    # Value totals cover only the valued portfolio; capital and cash cover both.
    assert overview.totals.portfolio_count == 2
    assert overview.totals.valued_portfolio_count == 1
    assert overview.totals.total_value == Decimal("41200")
    assert overview.totals.market_value == Decimal("1200")
    assert overview.totals.unrealized_pnl == Decimal("200")
    assert overview.totals.initial_capital == Decimal("200000")
    assert overview.totals.cash_balance == Decimal("80000")


def test_portfolio_without_holdings_is_valued_at_its_cash(overview_db, monkeypatch):
    user_id, (portfolio,) = _user_with_portfolios(overview_db, ["Cash only"])
    _prices(monkeypatch, {})

    [item] = portfolio_api.read_portfolios_overview(user_id=user_id, db=overview_db).portfolios
    assert item.valuation_status == "ok"
    assert (item.total_value, item.market_value, item.unrealized_pnl_pct) == (Decimal("40000"), Decimal("0"), None)


def test_latest_recommendation_is_the_newest_snapshot(overview_db, monkeypatch):
    user_id, (portfolio, other) = _user_with_portfolios(overview_db, ["With history", "Without"])
    _prices(monkeypatch, {})
    older = persist_recommendation_snapshot(overview_db, portfolio.id, _recommendation(Decimal("30000")))
    newer = persist_recommendation_snapshot(overview_db, portfolio.id, _recommendation(Decimal("40000")))
    older.created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    newer.created_at = datetime(2026, 9, 5, tzinfo=timezone.utc)
    overview_db.commit()

    overview = portfolio_api.read_portfolios_overview(user_id=user_id, db=overview_db)

    by_name = {p.name: p for p in overview.portfolios}
    latest = by_name["With history"].latest_recommendation
    assert latest is not None
    assert latest.id == newer.id
    assert latest.capital == Decimal("40000")
    assert by_name["Without"].latest_recommendation is None


def test_overview_only_includes_the_callers_portfolios(overview_db, monkeypatch):
    owner, _ = _user_with_portfolios(overview_db, ["Mine"])
    stranger, (theirs,) = _user_with_portfolios(overview_db, ["Theirs"])
    persist_recommendation_snapshot(overview_db, theirs.id, _recommendation())
    _prices(monkeypatch, {})

    mine = portfolio_api.read_portfolios_overview(user_id=owner, db=overview_db)
    assert [p.name for p in mine.portfolios] == ["Mine"]
    assert mine.portfolios[0].latest_recommendation is None

    nobody = portfolio_api.read_portfolios_overview(user_id=uuid4(), db=overview_db)
    assert nobody.portfolios == []
    assert (nobody.totals.portfolio_count, nobody.totals.valued_portfolio_count, nobody.totals.total_value) == (0, 0, None)
