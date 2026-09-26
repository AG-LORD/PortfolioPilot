import math
import re
import statistics
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecommendationSnapshot
from app.schemas.stock_analysis import StockAnalysisRead, StockPricePointRead
from app.services import market_data, price_history
from app.services.drift import get_portfolio_drift
from app.services.features import FEATURE_COLUMNS, compute_features, prices_to_frame
from app.services.market_data import MarketDataUnavailableError
from app.services.portfolios import get_portfolio

_TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]{0,19}$")
HISTORY_CALENDAR_DAYS = 3 * 365
DISPLAY_HISTORY_ROWS = 252


def _normalize_ticker(raw_ticker: str) -> str:
    ticker = raw_ticker.strip().upper()
    if ticker.endswith(".NS"):
        ticker = ticker[:-3]
    if not _TICKER_PATTERN.fullmatch(ticker):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker must be a valid NSE symbol",
        )
    return ticker


def _period_return(closes: list[Decimal], observations: int) -> Decimal | None:
    if len(closes) <= observations:
        return None
    return closes[-1] / closes[-observations - 1] - Decimal("1")


def _annualized_volatility(closes: list[Decimal]) -> Decimal | None:
    daily_returns = [right / left - Decimal("1") for left, right in zip(closes, closes[1:])]
    if len(daily_returns) < 2:
        return None
    daily_values = [float(value) for value in daily_returns[-252:]]
    return Decimal(str(statistics.stdev(daily_values) * math.sqrt(252)))


def get_stock_analysis(
    db: Session,
    user_id: UUID,
    ticker: str,
    *,
    portfolio_id: UUID | None = None,
    recommendation_id: UUID | None = None,
) -> StockAnalysisRead:
    normalized_ticker = _normalize_ticker(ticker)
    if recommendation_id is not None and portfolio_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="portfolio_id is required with recommendation_id",
        )

    selected_portfolio_id = None
    selected_target = None
    if portfolio_id is not None:
        portfolio = get_portfolio(db, user_id, portfolio_id)
        selected_portfolio_id = portfolio.id
        if recommendation_id is None:
            selected_target = db.scalars(
                select(RecommendationSnapshot)
                .where(RecommendationSnapshot.portfolio_id == portfolio_id)
                .order_by(RecommendationSnapshot.created_at.desc())
                .limit(1)
            ).first()
        else:
            selected_target = db.get(RecommendationSnapshot, recommendation_id)
            if selected_target is None or selected_target.portfolio_id != portfolio_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")

    start = date.today() - timedelta(days=HISTORY_CALENDAR_DAYS)
    end = date.today() + timedelta(days=1)
    history = price_history.get_price_history(db, [normalized_ticker], start, end)
    points = history.points.get(normalized_ticker, [])
    if not points:
        reason = history.errors.get(normalized_ticker)
        raise MarketDataUnavailableError(
            normalized_ticker,
            reason.reason if reason else "no adjusted price history is available",
        )

    indicators_frame = compute_features(prices_to_frame(points))
    if indicators_frame.empty:
        technical_indicators = {}
    else:
        latest_features = indicators_frame.iloc[-1]
        technical_indicators = {
            name: Decimal(str(float(latest_features[name])))
            for name in FEATURE_COLUMNS
            if math.isfinite(float(latest_features[name]))
        }

    try:
        current_price = market_data.get_current_price(normalized_ticker)
    except MarketDataUnavailableError:
        current_price = None

    closes = [point.close for point in points]
    latest = points[-1]
    current_weight = None
    target_weight = None
    expected_return = None
    expected_return_source = None
    model_version = None
    if portfolio_id is not None:
        drift = get_portfolio_drift(db, user_id, portfolio_id)
        current_position = next(
            (position for position in drift.positions if position.ticker == normalized_ticker),
            None,
        )
        current_weight = current_position.current_weight if current_position else Decimal("0")

        if selected_target is not None:
            allocation = next(
                (item for item in selected_target.allocations if item["ticker"] == normalized_ticker),
                None,
            )
            if allocation is not None:
                expected_return = Decimal(str(allocation["expected_return"]))
                expected_return_source = allocation["source"]
                target_weight = Decimal(str(allocation["target_weight"]))
                model_version = selected_target.model_version

    return StockAnalysisRead(
        ticker=normalized_ticker,
        current_price=current_price,
        current_quote_available=current_price is not None,
        latest_close=latest.close,
        latest_close_date=latest.date,
        historical_prices=[
            StockPricePointRead(
                date=point.date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
            )
            for point in points[-DISPLAY_HISTORY_ROWS:]
        ],
        technical_indicators=technical_indicators,
        return_20d=_period_return(closes, 20),
        return_60d=_period_return(closes, 60),
        return_252d=_period_return(closes, 252),
        annualized_volatility_252d=_annualized_volatility(closes),
        portfolio_id=selected_portfolio_id,
        recommendation_id=selected_target.id if selected_target else None,
        expected_return_annual=expected_return,
        expected_return_source=expected_return_source,
        model_version=model_version,
        target_weight=target_weight,
        current_weight=current_weight,
    )