"""Point-in-time historical-mean baseline on the same horizon as the models.

forecast_t = horizon * mean(daily returns over the trailing BASELINE_LOOKBACK
trading days up to and including t). Arithmetic mean, consistent with the
live historical provider (mean daily return * 252 per year). Dates without a
full trailing window get NaN (no forecast).
"""

import pandas as pd

BASELINE_LOOKBACK = 252
BASELINE_COLUMN = "hist_mean_forecast"


def historical_mean_forecast(
    close: pd.Series, horizon: int, lookback: int = BASELINE_LOOKBACK
) -> pd.Series:
    daily_returns = close / close.shift(1) - 1
    return horizon * daily_returns.rolling(lookback, min_periods=lookback).mean()
