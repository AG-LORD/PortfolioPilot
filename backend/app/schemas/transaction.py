from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    ticker: str = Field(max_length=20)
    transaction_type: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    occurred_at: datetime | None = None


class TransactionRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    ticker: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    occurred_at: datetime
    created_at: datetime
    source: str

    model_config = {"from_attributes": True}
