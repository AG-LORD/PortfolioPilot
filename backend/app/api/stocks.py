import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.schemas.stock_analysis import StockAnalysisRead
from app.services.market_data import MarketDataUnavailableError
from app.services.stock_analysis import get_stock_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/{ticker}/analysis", response_model=StockAnalysisRead)
def read_stock_analysis(
    ticker: str,
    portfolio_id: UUID | None = Query(default=None),
    recommendation_id: UUID | None = Query(default=None),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        return get_stock_analysis(
            db,
            user_id,
            ticker,
            portfolio_id=portfolio_id,
            recommendation_id=recommendation_id,
        )
    except MarketDataUnavailableError as exc:
        logger.warning("Stock analysis history unavailable for %s: %s", ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adjusted stock history is currently unavailable.",
        ) from exc