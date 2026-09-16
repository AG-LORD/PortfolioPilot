from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Holding, Transaction
from app.schemas.transaction import TransactionCreate
from app.services.portfolios import get_portfolio


def execute_transaction(
    db: Session, user_id: UUID, portfolio_id: UUID, data: TransactionCreate
) -> Transaction:
    portfolio = get_portfolio(db, user_id, portfolio_id)

    holding = (
        db.query(Holding)
        .filter(Holding.portfolio_id == portfolio_id, Holding.ticker == data.ticker)
        .first()
    )

    if data.transaction_type == "BUY":
        cost = data.quantity * data.price + data.fees
        if cost > portfolio.cash_balance:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient cash balance")

        portfolio.cash_balance -= cost

        if holding is None:
            holding = Holding(
                portfolio_id=portfolio_id,
                ticker=data.ticker,
                quantity=data.quantity,
                average_cost=data.price,
            )
            db.add(holding)
        else:
            total_cost = holding.quantity * holding.average_cost + data.quantity * data.price
            new_quantity = holding.quantity + data.quantity
            holding.average_cost = total_cost / new_quantity
            holding.quantity = new_quantity

    else:  # SELL
        if holding is None or holding.quantity < data.quantity:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient holding quantity")

        proceeds = data.quantity * data.price - data.fees
        portfolio.cash_balance += proceeds
        holding.quantity -= data.quantity

        if holding.quantity == 0:
            db.delete(holding)

    transaction = Transaction(
        portfolio_id=portfolio_id,
        ticker=data.ticker,
        transaction_type=data.transaction_type,
        quantity=data.quantity,
        price=data.price,
        fees=data.fees,
        occurred_at=data.occurred_at or datetime.now(timezone.utc),
        source="manual",
    )
    db.add(transaction)

    db.commit()
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
