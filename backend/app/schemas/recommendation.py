from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

ResponseReturnModel = Literal["historical", "ml"]
ForecastSource = Literal["precomputed", "on_request"]


class RecommendationRequest(BaseModel):
    universe: str | None = None
    tickers: list[str] | None = None
    return_model: Literal["historical", "ml"] = "historical"

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if (self.universe is None) == (self.tickers is None):
            raise ValueError("Provide exactly one of 'universe' or 'tickers'.")
        return self


class AllocationDriverItem(BaseModel):
    feature: str
    value: Decimal
    # Annualized change in the estimate when this feature is replaced by its
    # training median (local ablation; approximate, explains the model only).
    contribution: Decimal


class RecommendedAllocationItem(BaseModel):
    ticker: str
    expected_return: Decimal
    target_weight: Decimal
    amount: Decimal
    at_position_limit: bool
    # Provider of this ticker's expected_return; "historical" in ml mode means
    # this ticker fell back because it had no usable ML forecast.
    source: ResponseReturnModel
    # ML forecast capped to the model's training-label range.
    clipped: bool = False
    # ML-sourced tickers only; empty / null for historical fallbacks.
    drivers: list[AllocationDriverItem] = []
    typical_estimate: Decimal | None = None


class ExcludedTickerItem(BaseModel):
    ticker: str
    reason: str


class RecommendationConstraintsRead(BaseModel):
    max_position_weight: Decimal
    target_volatility: Decimal


class RecommendationRead(BaseModel):
    id: UUID | None = None
    created_at: datetime | None = None
    portfolio_id: UUID
    universe: str
    universe_as_of: date | None
    return_model: ResponseReturnModel
    model_version: str | None = None
    forecast_as_of: date | None = None
    # Nightly stored forecasts vs. a model fitted on request; null when historical only.
    forecast_source: ForecastSource | None = None
    capital: Decimal
    allocations: list[RecommendedAllocationItem]
    cash_weight: Decimal
    cash_amount: Decimal
    expected_portfolio_return: Decimal
    expected_portfolio_volatility: Decimal
    constraints: RecommendationConstraintsRead
    excluded: list[ExcludedTickerItem]

    model_config = {"from_attributes": True}


class RecommendationSummary(BaseModel):
    id: UUID
    created_at: datetime
    universe: str
    return_model: ResponseReturnModel
    model_version: str | None
    capital: Decimal
    cash_weight: Decimal
    expected_portfolio_return: Decimal
    expected_portfolio_volatility: Decimal

    model_config = {"from_attributes": True}
