from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from app.services.market_data import PricePoint

# Synthetic tickers stored in the price cache must use this prefix so they can
# never collide with real NSE symbols.
TEST_TICKER_PREFIX = "ZZTEST_"


def make_series(seed, n_days=400, end=None, drift=0.0008, vol=0.015, weekdays_only=False):
    """Synthetic daily OHLCV ending at `end` (default: 2 days ago), full float
    precision like market_data produces."""
    end = end or date.today() - timedelta(days=2)
    days = [end - timedelta(days=i) for i in range(n_days)][::-1]
    if weekdays_only:
        days = [d for d in days if d.weekday() < 5]
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(np.concatenate([[1.0], 1 + rng.normal(drift, vol, len(days) - 1)]))
    return [
        PricePoint(
            date=d,
            open=Decimal(str(c * 0.998)),
            high=Decimal(str(c * 1.01)),
            low=Decimal(str(c * 0.99)),
            close=Decimal(str(c)),
            volume=1000 + i,
        )
        for i, (d, c) in enumerate(zip(days, closes))
    ]


class FakeMarket:
    """Stands in for market_data.download_history_batch (the yfinance layer)."""

    def __init__(self):
        self.series: dict[str, list[PricePoint]] = {}
        self.calls: list[tuple[list[str], date, date]] = []
        self.fail: Exception | None = None

    def download(self, tickers, start, end):
        assert all(t.startswith(TEST_TICKER_PREFIX) for t in tickers), tickers
        self.calls.append((list(tickers), start, end))
        if self.fail:
            raise self.fail
        return {t: [p for p in self.series.get(t, []) if start <= p.date < end] for t in tickers}
