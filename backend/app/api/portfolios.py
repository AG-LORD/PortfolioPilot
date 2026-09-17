import logging
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.schemas.holding import HoldingRead
from app.schemas.optimization import TargetAllocationItem, TargetAllocationRead
from app.schemas.portfolio import PortfolioCreate, PortfolioRead
from app.schemas.portfolio_snapshot import PortfolioSnapshotRead
from app.schemas.risk_analytics import RiskAnalyticsRead
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.schemas.valuation import PortfolioValuation
from app.services.expected_returns import InsufficientHistoryError
from app.services.market_data import MarketDataUnavailableError
from app.services.optimization import OptimizationError, get_portfolio_target_allocation
from app.services.portfolios import (
    create_portfolio,
    get_portfolio,
    list_holdings,
    list_portfolios,
)
from app.services.risk_analytics import (
    DEFAULT_RISK_FREE_RATE_ANNUAL,
    DEFAULT_VAR_CONFIDENCE,
    get_portfolio_risk_analytics,
)
from app.services.snapshots import create_portfolio_snapshot
from app.services.transactions import execute_transaction, list_transactions
from app.services.valuation import get_portfolio_valuation

logger = logging.getLogger(__name__)

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


@router.get("/{portfolio_id}/valuation", response_model=PortfolioValuation)
def read_portfolio_valuation(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return get_portfolio_valuation(db, user_id, portfolio_id)
    except MarketDataUnavailableError as exc:
        logger.warning("Valuation failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market data is currently unavailable. Please try again later.",
        )


@router.get("/{portfolio_id}/risk", response_model=RiskAnalyticsRead)
def read_portfolio_risk(
    portfolio_id: UUID,
    risk_free_rate_annual: Decimal = DEFAULT_RISK_FREE_RATE_ANNUAL,
    var_confidence: Decimal = Query(
        default=DEFAULT_VAR_CONFIDENCE,
        gt=Decimal("0"),
        lt=Decimal("1"),
        description="Confidence level for Historical VaR and CVaR (strictly between 0 and 1).",
    ),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        result = get_portfolio_risk_analytics(
            db,
            user_id,
            portfolio_id,
            risk_free_rate_annual=risk_free_rate_annual,
            var_confidence=var_confidence,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
    return RiskAnalyticsRead(portfolio_id=portfolio_id, **asdict(result))


@router.get("/{portfolio_id}/optimize", response_model=TargetAllocationRead)
def read_portfolio_target_allocation(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        weights = get_portfolio_target_allocation(db, user_id, portfolio_id)
    except MarketDataUnavailableError as exc:
        logger.warning("Optimization market data failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market data is currently unavailable. Please try again later.",
        )
    except (InsufficientHistoryError, OptimizationError) as exc:
        logger.warning("Optimization failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    return TargetAllocationRead(
        portfolio_id=portfolio_id,
        allocations=[
            TargetAllocationItem(
                ticker=w.ticker,
                target_weight=w.target_weight,
                expected_return=w.expected_return,
            )
            for w in weights
            for w in weights.allocations
        ],
        cash_weight=weights.cash_weight,
    )


@router.post("/{portfolio_id}/snapshots", response_model=PortfolioSnapshotRead)
def create_snapshot(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return create_portfolio_snapshot(db, user_id, portfolio_id)
    except MarketDataUnavailableError as exc:
        logger.warning("Snapshot failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market data is currently unavailable. Please try again later.",
        )
