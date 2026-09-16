from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class HoldingValuation(BaseModel):
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class PortfolioValuation(BaseModel):
    portfolio_id: UUID
    cash_balance: Decimal
    invested_value: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    holdings: list[HoldingValuation]
