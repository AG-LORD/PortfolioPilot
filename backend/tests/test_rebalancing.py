from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Holding, Portfolio, RebalanceProposal, RecommendationSnapshot, RiskProfile, Transaction, UserProfile
from app.services.market_data import MarketDataUnavailableError
from app.services import rebalancing as rebalance_service
from app.services.rebalancing import create_rebalance_proposal, get_rebalance_proposal


@pytest.fixture
def rebalance_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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
        max_position_weight=Decimal("0.5"),
        max_sector_weight=Decimal("0.6"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(UserProfile(id=user_id))
    session.add(risk_profile)
    session.flush()
    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="Rebalance test portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("1000"),
        cash_balance=Decimal("600"),
    )
    session.add(portfolio)
    session.commit()
    yield session, user_id, portfolio
    session.close()
    engine.dispose()


def _add_target(session, portfolio, allocations, cash_weight=Decimal("0.3"), created_at=None):
    target = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        created_at=created_at or datetime.now(timezone.utc) + timedelta(seconds=1),
        capital=Decimal("1000"),
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        model_version=None,
        forecast_as_of=None,
        expected_portfolio_return=Decimal("0.1"),
        expected_portfolio_volatility=Decimal("0.1"),
        cash_weight=cash_weight,
        cash_amount=Decimal("300"),
        max_position_weight=Decimal("0.5"),
        target_volatility=Decimal("0.15"),
        allocations=allocations,
        excluded=[],
    )
    session.add(target)
    session.commit()
    return target


def test_proposal_uses_whole_shares_and_does_not_execute(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="A",
            quantity=Decimal("4"),
            average_cost=Decimal("90"),
        )
    )
    target = _add_target(
        session,
        portfolio,
        [
            {"ticker": "A", "target_weight": "0.2"},
            {"ticker": "B", "target_weight": "0.5"},
        ],
    )
    monkeypatch.setattr(
        rebalance_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )
    cash_before = portfolio.cash_balance
    holdings_before = [(h.ticker, h.quantity) for h in session.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()]
    transaction_count_before = session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count()

    first = create_rebalance_proposal(session, user_id, portfolio.id)
    second = create_rebalance_proposal(session, user_id, portfolio.id)

    trades = {(trade.ticker, trade.side): trade for trade in first.trades}
    assert set(trades) == {("A", "SELL"), ("B", "BUY")}
    assert trades[("A", "SELL")].quantity == 2
    assert trades[("B", "BUY")].quantity == 5
    assert all(isinstance(trade.quantity, int) for trade in first.trades)
    assert first.recommendation_id == target.id
    assert first.sell_total == Decimal("200")
    assert first.buy_total == Decimal("500")
    assert first.projected_cash == Decimal("300")
    assert first.estimated_fees == Decimal("0")
    assert first.fee_assumption.startswith("No fee schedule")
    assert [trade.model_dump() for trade in first.trades] == [trade.model_dump() for trade in second.trades]
    assert portfolio.cash_balance == cash_before
    assert [(h.ticker, h.quantity) for h in session.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()] == holdings_before
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == transaction_count_before
    assert first.status == "PENDING"


def test_buy_plan_never_exceeds_cash_when_target_is_over_budget(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    portfolio.cash_balance = Decimal("100")
    _add_target(
        session,
        portfolio,
        [{"ticker": "B", "target_weight": "2.0"}],
        cash_weight=Decimal("0"),
    )
    monkeypatch.setattr(
        rebalance_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("30"),
    )

    proposal = create_rebalance_proposal(session, user_id, portfolio.id)

    [trade] = proposal.trades
    assert trade.side == "BUY"
    assert trade.quantity == 3
    assert trade.estimated_net_amount <= proposal.cash_before
    assert proposal.projected_cash == Decimal("10")


def test_proposal_requires_saved_target(rebalance_db):
    session, user_id, portfolio = rebalance_db

    with pytest.raises(ValueError, match="saved recommendation"):
        create_rebalance_proposal(session, user_id, portfolio.id)


def test_stale_target_is_rejected(rebalance_db):
    session, user_id, portfolio = rebalance_db
    portfolio.updated_at = datetime.now(timezone.utc)
    _add_target(
        session,
        portfolio,
        [{"ticker": "A", "target_weight": "0.5"}],
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    with pytest.raises(ValueError, match="stale"):
        create_rebalance_proposal(session, user_id, portfolio.id)


def test_missing_market_price_prevents_proposal(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "A", "target_weight": "0.5"}])

    def missing_price(ticker):
        raise MarketDataUnavailableError(ticker, "missing test quote")

    monkeypatch.setattr(rebalance_service.market_data, "get_current_price", missing_price)

    with pytest.raises(MarketDataUnavailableError):
        create_rebalance_proposal(session, user_id, portfolio.id)


def test_proposal_read_is_scoped_to_portfolio_and_owner(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    target = _add_target(session, portfolio, [{"ticker": "A", "target_weight": "0.5"}])
    monkeypatch.setattr(
        rebalance_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)

    assert get_rebalance_proposal(session, user_id, portfolio.id, proposal.id).id == proposal.id
    with pytest.raises(ValueError, match="not found"):
        get_rebalance_proposal(session, user_id, portfolio.id, uuid4())
    with pytest.raises(HTTPException) as exc_info:
        get_rebalance_proposal(session, uuid4(), portfolio.id, proposal.id)
    assert exc_info.value.status_code == 404
    assert target.id == proposal.recommendation_id


def test_other_user_cannot_create_rebalance_proposal(rebalance_db, monkeypatch):
    session, _, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "B", "target_weight": "0.5"}])

    def market_data_must_not_be_requested(*_args, **_kwargs):
        pytest.fail("Ownership must be checked before proposal price lookups")

    monkeypatch.setattr(rebalance_service.market_data, "get_current_price", market_data_must_not_be_requested)
    with pytest.raises(HTTPException) as exc_info:
        create_rebalance_proposal(session, uuid4(), portfolio.id)

    assert exc_info.value.status_code == 404
    assert session.query(RebalanceProposal).filter(RebalanceProposal.portfolio_id == portfolio.id).count() == 0