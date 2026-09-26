from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Holding, Portfolio, RebalanceProposal, RecommendationSnapshot, Transaction
from app.schemas.rebalance import RebalanceExecutionRead, RebalanceTradeRead
from app.services import market_data
from app.services.market_data import MarketDataUnavailableError
from app.services.rebalancing import _fingerprint


class RebalanceExecutionConflict(Exception):
    pass


def execute_rebalance_proposal(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    proposal_id: UUID,
) -> RebalanceExecutionRead:
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
    )
    if portfolio is None or portfolio.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")

    proposal = db.scalar(
        select(RebalanceProposal)
        .where(
            RebalanceProposal.id == proposal_id,
            RebalanceProposal.portfolio_id == portfolio_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rebalance proposal not found")
    if proposal.status != "PENDING":
        raise RebalanceExecutionConflict("This proposal is no longer pending execution")

    holdings = db.scalars(
        select(Holding)
        .where(Holding.portfolio_id == portfolio_id)
        .order_by(Holding.ticker)
        .with_for_update()
    ).all()
    target = db.get(RecommendationSnapshot, proposal.recommendation_id)
    if target is None or target.portfolio_id != portfolio_id:
        proposal.status = "EXPIRED"
        db.commit()
        raise RebalanceExecutionConflict("The target recommendation is no longer available")

    tickers = sorted(
        {holding.ticker for holding in holdings}
        | {item["ticker"] for item in target.allocations}
    )
    try:
        prices = {ticker: market_data.get_current_price(ticker) for ticker in tickers}
    except MarketDataUnavailableError:
        raise

    current_fingerprint = _fingerprint(portfolio, holdings, target, prices)
    if current_fingerprint != proposal.state_fingerprint:
        proposal.status = "EXPIRED"
        db.commit()
        raise RebalanceExecutionConflict(
            "Portfolio state or prices changed after this proposal; create a new proposal"
        )

    try:
        trades = [RebalanceTradeRead.model_validate(item) for item in proposal.trades]
    except ValueError as exc:
        proposal.status = "EXPIRED"
        db.commit()
        raise RebalanceExecutionConflict("The saved proposal contains invalid trades") from exc

    holdings_by_ticker = {holding.ticker: holding for holding in holdings}
    available_cash = portfolio.cash_balance
    for trade in trades:
        if trade.quantity <= 0 or trade.quantity != int(trade.quantity):
            raise RebalanceExecutionConflict("Proposal quantities must be positive whole shares")
        price = prices.get(trade.ticker)
        if price is None or price != trade.estimated_price:
            proposal.status = "EXPIRED"
            db.commit()
            raise RebalanceExecutionConflict(
                "A quoted price changed after review; create a new proposal"
            )
        amount = Decimal(trade.quantity) * price
        holding = holdings_by_ticker.get(trade.ticker)
        if trade.side == "SELL":
            if holding is None or holding.quantity < Decimal(trade.quantity):
                raise RebalanceExecutionConflict("A proposed sale exceeds the current holding")
            available_cash += amount
        else:
            available_cash -= amount
            if available_cash < 0:
                raise RebalanceExecutionConflict("The proposal exceeds available cash")

    transaction_ids: list[UUID] = []
    occurred_at = datetime.now(timezone.utc)
    try:
        for trade in trades:
            quantity = Decimal(trade.quantity)
            price = prices[trade.ticker]
            holding = holdings_by_ticker.get(trade.ticker)
            if trade.side == "SELL":
                portfolio.cash_balance += quantity * price
                holding.quantity -= quantity
                if holding.quantity == 0:
                    db.delete(holding)
                    del holdings_by_ticker[trade.ticker]
            else:
                cost = quantity * price
                portfolio.cash_balance -= cost
                if holding is None:
                    holding = Holding(
                        portfolio_id=portfolio_id,
                        ticker=trade.ticker,
                        quantity=quantity,
                        average_cost=price,
                    )
                    db.add(holding)
                    holdings_by_ticker[trade.ticker] = holding
                else:
                    old_cost = holding.quantity * holding.average_cost
                    holding.quantity += quantity
                    holding.average_cost = (old_cost + cost) / holding.quantity

            transaction = Transaction(
                id=uuid4(),
                portfolio_id=portfolio_id,
                ticker=trade.ticker,
                transaction_type=trade.side,
                quantity=quantity,
                price=price,
                fees=Decimal("0"),
                occurred_at=occurred_at,
                source="rebalance",
            )
            db.add(transaction)
            transaction_ids.append(transaction.id)

        proposal.status = "EXECUTED"
        proposal.executed_at = occurred_at
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(portfolio)
    return RebalanceExecutionRead(
        proposal_id=proposal.id,
        status="EXECUTED",
        transaction_ids=transaction_ids,
        cash_balance=portfolio.cash_balance,
    )