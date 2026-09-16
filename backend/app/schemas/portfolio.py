from decimal import Decimal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    name: str = Field(max_length=100)
    purpose: str | None = Field(default=None, max_length=255)
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    risk_profile_id: UUID
    initial_capital: Decimal = Field(gt=0)


class PortfolioRead(BaseModel):
    id: UUID
    user_id: UUID
    risk_profile_id: UUID
    name: str
    purpose: str | None
    base_currency: str
    initial_capital: Decimal
    cash_balance: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
