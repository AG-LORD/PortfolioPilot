"""Market conventions shared by request-time services and offline ML code.

No database imports: the offline evaluation script depends on this module.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# PortfolioPilot is an Indian-equity app: a market "day" is a calendar date in
# this timezone, not UTC or the caller's.
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")

# Trading days per year. A standard convention, not an NSE-specific count
# (the app has no exchange trading calendar).
ANNUALIZATION_FACTOR = 252

MARKET_CLOSE = time(15, 30)
CLOSE_SETTLE_BUFFER = timedelta(minutes=30)


def last_completed_trading_day(now: datetime) -> date:
    """Today once MARKET_CLOSE + CLOSE_SETTLE_BUFFER IST has passed, else
    yesterday. Weekends and holidays are not special-cased."""
    local = now.astimezone(MARKET_TIMEZONE)
    completed_at = datetime.combine(local.date(), MARKET_CLOSE, tzinfo=MARKET_TIMEZONE)
    if local >= completed_at + CLOSE_SETTLE_BUFFER:
        return local.date()
    return local.date() - timedelta(days=1)
