"""Synthetic OHLCV frames and price points for the feature-group tests."""

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from app.services.market_data import PricePoint


def ohlcv_frame(close, high=None, low=None, volume=None, open_=None, start="2024-01-01") -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    index = pd.Index(pd.bdate_range(start, periods=len(close)).date, name="date")
    return pd.DataFrame(
        {
            "open": close if open_ is None else np.asarray(open_, dtype=float),
            "high": close * 1.005 if high is None else np.asarray(high, dtype=float),
            "low": close * 0.995 if low is None else np.asarray(low, dtype=float),
            "close": close,
            "volume": np.full(len(close), 1000.0) if volume is None else np.asarray(volume, dtype=float),
        },
        index=index,
    )


def random_ohlcv(n=400, seed=0, drift=0.0004, vol=0.018) -> pd.DataFrame:
    """Random-walk OHLCV with consistent high/low and varying volume."""
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(drift, vol, n))
    open_ = close * (1 + rng.normal(0, 0.004, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.015, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.015, n))
    volume = rng.lognormal(mean=12, sigma=0.4, size=n).round()
    return ohlcv_frame(close, high, low, volume, open_)


def frame_to_points(frame: pd.DataFrame) -> list[PricePoint]:
    return [
        PricePoint(
            date=d if isinstance(d, date) else d.date(),
            open=Decimal(str(r.open)),
            high=Decimal(str(r.high)),
            low=Decimal(str(r.low)),
            close=Decimal(str(r.close)),
            volume=int(r.volume),
        )
        for d, r in zip(frame.index, frame.itertuples())
    ]
