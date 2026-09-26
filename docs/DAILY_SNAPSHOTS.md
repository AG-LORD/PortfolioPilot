# Nightly jobs and daily portfolio snapshots

Schedule **`backend/scripts/nightly_jobs.py`** once per trading weekday after the close. It runs three stages and reports each one; a failed stage does not stop the others:

1. **snapshots**: today's snapshot for every portfolio (the logic of `take_daily_snapshots.py`, below).
2. **prices**: warms the price cache for the NIFTY 50 universe.
3. **forecasts**: trains the ML model once on the pooled NIFTY 50 panel and stores the forecasts for the latest feature date in `ml_forecasts` (see `docs/ML_METHODOLOGY.md`, section 9). Recommendations that day use them without training.

```
cd backend
python -m scripts.nightly_jobs
```

`python -m scripts.take_daily_snapshots` still runs the snapshot stage alone.

## Snapshots

Risk analytics (volatility, Sharpe ratio, VaR) are computed from daily portfolio snapshots and need about 30 of them.

- It uses `DATABASE_URL` from `backend/.env` and the same snapshot service as `POST /portfolios/{id}/snapshots`.
- It only runs once today's session is complete: 15:30 IST close plus a 30-minute settle buffer (`market_calendar`). Earlier, it exits without taking snapshots.
- A portfolio that already has today's snapshot (one per IST calendar day) is reported as **skipped**. A portfolio whose prices are unavailable is reported as **failed** with the reason; the others still run.
- Exit codes (both scripts): 0 all done, 1 something failed (a portfolio, or a nightly stage), 2 run before the session was complete, 3 not a trading weekday (Saturday/Sunday).
- NSE exchange holidays are not detected (known limitation): on a weekday holiday the jobs run against unchanged prices.

## Windows Task Scheduler (16:30 IST, Monday–Friday)

Assuming the machine clock is IST and Python is on `PATH`:

```
schtasks /Create /TN "PortfolioPilot nightly jobs" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:30 ^
  /TR "cmd /c cd /d C:\Dev\PortfolioPilot\backend && python -m scripts.nightly_jobs >> nightly.log 2>&1"
```

Use the full path to the virtual environment's `python.exe` if the backend runs in one.

## cron (16:30 IST, Monday–Friday)

```
CRON_TZ=Asia/Kolkata
30 16 * * 1-5  cd /path/to/PortfolioPilot/backend && python -m scripts.nightly_jobs >> nightly.log 2>&1
```

If your cron does not support `CRON_TZ`, convert to the server's timezone (16:30 IST is 11:00 UTC: `0 11 * * 1-5`).
