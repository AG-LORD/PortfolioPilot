"""Record today's valuation snapshot for every portfolio.

Run from backend/ once a day after the NSE close (see docs/DAILY_SNAPSHOTS.md):
    python -m scripts.take_daily_snapshots

Uses the regular snapshot service against DATABASE_URL. It only runs once
today's session is complete (market_calendar: MARKET_CLOSE plus the settle
buffer, IST). A portfolio that already has today's snapshot is "skipped";
one portfolio failing (e.g. a price is unavailable) is reported and does not
stop the others. Weekends are skipped (NSE holidays are not known).

Exit codes (shared with scripts/nightly_jobs.py): EXIT_OK 0, EXIT_FAILED 1
(something failed), EXIT_TOO_EARLY 2 (session not complete yet),
EXIT_NON_TRADING_DAY 3 (weekend).
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Portfolio
from app.services.market_calendar import MARKET_TIMEZONE, is_trading_weekday, last_completed_trading_day
from app.services.market_data import MarketDataUnavailableError
from app.services.snapshots import create_portfolio_snapshot


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_TOO_EARLY = 2
EXIT_NON_TRADING_DAY = 3


@dataclass
class SnapshotRunSummary:
    ran: bool = True
    not_run_exit_code: int | None = None  # EXIT_TOO_EARLY / EXIT_NON_TRADING_DAY when ran is False
    created: list[UUID] = field(default_factory=list)
    skipped: list[UUID] = field(default_factory=list)
    failed: dict[UUID, str] = field(default_factory=dict)


def market_closed_today(now: datetime) -> bool:
    return last_completed_trading_day(now) == now.astimezone(MARKET_TIMEZONE).date()


def run_gate(now: datetime) -> int | None:
    """None when today's jobs may run; otherwise the exit code explaining why not."""
    if not is_trading_weekday(now.astimezone(MARKET_TIMEZONE).date()):
        return EXIT_NON_TRADING_DAY
    if not market_closed_today(now):
        return EXIT_TOO_EARLY
    return None


GATE_MESSAGES = {
    EXIT_NON_TRADING_DAY: "today is not a trading weekday",
    EXIT_TOO_EARLY: "today's market session is not complete yet",
}


def take_daily_snapshots(
    db: Session | None, now: datetime, portfolio_ids: list[UUID] | None = None
) -> SnapshotRunSummary:
    """portfolio_ids limits the run (used by tests); None means every portfolio."""
    blocked = run_gate(now)
    if blocked is not None:
        return SnapshotRunSummary(ran=False, not_run_exit_code=blocked)

    query = select(Portfolio.id, Portfolio.user_id).order_by(Portfolio.created_at)
    if portfolio_ids is not None:
        query = query.where(Portfolio.id.in_(portfolio_ids))
    targets = db.execute(query).all()

    summary = SnapshotRunSummary()
    for portfolio_id, user_id in targets:
        try:
            create_portfolio_snapshot(db, user_id, portfolio_id)
        except HTTPException as exc:
            db.rollback()
            if exc.status_code == status.HTTP_409_CONFLICT:
                summary.skipped.append(portfolio_id)
            else:
                summary.failed[portfolio_id] = str(exc.detail)
        except MarketDataUnavailableError as exc:
            db.rollback()
            summary.failed[portfolio_id] = str(exc)
        except Exception as exc:  # one portfolio must not stop the rest
            db.rollback()
            summary.failed[portfolio_id] = f"{type(exc).__name__}: {exc}"
        else:
            summary.created.append(portfolio_id)
    return summary


def print_summary(summary: SnapshotRunSummary, now: datetime) -> None:
    local = now.astimezone(MARKET_TIMEZONE)
    if not summary.ran:
        print(f"{local:%Y-%m-%d %H:%M} IST: {GATE_MESSAGES[summary.not_run_exit_code]}; no snapshots taken.")
        return
    print(
        f"{local:%Y-%m-%d %H:%M} IST: created {len(summary.created)}, "
        f"skipped {len(summary.skipped)} (already had today's snapshot), failed {len(summary.failed)}"
    )
    for portfolio_id, reason in summary.failed.items():
        print(f"  failed {portfolio_id}: {reason}")


def main() -> int:
    from app.database import SessionLocal

    now = datetime.now(MARKET_TIMEZONE)
    db = SessionLocal()
    try:
        summary = take_daily_snapshots(db, now)
    finally:
        db.close()
    print_summary(summary, now)
    if not summary.ran:
        return summary.not_run_exit_code
    return EXIT_FAILED if summary.failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
