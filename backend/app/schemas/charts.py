from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class HistoryPreviewPoint(BaseModel):
    date: date
    mix: Decimal
    benchmark: Decimal


class HistoryPreviewRead(BaseModel):
    start: date
    end: date
    points: list[HistoryPreviewPoint]
    # Says this is hindsight context with today's weights, not a backtest or forecast.
    note: str


class PerformancePointRead(BaseModel):
    date: date
    portfolio: Decimal
    # NIFTY 50 scaled to the first snapshot's value; null before any close exists.
    benchmark: Decimal | None


class PortfolioPerformanceRead(BaseModel):
    # Empty with fewer than 2 daily snapshots.
    points: list[PerformancePointRead]
