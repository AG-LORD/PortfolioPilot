"""Nightly jobs, run once per trading weekday after the NSE close.

Run from backend/ (see docs/DAILY_SNAPSHOTS.md for scheduling):
    python -m scripts.nightly_jobs

Stages, each reported separately; one failing stage does not stop the others:
  1. snapshots  - today's portfolio snapshots (scripts.take_daily_snapshots)
  2. prices     - warm the price cache for the NIFTY50 universe (ML history window)
  3. forecasts  - train the ML model once on the pooled NIFTY50 panel with
                  fit_and_forecast() (the same code as on-request forecasts)
                  and upsert the forecasts for the latest feature date into
                  ml_forecasts.

Exit codes are those of scripts.take_daily_snapshots: EXIT_OK, EXIT_FAILED
(any stage failed), EXIT_TOO_EARLY, EXIT_NON_TRADING_DAY.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.services import price_history
from app.services.market_calendar import MARKET_TIMEZONE
from app.services.ml_forecasts import upsert_panel_forecast
from app.services.return_providers import MIN_PRICE_ROWS, ML_HISTORY_DAYS, fit_and_forecast
from app.services.universe import get_universe
from scripts.take_daily_snapshots import (
    EXIT_FAILED,
    EXIT_OK,
    GATE_MESSAGES,
    run_gate,
    take_daily_snapshots,
)

NIGHTLY_UNIVERSE = "NIFTY50"


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str


@dataclass
class NightlyRunSummary:
    ran: bool = True
    not_run_exit_code: int | None = None
    stages: list[StageResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(not stage.ok for stage in self.stages)


def _history_window(today: date) -> tuple[date, date]:
    return today - timedelta(days=ML_HISTORY_DAYS), today


def stage_snapshots(db: Session, now: datetime) -> StageResult:
    summary = take_daily_snapshots(db, now)
    detail = f"created {len(summary.created)}, skipped {len(summary.skipped)}, failed {len(summary.failed)}"
    detail += "".join(f"; {pid}: {reason}" for pid, reason in summary.failed.items())
    return StageResult("snapshots", ok=not summary.failed, detail=detail)


def _universe_prices(db: Session, today: date):
    _, _, tickers = get_universe(NIGHTLY_UNIVERSE)
    start, end = _history_window(today)
    return tickers, price_history.get_price_history(db, tickers, start, end)


def stage_prices(db: Session, now: datetime) -> StageResult:
    tickers, history = _universe_prices(db, now.astimezone(MARKET_TIMEZONE).date())
    detail = f"{len(tickers) - len(history.errors)} of {len(tickers)} tickers cached"
    detail += "".join(f"; {t}: {err.reason}" for t, err in history.errors.items())
    # Individual tickers without data are reported but do not fail the stage.
    return StageResult("prices", ok=len(history.errors) < len(tickers), detail=detail)


def stage_forecasts(db: Session, now: datetime) -> StageResult:
    tickers, history = _universe_prices(db, now.astimezone(MARKET_TIMEZONE).date())
    prices = {
        t: history.points[t]
        for t in tickers
        if t not in history.errors and len(history.points.get(t, [])) >= MIN_PRICE_ROWS
    }
    panel = fit_and_forecast(prices)
    if panel is None:
        return StageResult("forecasts", ok=False, detail="not enough training rows; nothing stored")
    stored = upsert_panel_forecast(db, panel)
    lower, upper = panel.clip_bounds
    clipped = sum(f.clipped for f in panel.forecasts.values())
    return StageResult(
        "forecasts",
        ok=True,
        detail=(
            f"{stored} forecasts stored for {panel.as_of} ({panel.model_version}); "
            f"trained on {panel.training_rows} rows {panel.training_start}..{panel.training_end}; "
            f"clip bounds {lower:.4f}..{upper:.4f}, {clipped} clipped"
        ),
    )


STAGES: list[tuple[str, Callable[[Session, datetime], StageResult]]] = [
    ("snapshots", stage_snapshots),
    ("prices", stage_prices),
    ("forecasts", stage_forecasts),
]


def run_nightly(db: Session | None, now: datetime) -> NightlyRunSummary:
    blocked = run_gate(now)
    if blocked is not None:
        return NightlyRunSummary(ran=False, not_run_exit_code=blocked)

    summary = NightlyRunSummary()
    for name, stage in STAGES:
        try:
            summary.stages.append(stage(db, now))
        except Exception as exc:  # one stage must not stop the others
            db.rollback()
            summary.stages.append(StageResult(name, ok=False, detail=f"{type(exc).__name__}: {exc}"))
    return summary


def print_summary(summary: NightlyRunSummary, now: datetime) -> None:
    local = now.astimezone(MARKET_TIMEZONE)
    if not summary.ran:
        print(f"{local:%Y-%m-%d %H:%M} IST: {GATE_MESSAGES[summary.not_run_exit_code]}; nightly jobs not run.")
        return
    print(f"{local:%Y-%m-%d %H:%M} IST nightly jobs:")
    for stage in summary.stages:
        print(f"  {stage.name:<10} {'ok' if stage.ok else 'FAILED':<7} {stage.detail}")


def exit_code(summary: NightlyRunSummary) -> int:
    if not summary.ran:
        return summary.not_run_exit_code
    return EXIT_FAILED if summary.failed else EXIT_OK


def main() -> int:
    from app.database import SessionLocal

    now = datetime.now(MARKET_TIMEZONE)
    db = SessionLocal()
    try:
        summary = run_nightly(db, now)
    finally:
        db.close()
    print_summary(summary, now)
    return exit_code(summary)


if __name__ == "__main__":
    sys.exit(main())
