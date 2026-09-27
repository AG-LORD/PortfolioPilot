from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TransactionCreate(BaseModel):
    ticker: str = Field(max_length=20)
    transaction_type: Literal["BUY", "SELL", "DEPOSIT"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class BatchTradeItem(BaseModel):
    side: Literal["BUY", "SELL"]
    ticker: str = Field(max_length=20)
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)


# 1 to 50 trades recorded atomically.
BatchTradeRequest = Annotated[list[BatchTradeItem], Field(min_length=1, max_length=50)]


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
