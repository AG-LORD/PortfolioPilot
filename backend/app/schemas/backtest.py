from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BacktestRequest(BaseModel):
    start: date
    end: date
    rebalance_frequency: Literal["daily", "weekly", "monthly"] = "monthly"
    starting_capital: Decimal = Field(gt=0)
    universe: str | None = None
    tickers: list[str] | None = None
    return_model: Literal["historical", "ml"] = "historical"
    max_position_weight: Decimal = Field(default=Decimal("0.1"), gt=0, le=1)
    target_volatility: Decimal = Field(default=Decimal("0.15"), gt=0)

    @model_validator(mode="after")
    def validate_period_and_universe(self):
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        if (self.universe is None) == (self.tickers is None):
            raise ValueError("Provide exactly one of universe or tickers")
        return self


class BacktestEquityPointRead(BaseModel):
    date: date
    total_value: Decimal


class BacktestStrategyRead(BaseModel):
    model: str
    model_version: str
    cumulative_return: Decimal
    annualized_return: Decimal | None
    annualized_volatility: Decimal | None
    max_drawdown: Decimal
    sharpe_ratio: Decimal | None
    turnover: Decimal
    rebalance_count: int
    daily_observation_count: int
    equity_curve: list[BacktestEquityPointRead]


class BacktestSettingsRead(BaseModel):
    start: date
    end: date
    rebalance_frequency: Literal["daily", "weekly", "monthly"]
    starting_capital: Decimal
    return_model: Literal["historical", "ml"]
    max_position_weight: Decimal
    target_volatility: Decimal
    universe: str
    universe_as_of: date | None
    universe_revision: str
    price_source: str


class BacktestResultRead(BaseModel):
    settings: BacktestSettingsRead
    selected_strategy: str
    feature_version: str
    evaluation_version: str
    daily_risk_free_rate_assumption: Decimal
    fee_assumption: str
    execution_assumption: str
    scored_rows: int
    effective_start: date
    effective_end: date
    excluded: list[dict[str, str]]
    strategies: list[BacktestStrategyRead]