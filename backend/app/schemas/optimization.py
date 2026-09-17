from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class TargetAllocationItem(BaseModel):
    ticker: str
    target_weight: Decimal
    expected_return: Decimal


class TargetAllocationRead(BaseModel):
    portfolio_id: UUID
    allocations: list[TargetAllocationItem]
