from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class RiskAnalyticsRead(BaseModel):
    portfolio_id: UUID
    observation_count: int
    first_snapshot_date: date | None
    last_snapshot_date: date | None
    cumulative_return: Decimal | None
    annualized_volatility: Decimal | None
    max_drawdown: Decimal | None
    sharpe_ratio: Decimal | None
    risk_free_rate_annual: Decimal
    message: str | None
