from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.recommendation import RecommendationSummary


class OverviewTotals(BaseModel):
    portfolio_count: int
    initial_capital: Decimal
    cash_balance: Decimal
    market_value: Decimal | None
    total_value: Decimal | None
    unrealized_pnl: Decimal | None
    # Portfolios included in market_value / total_value / unrealized_pnl.
    valued_portfolio_count: int = 0


class PortfolioOverviewItem(BaseModel):
    id: UUID
    name: str
    risk_category: str
    initial_capital: Decimal
    cash_balance: Decimal
    valuation_status: Literal["ok", "unavailable"]
    market_value: Decimal | None
    total_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_pct: Decimal | None
    holdings_count: int
    latest_recommendation: RecommendationSummary | None
    # initial_capital plus every later deposit (net of fees).
    total_deposited: Decimal | None = None
    # Last change to cash or holdings.
    updated_at: datetime | None = None
    adopted_recommendation_id: UUID | None = None
    adopted_at: datetime | None = None
    # total_value of the last 30 daily snapshots, oldest first; empty if fewer than 2.
    sparkline: list[Decimal] = []


class PortfolioOverviewRead(BaseModel):
    totals: OverviewTotals
    portfolios: list[PortfolioOverviewItem]
