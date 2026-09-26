import logging
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.schemas.holding import HoldingRead
from app.schemas.drift import PortfolioDriftRead
from app.schemas.optimization import TargetAllocationItem, TargetAllocationRead
from app.schemas.overview import PortfolioOverviewRead
from app.schemas.portfolio import PortfolioCapitalAddRequest, PortfolioCreate, PortfolioRead
from app.schemas.portfolio_snapshot import PortfolioSnapshotRead
from app.schemas.rebalance import (
    RebalanceExecutionRead,
    RebalanceExecutionRequest,
    RebalanceProposalRead,
    RebalanceProposalRequest,
)
from app.schemas.recommendation import (
    RecommendationRead,
    RecommendationRequest,
    RecommendationSummary,
)
from app.schemas.risk_analytics import RiskAnalyticsRead
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.schemas.valuation import PortfolioValuation
from app.services.expected_returns import InsufficientHistoryError
from app.services.drift import get_portfolio_drift
from app.services.market_data import MarketDataUnavailableError
from app.services.optimization import OptimizationError, get_portfolio_target_allocation
from app.services.overview import get_portfolio_overview
from app.services.portfolios import (
    add_capital,
    create_portfolio,
    get_portfolio,
    list_holdings,
    list_portfolios,
)
from app.services.recommendation import (
    get_portfolio_recommendation,
    get_recommendation_snapshot,
    list_recommendation_snapshots,
    persist_recommendation_snapshot,
)
from app.services.risk_analytics import (
    DEFAULT_RISK_FREE_RATE_ANNUAL,
    DEFAULT_VAR_CONFIDENCE,
    get_portfolio_risk_analytics,
)
from app.services.rebalancing import create_rebalance_proposal, get_rebalance_proposal
from app.services.rebalance_execution import RebalanceExecutionConflict, execute_rebalance_proposal
from app.services.snapshots import create_portfolio_snapshot
from app.services.transactions import execute_transaction, list_transactions
from app.services.universe import UniverseError
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


# Declared before /{portfolio_id} so "overview" is not parsed as a portfolio id.
@router.get("/overview", response_model=PortfolioOverviewRead)
def read_portfolios_overview(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return get_portfolio_overview(db, user_id)


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


@router.get("/{portfolio_id}/drift", response_model=PortfolioDriftRead)
def read_portfolio_drift(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return get_portfolio_drift(db, user_id, portfolio_id)


@router.post(
    "/{portfolio_id}/rebalance-proposals",
    response_model=RebalanceProposalRead,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio_rebalance_proposal(
    portfolio_id: UUID,
    data: RebalanceProposalRequest = RebalanceProposalRequest(),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return create_rebalance_proposal(db, user_id, portfolio_id, data.recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MarketDataUnavailableError as exc:
        logger.warning("Rebalance pricing failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market prices are unavailable for a rebalancing proposal.",
        ) from exc


@router.get(
    "/{portfolio_id}/rebalance-proposals/{proposal_id}",
    response_model=RebalanceProposalRead,
)
def read_portfolio_rebalance_proposal(
    portfolio_id: UUID,
    proposal_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return get_rebalance_proposal(db, user_id, portfolio_id, proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{portfolio_id}/rebalance-proposals/{proposal_id}/execute",
    response_model=RebalanceExecutionRead,
)
def execute_portfolio_rebalance(
    portfolio_id: UUID,
    proposal_id: UUID,
    data: RebalanceExecutionRequest,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if data.confirm is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Explicit confirmation is required")
    try:
        return execute_rebalance_proposal(db, user_id, portfolio_id, proposal_id)
    except RebalanceExecutionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MarketDataUnavailableError as exc:
        logger.warning("Rebalance execution pricing failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market prices are unavailable; no rebalance trades were executed.",
        ) from exc


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
            for w in weights.allocations
        ],
        cash_weight=weights.cash_weight,
    )


@router.post("/{portfolio_id}/recommendation", response_model=RecommendationRead)
def create_portfolio_recommendation(
    portfolio_id: UUID,
    data: RecommendationRequest,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        recommendation = get_portfolio_recommendation(
            db,
            user_id,
            portfolio_id,
            universe=data.universe,
            tickers=data.tickers,
            return_model=data.return_model,
        )
    except (UniverseError, InsufficientHistoryError, OptimizationError) as exc:
        logger.warning("Recommendation failed for portfolio %s: %s", portfolio_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    snapshot = persist_recommendation_snapshot(db, portfolio_id, recommendation)
    recommendation.id = snapshot.id
    recommendation.created_at = snapshot.created_at
    return RecommendationRead(portfolio_id=portfolio_id, **asdict(recommendation))


@router.get("/{portfolio_id}/recommendations", response_model=list[RecommendationSummary])
def read_portfolio_recommendations(
    portfolio_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    get_portfolio(db, user_id, portfolio_id)
    return [
        RecommendationSummary(
            id=s.id,
            created_at=s.created_at,
            universe=s.universe,
            return_model=s.return_model,
            model_version=s.model_version,
            capital=s.capital,
            cash_weight=s.cash_weight,
            expected_portfolio_return=s.expected_portfolio_return,
            expected_portfolio_volatility=s.expected_portfolio_volatility,
        )
        for s in list_recommendation_snapshots(db, user_id, portfolio_id)
    ]


@router.get(
    "/{portfolio_id}/recommendations/{recommendation_id}", response_model=RecommendationRead
)
def read_portfolio_recommendation(
    portfolio_id: UUID,
    recommendation_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        snapshot = get_recommendation_snapshot(db, user_id, portfolio_id, recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return RecommendationRead(
        id=snapshot.id,
        created_at=snapshot.created_at,
        portfolio_id=snapshot.portfolio_id,
        universe=snapshot.universe,
        universe_as_of=snapshot.universe_as_of,
        return_model=snapshot.return_model,
        model_version=snapshot.model_version,
        forecast_as_of=snapshot.forecast_as_of,
        capital=snapshot.capital,
        allocations=[
            {"ticker": item["ticker"], "expected_return": Decimal(str(item["expected_return"])), "target_weight": Decimal(str(item["target_weight"])), "amount": Decimal(str(item["amount"])), "at_position_limit": item["at_position_limit"], "source": item["source"]}
            for item in snapshot.allocations
        ],
        cash_weight=snapshot.cash_weight,
        cash_amount=snapshot.cash_amount,
        expected_portfolio_return=snapshot.expected_portfolio_return,
        expected_portfolio_volatility=snapshot.expected_portfolio_volatility,
        constraints={
            "max_position_weight": snapshot.max_position_weight,
            "target_volatility": snapshot.target_volatility,
        },
        excluded=[{"ticker": item["ticker"], "reason": item["reason"]} for item in snapshot.excluded],
    )


@router.post("/{portfolio_id}/capital", response_model=PortfolioRead)
def add_portfolio_capital(
    portfolio_id: UUID,
    data: PortfolioCapitalAddRequest,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return add_capital(db, user_id, portfolio_id, data.amount)


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
