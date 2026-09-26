import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.ml.evaluation import EvaluationError
from app.schemas.backtest import BacktestRequest, BacktestResultRead
from app.services.backtesting import BacktestError, run_portfolio_backtest
from app.services.expected_returns import InsufficientHistoryError
from app.services.market_data import MarketDataUnavailableError
from app.services.optimization import OptimizationError
from app.services.universe import UniverseError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestResultRead)
def create_backtest(
    data: BacktestRequest,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return run_portfolio_backtest(db, data)
    except (UniverseError, BacktestError, InsufficientHistoryError, OptimizationError, EvaluationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except MarketDataUnavailableError as exc:
        logger.warning("Backtest market data unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adjusted market history is currently unavailable for this backtest.",
        ) from exc