from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import PortfolioSnapshot
from app.services.portfolios import get_portfolio
from app.services.valuation import get_portfolio_valuation

# PortfolioPilot is an Indian-equity app: a "day" for snapshot purposes
# is a calendar date in this market timezone, not UTC or the caller's.
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _market_snapshot_date(now: datetime) -> datetime:
    market_date = now.astimezone(MARKET_TIMEZONE).date()
    return datetime.combine(market_date, time.min, tzinfo=MARKET_TIMEZONE)


def create_portfolio_snapshot(db: Session, user_id: UUID, portfolio_id: UUID) -> PortfolioSnapshot:
    portfolio = get_portfolio(db, user_id, portfolio_id)

    # snapshot_date acts as a daily key for the portfolio, one per
    # calendar day in Asia/Kolkata (e.g. 17 Sep 01:00 IST -> 2026-09-17,
    # even though that instant is still 16 Sep in UTC).
    snapshot_date = _market_snapshot_date(datetime.now(MARKET_TIMEZONE))

    existing = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A snapshot already exists for this portfolio today",
        )

    valuation = get_portfolio_valuation(db, user_id, portfolio_id)

    previous = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == portfolio_id)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .first()
    )

    daily_return = None
    if previous is not None and previous.total_value != 0:
        daily_return = (valuation.total_value - previous.total_value) / previous.total_value

    cumulative_return = None
    if portfolio.initial_capital != 0:
        cumulative_return = (
            valuation.total_value - portfolio.initial_capital
        ) / portfolio.initial_capital

    snapshot = PortfolioSnapshot(
        portfolio_id=portfolio_id,
        snapshot_date=snapshot_date,
        total_value=valuation.total_value,
        cash_balance=valuation.cash_balance,
        invested_value=valuation.invested_value,
        daily_return=daily_return,
        cumulative_return=cumulative_return,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
