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


def is_trading_weekday(day: date) -> bool:
    """Monday to Friday. NSE exchange holidays are not known here, so a
    holiday that falls on a weekday counts as a trading weekday."""
    return day.weekday() < 5


def latest_completed_trading_weekday(now: datetime) -> date:
    """last_completed_trading_day(now), stepped back to the previous weekday
    when that falls on a weekend."""
    day = last_completed_trading_day(now)
    while not is_trading_weekday(day):
        day -= timedelta(days=1)
    return day
