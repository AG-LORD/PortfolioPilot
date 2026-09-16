from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Portfolio, RiskProfile, Holding
from app.schemas.portfolio import PortfolioCreate


def create_portfolio(db: Session, user_id: UUID, data: PortfolioCreate) -> Portfolio:
    risk_profile = db.get(RiskProfile, data.risk_profile_id)
    if risk_profile is None or risk_profile.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk profile not found",
        )

    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=data.risk_profile_id,
        name=data.name,
        purpose=data.purpose,
        base_currency=data.base_currency,
        initial_capital=data.initial_capital,
        cash_balance=data.initial_capital,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio

def list_portfolios(db: Session, user_id: UUID) -> list[Portfolio]:
    return db.query(Portfolio).filter(Portfolio.user_id == user_id).all()


def get_portfolio(db: Session, user_id: UUID, portfolio_id: UUID) -> Portfolio:
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )
    return portfolio

def list_holdings(db: Session, user_id: UUID, portfolio_id: UUID) -> list[Holding]:
    get_portfolio(db, user_id, portfolio_id)
    return db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()
