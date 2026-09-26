import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Holding, Transaction
from app.schemas.transaction import TransactionCreate
from app.services.portfolios import get_portfolio_for_update

_TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]{0,19}$")


def _normalize_transaction_ticker(raw_ticker: str, transaction_type: str) -> str:
    ticker = raw_ticker.strip().upper()
    if ticker.endswith(".NS"):
        ticker = ticker[:-3]
    if not _TICKER_PATTERN.fullmatch(ticker):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Ticker must be a valid NSE symbol",
        )
    if transaction_type == "DEPOSIT" and ticker != "CASH":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Deposits must use the CASH ticker",
        )
    if transaction_type != "DEPOSIT" and ticker == "CASH":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CASH is reserved for deposit transactions",
        )
    return ticker


def execute_transaction(
    db: Session, user_id: UUID, portfolio_id: UUID, data: TransactionCreate
) -> Transaction:
    portfolio = get_portfolio_for_update(db, user_id, portfolio_id)
    ticker = _normalize_transaction_ticker(data.ticker, data.transaction_type)

    holding = db.scalar(
        select(Holding)
        .where(Holding.portfolio_id == portfolio_id, Holding.ticker == ticker)
        .with_for_update()
    )

    if data.transaction_type == "BUY":
        cost = data.quantity * data.price + data.fees
        if cost > portfolio.cash_balance:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient cash balance")

        portfolio.cash_balance -= cost

        if holding is None:
            holding = Holding(
                portfolio_id=portfolio_id,
                ticker=ticker,
                quantity=data.quantity,
                average_cost=(data.quantity * data.price + data.fees) / data.quantity,
            )
            db.add(holding)
        else:
            total_cost = (
                holding.quantity * holding.average_cost
                + data.quantity * data.price
                + data.fees
            )
            new_quantity = holding.quantity + data.quantity
            holding.average_cost = total_cost / new_quantity
            holding.quantity = new_quantity

    elif data.transaction_type == "SELL":
        if holding is None or holding.quantity < data.quantity:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient holding quantity")

        proceeds = data.quantity * data.price - data.fees
        if proceeds < 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Fees cannot exceed sale proceeds",
            )
        portfolio.cash_balance += proceeds
        holding.quantity -= data.quantity

        if holding.quantity == 0:
            db.delete(holding)
    else:  # DEPOSIT
        deposit_amount = data.quantity * data.price - data.fees
        if deposit_amount <= 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Deposit amount must be positive after fees",
            )
        portfolio.cash_balance += deposit_amount

    transaction = Transaction(
        portfolio_id=portfolio_id,
        ticker=ticker,
        transaction_type=data.transaction_type,
        quantity=data.quantity,
        price=data.price,
        fees=data.fees,
        occurred_at=data.occurred_at or datetime.now(timezone.utc),
        source="manual",
    )
    db.add(transaction)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(transaction)
    return transaction

def list_transactions(db: Session, user_id: UUID, portfolio_id: UUID) -> list[Transaction]:
    from app.services.portfolios import get_portfolio
    get_portfolio(db, user_id, portfolio_id)
    return (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.occurred_at.desc())
        .all()
    )
