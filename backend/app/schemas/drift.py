from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


DriftPositionStatus = Literal[
    "no_target",
    "unavailable",
    "overweight",
    "underweight",
    "at_target",
]
DriftTargetStatus = Literal["missing", "current", "stale"]


class DriftPositionRead(BaseModel):
    ticker: str
    quantity: Decimal | None
    current_price: Decimal | None
    current_value: Decimal | None
    current_weight: Decimal | None
    target_weight: Decimal | None
    weight_difference: Decimal | None
    status: DriftPositionStatus
    excluded: bool
    exclusion_reason: str | None
    requires_attention: bool


class PortfolioDriftRead(BaseModel):
    portfolio_id: UUID
    portfolio_value: Decimal | None
    valuation_complete: bool
    missing_prices: list[str]
    target_recommendation_id: UUID | None
    target_created_at: datetime | None
    target_status: DriftTargetStatus
    drift_threshold: Decimal
    attention_count: int
    positions: list[DriftPositionRead]