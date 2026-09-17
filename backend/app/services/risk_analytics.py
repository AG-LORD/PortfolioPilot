"""Pure portfolio risk analytics, computed from a snapshot value series.

MVP conventions, not claims of precision:
- ANNUALIZATION_FACTOR=252 is a standard convention, not an NSE-specific
  trading-day count (no exchange trading calendar exists in this app).
- DEFAULT_RISK_FREE_RATE_ANNUAL=0 is an MVP default, not a claim that the
  real Indian risk-free rate is zero.
- Volatility/Sharpe assume roughly-daily snapshot spacing. Snapshots are
  manually triggered, so irregular gaps between them are treated as single
  return observations anyway (no gap-weighting) — an approximation, kept
  auditable via first_snapshot_date/last_snapshot_date in the result.
"""

import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.portfolios import get_portfolio
from app.services.snapshots import MARKET_TIMEZONE, list_snapshots

ANNUALIZATION_FACTOR = 252
DEFAULT_RISK_FREE_RATE_ANNUAL = Decimal("0")


@dataclass
class SnapshotPoint:
    date: date
    total_value: Decimal


@dataclass
class RiskAnalyticsResult:
    observation_count: int
    first_snapshot_date: date | None
    last_snapshot_date: date | None
    cumulative_return: Decimal | None
    annualized_volatility: Decimal | None
    max_drawdown: Decimal | None
    sharpe_ratio: Decimal | None
    risk_free_rate_annual: Decimal
    message: str | None


def calculate_daily_returns(points: list[SnapshotPoint]) -> list[Decimal]:
    """Simple returns between consecutive points; skips a pair if the prior value is 0."""
    returns = []
    for prev, curr in zip(points, points[1:]):
        if prev.total_value == 0:
            continue
        returns.append((curr.total_value - prev.total_value) / prev.total_value)
    return returns


def calculate_cumulative_return(points: list[SnapshotPoint], initial_capital: Decimal) -> Decimal | None:
    if not points or initial_capital == 0:
        return None
    return (points[-1].total_value - initial_capital) / initial_capital


def calculate_max_drawdown(points: list[SnapshotPoint]) -> Decimal | None:
    if not points:
        return None
    peak = points[0].total_value
    max_dd = Decimal("0")
    for point in points:
        if point.total_value > peak:
            peak = point.total_value
        if peak == 0:
            continue
        drawdown = (point.total_value - peak) / peak
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd


def calculate_volatility(returns: list[Decimal]) -> Decimal | None:
    if len(returns) < 2:
        return None
    daily_std = statistics.stdev(returns)
    return daily_std * Decimal(ANNUALIZATION_FACTOR).sqrt()


def calculate_sharpe_ratio(returns: list[Decimal], risk_free_rate_annual: Decimal) -> Decimal | None:
    if len(returns) < 2:
        return None
    daily_rf = risk_free_rate_annual / Decimal(ANNUALIZATION_FACTOR)
    excess_returns = [r - daily_rf for r in returns]
    std = statistics.stdev(excess_returns)
    if std == 0:
        return None
    mean_excess = statistics.mean(excess_returns)
    return (mean_excess / std) * Decimal(ANNUALIZATION_FACTOR).sqrt()


def calculate_risk_analytics(
    points: list[SnapshotPoint],
    initial_capital: Decimal,
    risk_free_rate_annual: Decimal = DEFAULT_RISK_FREE_RATE_ANNUAL,
) -> RiskAnalyticsResult:
    if not points:
        return RiskAnalyticsResult(
            observation_count=0,
            first_snapshot_date=None,
            last_snapshot_date=None,
            cumulative_return=None,
            annualized_volatility=None,
            max_drawdown=None,
            sharpe_ratio=None,
            risk_free_rate_annual=risk_free_rate_annual,
            message="No snapshot history exists for this portfolio yet.",
        )

    returns = calculate_daily_returns(points)

    message = None
    if len(returns) < 2:
        message = (
            f"Only {len(points)} snapshot(s) available ({len(returns)} usable return "
            "observation(s)); at least 3 snapshots with 2 usable returns are needed "
            "for volatility and Sharpe ratio."
        )

    return RiskAnalyticsResult(
        observation_count=len(returns),
        first_snapshot_date=points[0].date,
        last_snapshot_date=points[-1].date,
        cumulative_return=calculate_cumulative_return(points, initial_capital),
        annualized_volatility=calculate_volatility(returns),
        max_drawdown=calculate_max_drawdown(points),
        sharpe_ratio=calculate_sharpe_ratio(returns, risk_free_rate_annual),
        risk_free_rate_annual=risk_free_rate_annual,
        message=message,
    )


def get_portfolio_risk_analytics(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    risk_free_rate_annual: Decimal = DEFAULT_RISK_FREE_RATE_ANNUAL,
) -> RiskAnalyticsResult:
    portfolio = get_portfolio(db, user_id, portfolio_id)
    snapshots = list_snapshots(db, user_id, portfolio_id)

    # snapshot_date is read back from the DB with whatever tzinfo the driver
    # returns (typically UTC) — must convert to market time before taking
    # .date(), or the calendar date can be off by one (see snapshots.py).
    points = [
        SnapshotPoint(
            date=snapshot.snapshot_date.astimezone(MARKET_TIMEZONE).date(),
            total_value=snapshot.total_value,
        )
        for snapshot in snapshots
    ]

    return calculate_risk_analytics(points, portfolio.initial_capital, risk_free_rate_annual)
