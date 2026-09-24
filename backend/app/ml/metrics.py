"""Forecast evaluation metrics.

- MAE: mean absolute error between forecast and realized forward return.
- Hit rate: share of rows whose forecast sign matches the realized sign.
  Rows with a realized return of exactly 0 are excluded (no direction to
  hit); a forecast of exactly 0 counts as a miss.
- IC: on each date, the Spearman rank correlation between forecasts and
  realized returns across tickers; averaged over dates. Dates with fewer
  than MIN_IC_TICKERS tickers, or where either side is constant (rank
  correlation undefined), are skipped.
"""

import numpy as np
import pandas as pd

MIN_IC_TICKERS = 5


def mean_absolute_error(forecast: pd.Series, realized: pd.Series) -> float:
    return float((forecast - realized).abs().mean())


def hit_rate(forecast: pd.Series, realized: pd.Series) -> float:
    directional = realized != 0
    return float((np.sign(forecast[directional]) == np.sign(realized[directional])).mean())


def daily_ic(dates: pd.Series, forecast: pd.Series, realized: pd.Series) -> pd.Series:
    """Spearman IC per date (index: date), only for usable dates."""
    frame = pd.DataFrame({"date": dates.to_numpy(), "f": forecast.to_numpy(), "r": realized.to_numpy()})
    values = {}
    for day, group in frame.groupby("date", sort=True):
        if len(group) < MIN_IC_TICKERS or group["f"].nunique() < 2 or group["r"].nunique() < 2:
            continue
        values[day] = float(np.corrcoef(group["f"].rank(), group["r"].rank())[0, 1])
    return pd.Series(values, dtype=float)


def mean_ic(dates: pd.Series, forecast: pd.Series, realized: pd.Series) -> float:
    return float(daily_ic(dates, forecast, realized).mean())
