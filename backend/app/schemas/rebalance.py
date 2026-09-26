from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RebalanceProposalRequest(BaseModel):
    recommendation_id: UUID | None = None


class RebalanceExecutionRequest(BaseModel):
    confirm: Literal[True]


class RebalanceTradeRead(BaseModel):
    ticker: str
    side: Literal["BUY", "SELL"]
    quantity: int
    estimated_price: Decimal
    estimated_gross_amount: Decimal
    estimated_fee: Decimal
    estimated_net_amount: Decimal
    current_weight: Decimal
    target_weight: Decimal
    resulting_weight: Decimal


class RebalanceWeightRead(BaseModel):
    ticker: str
    current_weight: Decimal
    target_weight: Decimal
    resulting_weight: Decimal


class RebalanceProposalRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    recommendation_id: UUID
    created_at: datetime
    status: Literal["PENDING", "EXECUTED", "EXPIRED"]
    portfolio_value: Decimal
    cash_before: Decimal
    projected_cash: Decimal
    buy_total: Decimal
    sell_total: Decimal
    estimated_fees: Decimal
    fee_assumption: str
    trades: list[RebalanceTradeRead]
    resulting_weights: list[RebalanceWeightRead]


class RebalanceExecutionRead(BaseModel):
    proposal_id: UUID
    status: Literal["EXECUTED"]
    transaction_ids: list[UUID]
    cash_balance: Decimal