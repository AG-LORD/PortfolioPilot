from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Holding, Portfolio, RiskProfile, Transaction, UserProfile
from app.schemas.portfolio import PortfolioCapitalAddRequest
from app.schemas.transaction import TransactionCreate
from app.api.portfolios import add_portfolio_capital
from app.services.transactions import execute_transaction


@pytest.fixture
def sqlite_portfolio():
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
        max_position_weight=Decimal("0.1"),
        max_sector_weight=Decimal("0.25"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(UserProfile(id=user_id))
    session.add(risk_profile)
    session.flush()
    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="Test Portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("100000"),
        cash_balance=Decimal("50000"),
    )
    session.add(portfolio)
    session.commit()

    yield session, user_id, portfolio

    session.close()
    engine.dispose()


@pytest.mark.parametrize("transaction_type", ["TRANSFER"])
def test_manual_transaction_schema_rejects_unknown_types(transaction_type):
    with pytest.raises(ValidationError):
        TransactionCreate(
            ticker="ZZTESTTRADE",
            transaction_type=transaction_type,
            quantity=Decimal("1"),
            price=Decimal("10"),
        )


def test_manual_transaction_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="must include a timezone"):
        TransactionCreate(
            ticker="TCS",
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("10"),
            occurred_at=datetime(2026, 9, 26),
        )


@pytest.mark.parametrize("ticker", ["", "BAD/TICKER", "CASH"])
def test_stock_trade_rejects_invalid_or_reserved_ticker(sqlite_portfolio, ticker):
    session, user_id, portfolio = sqlite_portfolio
    with pytest.raises(HTTPException) as exc_info:
        execute_transaction(
            session,
            user_id,
            portfolio.id,
            TransactionCreate(
                ticker=ticker,
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("10"),
            ),
        )

    assert exc_info.value.status_code == 422


def test_stock_ticker_is_normalized_before_persistence(sqlite_portfolio):
    session, user_id, portfolio = sqlite_portfolio
    transaction = execute_transaction(
        session,
        user_id,
        portfolio.id,
        TransactionCreate(
            ticker=" tcs.ns ",
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("10"),
        ),
    )
    holding = session.query(Holding).filter(Holding.portfolio_id == portfolio.id).one()

    assert transaction.ticker == "TCS"
    assert holding.ticker == "TCS"


def test_capital_deposit_persists_without_changing_holdings(sqlite_portfolio):
    session, user_id, portfolio = sqlite_portfolio
    original_holding = Holding(
        portfolio_id=portfolio.id,
        ticker="ZZTEST_EXISTING",
        quantity=Decimal("3"),
        average_cost=Decimal("125"),
    )
    session.add(original_holding)
    session.commit()
    original_cash = portfolio.cash_balance

    updated = add_portfolio_capital(
        portfolio_id=portfolio.id,
        data=PortfolioCapitalAddRequest(amount=Decimal("50000")),
        user_id=user_id,
        db=session,
    )

    assert updated.cash_balance == original_cash + Decimal("50000")
    [transaction] = session.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id
    ).all()
    assert (transaction.ticker, transaction.transaction_type, transaction.source) == (
        "CASH",
        "DEPOSIT",
        "capital",
    )
    assert transaction.quantity == Decimal("1")
    assert transaction.price == Decimal("50000")
    assert transaction.fees == Decimal("0")
    [remaining_holding] = session.query(Holding).filter(
        Holding.portfolio_id == portfolio.id
    ).all()
    assert remaining_holding.id == original_holding.id
    assert remaining_holding.ticker == "ZZTEST_EXISTING"
    assert remaining_holding.quantity == Decimal("3")
    assert session.query(Holding).filter(
        Holding.portfolio_id == portfolio.id,
        Holding.ticker == "CASH",
    ).count() == 0


def test_buy_and_sell_transaction_behavior_is_unchanged(sqlite_portfolio):
    session, user_id, portfolio = sqlite_portfolio

    buy = execute_transaction(
        session,
        user_id,
        portfolio.id,
        TransactionCreate(
            ticker="ZZTESTTRADE",
            transaction_type="BUY",
            quantity=Decimal("2"),
            price=Decimal("100"),
            fees=Decimal("2"),
        ),
    )
    assert buy.transaction_type == "BUY"
    assert buy.source == "manual"
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("49798")

    holding = (
        session.query(Holding)
        .filter(Holding.portfolio_id == portfolio.id, Holding.ticker == "ZZTESTTRADE")
        .one()
    )
    assert holding.quantity == Decimal("2")
    assert holding.average_cost == Decimal("101")

    sell = execute_transaction(
        session,
        user_id,
        portfolio.id,
        TransactionCreate(
            ticker="ZZTESTTRADE",
            transaction_type="SELL",
            quantity=Decimal("1"),
            price=Decimal("120"),
            fees=Decimal("1"),
        ),
    )
    assert sell.transaction_type == "SELL"
    assert sell.source == "manual"
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("49917")
    assert session.get(Holding, holding.id).quantity == Decimal("1")


def test_deposit_transaction_is_cash_only(sqlite_portfolio):
    session, user_id, portfolio = sqlite_portfolio
    original_cash = portfolio.cash_balance

    deposit = execute_transaction(
        session,
        user_id,
        portfolio.id,
        TransactionCreate(
            ticker="CASH",
            transaction_type="DEPOSIT",
            quantity=Decimal("1"),
            price=Decimal("250"),
        ),
    )

    assert deposit.transaction_type == "DEPOSIT"
    assert deposit.ticker == "CASH"
    assert deposit.source == "manual"
    assert session.get(Portfolio, portfolio.id).cash_balance == original_cash + Decimal("250")
    assert session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count() == 0


def test_sell_fees_cannot_exceed_sale_proceeds(sqlite_portfolio):
    session, user_id, portfolio = sqlite_portfolio
    holding = Holding(
        portfolio_id=portfolio.id,
        ticker="TCS",
        quantity=Decimal("1"),
        average_cost=Decimal("10"),
    )
    session.add(holding)
    session.commit()
    cash_before = portfolio.cash_balance

    with pytest.raises(HTTPException) as exc_info:
        execute_transaction(
            session,
            user_id,
            portfolio.id,
            TransactionCreate(
                ticker="TCS",
                transaction_type="SELL",
                quantity=Decimal("1"),
                price=Decimal("10"),
                fees=Decimal("11"),
            ),
        )

    assert exc_info.value.status_code == 422
    session.rollback()
    assert session.get(Holding, holding.id).quantity == Decimal("1")
    assert session.get(Portfolio, portfolio.id).cash_balance == cash_before


def test_invalid_transaction_type_is_rejected_atomically(sqlite_portfolio):
    session, _, portfolio = sqlite_portfolio
    original_cash = portfolio.cash_balance
    portfolio.cash_balance += Decimal("100")
    session.add(
        Transaction(
            portfolio_id=portfolio.id,
            ticker="CASH",
            transaction_type="TRANSFER",
            quantity=Decimal("1"),
            price=Decimal("100"),
            fees=Decimal("0"),
            occurred_at=portfolio.created_at,
            source="capital",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    assert session.get(Portfolio, portfolio.id).cash_balance == original_cash
    assert session.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id
    ).count() == 0