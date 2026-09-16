from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.schemas.holding import HoldingRead
from app.schemas.portfolio import PortfolioCreate, PortfolioRead
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.services.portfolios import (
    create_portfolio,
    get_portfolio,
    list_holdings,
    list_portfolios,
)
from app.services.transactions import execute_transaction, list_transactions

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.post("", response_model=PortfolioRead)
def create_own_portfolio(
    data: PortfolioCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return create_portfolio(db, user_id, data)


@router.get("", response_model=list[PortfolioRead])
def read_own_portfolios(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return list_portfolios(db, user_id)


@router.get("/{portfolio_id}", response_model=PortfolioRead)
def read_own_portfolio(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return get_portfolio(db, user_id, portfolio_id)


@router.post("/{portfolio_id}/transactions", response_model=TransactionRead)
def create_transaction(
    portfolio_id: UUID,
    data: TransactionCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return execute_transaction(db, user_id, portfolio_id, data)


@router.get("/{portfolio_id}/holdings", response_model=list[HoldingRead])
def read_portfolio_holdings(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return list_holdings(db, user_id, portfolio_id)


@router.get("/{portfolio_id}/transactions", response_model=list[TransactionRead])
def read_portfolio_transactions(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return list_transactions(db, user_id, portfolio_id)
