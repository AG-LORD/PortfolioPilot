from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class StockPricePointRead(BaseModel):
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class StockAnalysisRead(BaseModel):
    ticker: str
    current_price: Decimal | None
    current_quote_available: bool
    latest_close: Decimal
    latest_close_date: date
    historical_prices: list[StockPricePointRead]
    technical_indicators: dict[str, Decimal]
    return_20d: Decimal | None
    return_60d: Decimal | None
    return_252d: Decimal | None
    annualized_volatility_252d: Decimal | None
    portfolio_id: UUID | None
    recommendation_id: UUID | None
    expected_return_annual: Decimal | None
    expected_return_source: Literal["historical", "ml"] | None
    model_version: str | None
    target_weight: Decimal | None
    current_weight: Decimal | None