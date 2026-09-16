from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class HoldingRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
