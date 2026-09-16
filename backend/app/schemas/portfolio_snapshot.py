from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PortfolioSnapshotRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    snapshot_date: datetime
    total_value: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    daily_return: Decimal | None
    cumulative_return: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}
