from decimal import Decimal
from typing import Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class RiskProfileCreate(BaseModel):
    score: Decimal = Field(ge=0, le=100)
    category: Literal["conservative", "moderate", "aggressive"]
    max_position_weight: Decimal = Field(gt=0, le=1)
    max_sector_weight: Decimal = Field(gt=0, le=1)
    drift_threshold: Decimal = Field(gt=0, le=1)
    target_volatility: Decimal = Field(gt=0)


class RiskProfileRead(RiskProfileCreate):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
