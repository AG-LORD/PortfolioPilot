from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator


class RecommendationRequest(BaseModel):
    universe: str | None = None
    tickers: list[str] | None = None
    return_model: Literal["historical"] = "historical"

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if (self.universe is None) == (self.tickers is None):
            raise ValueError("Provide exactly one of 'universe' or 'tickers'.")
        return self


class RecommendedAllocationItem(BaseModel):
    ticker: str
    expected_return: Decimal
    target_weight: Decimal
    amount: Decimal


class ExcludedTickerItem(BaseModel):
    ticker: str
    reason: str


class RecommendationConstraintsRead(BaseModel):
    max_position_weight: Decimal
    target_volatility: Decimal


class RecommendationRead(BaseModel):
    portfolio_id: UUID
    universe: str
    universe_as_of: date | None
    return_model: str
    capital: Decimal
    allocations: list[RecommendedAllocationItem]
    cash_weight: Decimal
    cash_amount: Decimal
    expected_portfolio_return: Decimal
    expected_portfolio_volatility: Decimal
    constraints: RecommendationConstraintsRead
    excluded: list[ExcludedTickerItem]
