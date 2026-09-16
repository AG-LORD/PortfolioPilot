"""Market data via yfinance.

Two distinct price concepts, not to be confused:
- CURRENT price (get_current_price): a best-effort "right now" price for
  live valuation. fast_info first, same-day history as fallback only —
  not a historical/analytical series.
- HISTORICAL price (get_historical_prices): adjusted OHLC (auto_adjust=True)
  for a date range — the canonical series for valuation history, feature
  engineering, ML training, and backtesting.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import yfinance as yf


class MarketDataUnavailableError(Exception):
    def __init__(self, ticker: str, reason: str):
        self.ticker = ticker
        self.reason = reason
        super().__init__(f"Market data unavailable for {ticker}: {reason}")


@dataclass
class PricePoint:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


def _to_yfinance_symbol(ticker: str) -> str:
    return f"{ticker.upper()}.NS"


def get_current_price(ticker: str) -> Decimal:
    """Best-effort current price for live valuation — not a historical price."""
    yf_ticker = yf.Ticker(_to_yfinance_symbol(ticker))

    try:
        last_price = yf_ticker.fast_info.last_price
        if last_price is not None and last_price > 0:
            return Decimal(str(last_price))
    except Exception:
        pass

    # Fallback: most recent daily close, not a real-time quote.
    try:
        history = yf_ticker.history(period="1d", auto_adjust=True)
        if not history.empty:
            close = history["Close"].iloc[-1]
            if close is not None and close > 0:
                return Decimal(str(close))
    except Exception:
        pass

    raise MarketDataUnavailableError(
        ticker, "no current price available from fast_info or recent history"
    )


def get_historical_prices(ticker: str, start: date, end: date) -> list[PricePoint]:
    """Adjusted OHLC history — the canonical series for analytics, not live valuation."""
    yf_ticker = yf.Ticker(_to_yfinance_symbol(ticker))

    try:
        history = yf_ticker.history(start=start, end=end, auto_adjust=True)
    except Exception as exc:
        raise MarketDataUnavailableError(ticker, f"history request failed: {exc}") from exc

    if history.empty:
        raise MarketDataUnavailableError(ticker, "no historical data returned")

    return [
        PricePoint(
            date=index.date(),
            open=Decimal(str(row["Open"])),
            high=Decimal(str(row["High"])),
            low=Decimal(str(row["Low"])),
            close=Decimal(str(row["Close"])),
            volume=int(row["Volume"]),
        )
        for index, row in history.iterrows()
    ]
