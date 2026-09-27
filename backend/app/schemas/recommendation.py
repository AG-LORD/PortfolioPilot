from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

ResponseReturnModel = Literal["historical", "ml"]
# negative_estimate: expected_return <= 0; sector_limit: its sector's cap is
# binding; risk_tradeoff: adds more risk than return for the profile's risk
# aversion. risk_limit only appears on snapshots saved before the
# mean-variance optimizer (it meant "positive estimate, left out").
NotSelectedReason = Literal["negative_estimate", "sector_limit", "risk_tradeoff", "risk_limit"]
# Why a selected stock did not get more weight; null when no limit is binding.
LimitReason = Literal["position_limit", "sector_limit"]
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
    # Display label from app/data/sectors.json; null when unknown.
    sector: str | None = None
    # The shrunk estimate the optimizer used (expected_return is the model's own
    # estimate); null on snapshots saved before shrinkage.
    expected_return_used: Decimal | None = None
    limit_reason: LimitReason | None = None


class NotSelectedItem(BaseModel):
    """An eligible ticker (usable estimate) that the optimizer gave zero weight."""

    ticker: str
    sector: str | None = None
    expected_return: Decimal
    source: ResponseReturnModel
    reason: NotSelectedReason
    expected_return_used: Decimal | None = None


class ExcludedTickerItem(BaseModel):
    ticker: str
    reason: str


class RecommendationConstraintsRead(BaseModel):
    max_position_weight: Decimal
    target_volatility: Decimal
    # The profile's sector cap (enforced by the optimizer); null if unknown.
    max_sector_weight: Decimal | None = None


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
    # Null for snapshots saved before this field existed (unknown), [] when none were left out.
    not_selected: list[NotSelectedItem] | None = None

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
