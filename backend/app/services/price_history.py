"""Persistent daily price cache in front of market_data's historical prices.

Prices are stored exactly as market_data returns them (yfinance
auto_adjust=True: O/H/L/C adjusted for splits and dividends on one basis).

Coverage: price_cache_coverage holds one contiguous, inclusive date range per
ticker. Dates inside it without a daily_prices row had no data (weekends,
holidays, pre-listing) and are never re-requested. A request outside the
range fetches only the missing edge(s); the new edge always touches the
existing range, so a gap between old coverage and a new request is fetched
too and the range stays contiguous.

Partial days: nothing after the last completed IST trading day is stored or
counted as covered. A day counts as completed from MARKET_CLOSE +
CLOSE_SETTLE_BUFFER IST.

Corporate actions: adjusted history changes retroactively after dividends
and splits, so cached rows can go stale. A ticker's whole covered range is
re-fetched and replaced when
  - its last full refresh is older than FULL_REFRESH_MAX_AGE,
  - force_refresh=True, or
  - the seam check fails: every edge fetch re-downloads the cached boundary
    day next to it, and if that day's close moved by more than
    SEAM_TOLERANCE (relative) the cached basis is out of date.

All tickers that need data are fetched in one batched download (plus one
more batch for tickers escalated to a full refresh by the seam check).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import DailyPrice, PriceCacheCoverage
from app.services import market_data
from app.services.market_calendar import (  # noqa: F401 (re-exported for callers/tests)
    CLOSE_SETTLE_BUFFER,
    MARKET_CLOSE,
    MARKET_TIMEZONE,
    last_completed_trading_day,
)
from app.services.market_data import NO_DATA_REASON, MarketDataUnavailableError, PricePoint

SOURCE = "yfinance"
FULL_REFRESH_MAX_AGE = timedelta(days=7)
SEAM_TOLERANCE = Decimal("0.0001")  # 0.01%


@dataclass
class PriceHistory:
    points: dict[str, list[PricePoint]] = field(default_factory=dict)
    errors: dict[str, MarketDataUnavailableError] = field(default_factory=dict)


@dataclass
class _Plan:
    ticker: str
    fetch_start: date
    fetch_end: date  # inclusive
    new_start: date
    new_end: date
    full_refresh: bool
    seam_closes: dict[date, Decimal] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(MARKET_TIMEZONE)


def get_price_history(
    db: Session,
    tickers: list[str],
    start: date,
    end: date,
    *,
    force_refresh: bool = False,
) -> PriceHistory:
    """Ordered daily prices per ticker for [start, end) (end exclusive, like
    market_data). A ticker with no rows in range gets a
    MarketDataUnavailableError in `errors`, matching market_data's reasons."""
    now = _now()
    last_day = min(end - timedelta(days=1), last_completed_trading_day(now))
    result = PriceHistory()

    if start <= last_day:
        coverage = {
            c.ticker: c
            for c in db.scalars(
                select(PriceCacheCoverage).where(PriceCacheCoverage.ticker.in_(tickers))
            )
        }
        plans = [
            plan
            for ticker in tickers
            if (plan := _plan(db, ticker, coverage.get(ticker), start, last_day, now, force_refresh))
        ]
        escalated = _execute(db, plans, now, result)
        if escalated:
            _execute(db, escalated, now, result)
        db.commit()

    rows = db.scalars(
        select(DailyPrice)
        .where(
            DailyPrice.ticker.in_(tickers),
            DailyPrice.date >= start,
            DailyPrice.date < end,
        )
        .order_by(DailyPrice.ticker, DailyPrice.date)
    )
    for row in rows:
        result.points.setdefault(row.ticker, []).append(
            PricePoint(
                date=row.date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
        )

    for ticker in tickers:
        if ticker not in result.points and ticker not in result.errors:
            result.errors[ticker] = MarketDataUnavailableError(ticker, NO_DATA_REASON)
    return result


def _plan(
    db: Session,
    ticker: str,
    cov: PriceCacheCoverage | None,
    start: date,
    last_day: date,
    now: datetime,
    force_refresh: bool,
) -> _Plan | None:
    if cov is None:
        return _Plan(ticker, start, last_day, start, last_day, full_refresh=True)

    new_start = min(cov.covered_start, start)
    new_end = max(cov.covered_end, last_day)

    if force_refresh or now - cov.last_full_refresh_at > FULL_REFRESH_MAX_AGE:
        return _full_refresh_plan(ticker, new_start, new_end)

    if new_start == cov.covered_start and new_end == cov.covered_end:
        return None

    fetch_start, fetch_end = new_start, new_end
    seam_closes: dict[date, Decimal] = {}
    if new_start < cov.covered_start:
        first = _boundary_row(db, ticker, cov, first=True)
        fetch_end = first.date if first else cov.covered_start - timedelta(days=1)
        if first:
            seam_closes[first.date] = first.close
    if new_end > cov.covered_end:
        last = _boundary_row(db, ticker, cov, first=False)
        fetch_start = last.date if last else cov.covered_end + timedelta(days=1)
        if last:
            seam_closes[last.date] = last.close
        if new_start < cov.covered_start:
            fetch_start = new_start
            fetch_end = new_end

    return _Plan(
        ticker, fetch_start, fetch_end, new_start, new_end, full_refresh=False, seam_closes=seam_closes
    )


def _full_refresh_plan(ticker: str, new_start: date, new_end: date) -> _Plan:
    return _Plan(ticker, new_start, new_end, new_start, new_end, full_refresh=True)


def _boundary_row(
    db: Session, ticker: str, cov: PriceCacheCoverage, *, first: bool
) -> DailyPrice | None:
    order = DailyPrice.date.asc() if first else DailyPrice.date.desc()
    return db.scalars(
        select(DailyPrice)
        .where(
            DailyPrice.ticker == ticker,
            DailyPrice.date >= cov.covered_start,
            DailyPrice.date <= cov.covered_end,
        )
        .order_by(order)
        .limit(1)
    ).first()


def _seam_matches(points: list[PricePoint], seam_closes: dict[date, Decimal]) -> bool:
    fetched = {p.date: p.close for p in points}
    for day, cached_close in seam_closes.items():
        new_close = fetched.get(day)
        if new_close is None or cached_close == 0:
            return False
        if abs(new_close - cached_close) / cached_close > SEAM_TOLERANCE:
            return False
    return True


def _execute(db: Session, plans: list[_Plan], now: datetime, result: PriceHistory) -> list[_Plan]:
    """Fetch all plans in one batch and store them. Returns full-refresh plans
    for tickers whose seam check failed."""
    if not plans:
        return []

    batch_start = min(p.fetch_start for p in plans)
    batch_end = max(p.fetch_end for p in plans)
    try:
        fetched = market_data.download_history_batch(
            [p.ticker for p in plans], batch_start, batch_end + timedelta(days=1)
        )
    except MarketDataUnavailableError as exc:
        for p in plans:
            result.errors[p.ticker] = MarketDataUnavailableError(p.ticker, exc.reason)
        return []

    escalated: list[_Plan] = []
    for plan in plans:
        points = [p for p in fetched.get(plan.ticker, []) if plan.fetch_start <= p.date <= plan.fetch_end]

        if not plan.full_refresh:
            if not _seam_matches(points, plan.seam_closes):
                escalated.append(_full_refresh_plan(plan.ticker, plan.new_start, plan.new_end))
                continue
            # Seam days are only compared, never re-stored, so cached rows stay
            # on a single adjustment basis.
            points = [p for p in points if p.date not in plan.seam_closes]
        else:
            db.execute(
                delete(DailyPrice).where(
                    DailyPrice.ticker == plan.ticker,
                    DailyPrice.date >= plan.new_start,
                    DailyPrice.date <= plan.new_end,
                )
            )
        _upsert_prices(db, plan.ticker, points, now)
        _upsert_coverage(db, plan, now)

    return escalated


def _upsert_prices(db: Session, ticker: str, points: list[PricePoint], now: datetime) -> None:
    if not points:
        return
    stmt = insert(DailyPrice).values(
        [
            {
                "ticker": ticker,
                "date": p.date,
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
                "source": SOURCE,
                "fetched_at": now,
            }
            for p in points
        ]
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_daily_price_ticker_date",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "source": stmt.excluded.source,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    db.execute(stmt)


def _upsert_coverage(db: Session, plan: _Plan, now: datetime) -> None:
    update = {"covered_start": plan.new_start, "covered_end": plan.new_end}
    if plan.full_refresh:
        update["last_full_refresh_at"] = now
    stmt = insert(PriceCacheCoverage).values({"ticker": plan.ticker, "last_full_refresh_at": now, **update})
    db.execute(stmt.on_conflict_do_update(index_elements=["ticker"], set_=update))
