"""Chart series for the frontend: a recommendation's past-year preview and the
portfolio's snapshot history, each next to NIFTY 50.

Pure math sits above the orchestration line and needs no database. Prices come
from the daily price cache (price_history), NIFTY 50 under
market_data.NIFTY50_INDEX.

History preview: the recommendation's weights are held FIXED every day (daily
rebalanced to the same mix); cash earns 0%. It is hindsight context using
today's weights, not a backtest (no walk-forward, no fees) and not a forecast.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import PortfolioSnapshot
from app.services import market_data
from app.services.market_calendar import MARKET_TIMEZONE
from app.services.market_data import MarketDataUnavailableError, PricePoint
from app.services.portfolios import get_portfolio
from app.services.price_history import get_price_history
from app.services.recommendation import get_recommendation_snapshot

VALUE_QUANTUM = Decimal("0.01")
PERIOD_DAYS = {"1y": 365}
# A ticker whose first price is this much later than the requested start is
# treated as lacking full history (allows for weekends and holidays).
HISTORY_START_GRACE = timedelta(days=7)

PREVIEW_NOTE = (
    "Historical context only: today's weights applied to the past {period} with hindsight "
    "(held fixed, cash at 0%). This is not a backtest and not a forecast."
)


@dataclass
class MixPoint:
    date: date
    mix: Decimal
    benchmark: Decimal


@dataclass
class MixHistory:
    start: date
    end: date
    points: list[MixPoint]
    late_tickers: list[str]  # tickers whose history starts after the requested start


@dataclass
class PerformancePoint:
    date: date
    portfolio: Decimal
    benchmark: Decimal | None


def _q(value: Decimal) -> Decimal:
    return value.quantize(VALUE_QUANTUM, rounding=ROUND_HALF_UP)


def _closes(points: list[PricePoint]) -> dict[date, Decimal]:
    return {p.date: p.close for p in points if p.close > 0}


def fixed_weight_history(
    prices: dict[str, list[PricePoint]],
    weights: dict[str, Decimal],
    capital: Decimal,
    benchmark: list[PricePoint],
    requested_start: date,
) -> MixHistory:
    """Daily value of a fixed-weight mix (weights not in `weights` are cash at
    0%) and the benchmark scaled to the same starting capital.

    The series starts at the latest first-price date across the stocks and the
    benchmark, and uses only days on which all of them have a close."""
    series = {ticker: _closes(prices.get(ticker, [])) for ticker in weights}
    bench = _closes(benchmark)
    if not bench or any(not closes for closes in series.values()):
        raise ValueError("Every ticker and the benchmark need price history")

    first_dates = {ticker: min(closes) for ticker, closes in series.items()}
    common_start = max([min(bench), *first_dates.values()])
    late = sorted(t for t, d in first_dates.items() if d > requested_start + HISTORY_START_GRACE)

    days = sorted(
        d for d in bench if d >= common_start and all(d in closes for closes in series.values())
    )
    if not days:
        raise ValueError("No common trading days across the mix and the benchmark")

    value = capital
    bench_start = bench[days[0]]
    points = [MixPoint(days[0], _q(capital), _q(capital))]
    for previous, day in zip(days, days[1:]):
        daily_return = sum(
            (w * (series[t][day] / series[t][previous] - 1) for t, w in weights.items()),
            Decimal("0"),
        )
        value = value * (1 + daily_return)
        points.append(MixPoint(day, _q(value), _q(capital * bench[day] / bench_start)))
    return MixHistory(start=days[0], end=days[-1], points=points, late_tickers=late)


def preview_note(period: str, late_tickers: list[str], start: date) -> str:
    note = PREVIEW_NOTE.format(period="year" if period == "1y" else period)
    if late_tickers:
        note += (
            f" {', '.join(late_tickers)} lack a full {period} of prices, so the series starts on "
            f"{start.isoformat()}, the latest common start date."
        )
    return note


def performance_series(
    snapshots: list[tuple[date, Decimal]],
    benchmark: list[PricePoint],
) -> list[PerformancePoint]:
    """Snapshot values next to the benchmark scaled to the first snapshot's
    value. Each day uses the latest benchmark close on or before it; the
    benchmark is null where no close exists yet. Fewer than 2 snapshots: []."""
    if len(snapshots) < 2:
        return []
    closes = sorted(_closes(benchmark).items())

    def close_on_or_before(day: date) -> Decimal | None:
        found = None
        for close_day, close in closes:
            if close_day > day:
                break
            found = close
        return found

    base_value = snapshots[0][1]
    base_close = close_on_or_before(snapshots[0][0])
    points = []
    for day, value in snapshots:
        close = close_on_or_before(day)
        bench = _q(base_value * close / base_close) if close is not None and base_close else None
        points.append(PerformancePoint(day, _q(value), bench))
    return points


# --- orchestration (DB + market data) --------------------------------------


def get_history_preview(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    recommendation_id: UUID,
    period: str = "1y",
    *,
    today: date | None = None,
    benchmark_ticker: str | None = None,
):
    """Raises ValueError when the recommendation is not this portfolio's and
    MarketDataUnavailableError when prices are missing."""
    benchmark_ticker = benchmark_ticker or market_data.NIFTY50_INDEX
    snapshot = get_recommendation_snapshot(db, user_id, portfolio_id, recommendation_id)
    weights = {item["ticker"]: Decimal(str(item["target_weight"])) for item in snapshot.allocations}

    today = today or datetime.now(MARKET_TIMEZONE).date()
    start = today - timedelta(days=PERIOD_DAYS[period])
    tickers = [*weights, benchmark_ticker]
    history = get_price_history(db, tickers, start, today + timedelta(days=1))
    for ticker in tickers:
        if ticker in history.errors:
            raise history.errors[ticker]

    try:
        result = fixed_weight_history(
            {t: history.points[t] for t in weights},
            weights,
            snapshot.capital,
            history.points[benchmark_ticker],
            start,
        )
    except ValueError as exc:
        raise MarketDataUnavailableError(", ".join(tickers), str(exc)) from exc
    return result, preview_note(period, result.late_tickers, result.start)


def get_performance(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    *,
    benchmark_ticker: str | None = None,
) -> list[PerformancePoint]:
    benchmark_ticker = benchmark_ticker or market_data.NIFTY50_INDEX
    get_portfolio(db, user_id, portfolio_id)
    rows = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == portfolio_id)
        .order_by(PortfolioSnapshot.snapshot_date.asc())
        .all()
    )
    snapshots = [(row.snapshot_date.astimezone(MARKET_TIMEZONE).date(), row.total_value) for row in rows]
    if len(snapshots) < 2:
        return []

    # A week of lead-in so the first snapshot has a close on or before it.
    history = get_price_history(
        db, [benchmark_ticker], snapshots[0][0] - timedelta(days=7), snapshots[-1][0] + timedelta(days=1)
    )
    return performance_series(snapshots, history.points.get(benchmark_ticker, []))
