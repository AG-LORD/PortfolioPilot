"""Point-in-time, scale-free technical features for one ticker.

Every function takes series indexed by trading date (sorted ascending) and
uses only trailing windows: the value at date t depends only on rows dated
<= t (no centered windows, no backfill, no negative shifts, no full-series
statistics). Rows whose windows are incomplete (warm-up) are dropped, never
filled. The label (forward return) is the only negative shift and is kept
separate from the features.

Scale-free: every feature is a ratio of prices or of returns, so multiplying
all prices by a constant leaves it unchanged; one model can serve all stocks.

Recursive smoothers (EMA for MACD, Wilder for RSI/ATR) start at the first row
of the series they are given, so a value also depends (with exponentially
decaying weight) on where the series starts; they never depend on later rows.
Panel rows (forecasting and evaluation) therefore require MIN_FEATURE_HISTORY
trading days of prior history, which makes that dependence negligible.

This module does not import the database layer; only build_feature_panel
touches the price cache.
"""

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.baseline import BASELINE_COLUMN, historical_mean_forecast
from app.services.market_calendar import ANNUALIZATION_FACTOR
from app.services.market_data import NO_DATA_REASON, PricePoint
from app.services.universe import ExcludedTicker

SMA_SHORT_WINDOW = 20
SMA_LONG_WINDOW = 50
MOMENTUM_WINDOWS = (5, 20, 60)
RSI_WINDOW = 14
MACD_FAST_SPAN = 12
MACD_SLOW_SPAN = 26
MACD_SIGNAL_SPAN = 9
ATR_WINDOW = 14
REALIZED_VOL_WINDOW = 20
DEFAULT_HORIZON = 20

# Rows 0 .. WARMUP_ROWS-1 have at least one incomplete window and are dropped.
WARMUP_ROWS = max(
    SMA_LONG_WINDOW - 1,
    max(MOMENTUM_WINDOWS),
    RSI_WINDOW,
    ATR_WINDOW,
    REALIZED_VOL_WINDOW,
    MACD_SLOW_SPAN + MACD_SIGNAL_SPAN - 2,
)
MIN_HISTORY_ROWS = WARMUP_ROWS + 1

# Panel rows (used for forecasting and evaluation) need at least this many
# trading days of history before their date, so the recursive smoothers'
# dependence on where the series starts is negligible. Equals the baseline
# lookback. A ticker therefore needs MIN_PANEL_ROWS rows to appear at all.
MIN_FEATURE_HISTORY = 252
MIN_PANEL_ROWS = MIN_FEATURE_HISTORY + 1

FEATURE_COLUMNS = [
    "close_to_sma_20",
    "close_to_sma_50",
    "sma_20_to_sma_50",
    "momentum_5",
    "momentum_20",
    "momentum_60",
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "atr_14",
    "realized_vol_20",
]
LABEL_COLUMN = "label"


def prices_to_frame(points: list[PricePoint]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [float(p.open) for p in points],
            "high": [float(p.high) for p in points],
            "low": [float(p.low) for p in points],
            "close": [float(p.close) for p in points],
            "volume": [p.volume for p in points],
        },
        index=pd.Index([p.date for p in points], name="date"),
    )


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def momentum(close: pd.Series, k: int) -> pd.Series:
    return close / close.shift(k) - 1


def wilder_smooth(values: pd.Series, window: int) -> pd.Series:
    """Wilder smoothing: seeded with the mean of the first `window` valid
    values, then avg_t = (avg_{t-1} * (window - 1) + x_t) / window."""
    x = values.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < window:
        return pd.Series(out, index=values.index)
    seed_end = valid[window - 1]
    avg = x[valid[:window]].mean()
    out[seed_end] = avg
    for i in range(seed_end + 1, len(x)):
        avg = (avg * (window - 1) + x[i]) / window
        out[i] = avg
    return pd.Series(out, index=values.index)


def rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """0-100. All-flat window (no gains, no losses) gives 50."""
    delta = close.diff()
    avg_gain = wilder_smooth(delta.clip(lower=0), window)
    avg_loss = wilder_smooth(-delta.clip(upper=0), window)
    total = avg_gain + avg_loss
    result = 100 * avg_gain / total
    return result.mask((total == 0) & total.notna(), 50.0)


def macd(
    close: pd.Series,
    fast: int = MACD_FAST_SPAN,
    slow: int = MACD_SLOW_SPAN,
    signal: int = MACD_SIGNAL_SPAN,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(line, signal, histogram), each divided by close."""
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return line / close, signal_line / close, (line - signal_line) / close


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = ATR_WINDOW) -> pd.Series:
    """Wilder ATR divided by close. True range needs the previous close, so
    it starts at the second row."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1, skipna=False)
    return wilder_smooth(true_range, window) / close


def realized_volatility(close: pd.Series, window: int = REALIZED_VOL_WINDOW) -> pd.Series:
    daily_returns = close / close.shift(1) - 1
    return daily_returns.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(ANNUALIZATION_FACTOR)


def forward_return(close: pd.Series, horizon: int = DEFAULT_HORIZON) -> pd.Series:
    """Label: close_{t+h} / close_t - 1. The last `horizon` rows are NaN."""
    return close.shift(-horizon) / close - 1


def compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Feature frame indexed by date, warm-up rows dropped."""
    close = prices["close"]
    sma_short = sma(close, SMA_SHORT_WINDOW)
    sma_long = sma(close, SMA_LONG_WINDOW)
    macd_line, macd_signal, macd_hist = macd(close)

    features = pd.DataFrame(
        {
            "close_to_sma_20": close / sma_short - 1,
            "close_to_sma_50": close / sma_long - 1,
            "sma_20_to_sma_50": sma_short / sma_long - 1,
            **{f"momentum_{k}": momentum(close, k) for k in MOMENTUM_WINDOWS},
            "rsi_14": rsi(close),
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "atr_14": atr(prices["high"], prices["low"], close),
            "realized_vol_20": realized_volatility(close),
        },
        index=prices.index,
    )
    return features[FEATURE_COLUMNS].iloc[WARMUP_ROWS:]


# --- panel (DB + price cache) ----------------------------------------------


@dataclass
class FeaturePanel:
    panel: pd.DataFrame  # columns: date, ticker, FEATURE_COLUMNS, label, BASELINE_COLUMN
    excluded: list[ExcludedTicker]


def build_panel_from_prices(
    tickers: list[str],
    points_by_ticker: dict[str, list[PricePoint]],
    errors: dict[str, str],
    horizon: int = DEFAULT_HORIZON,
) -> FeaturePanel:
    """In-memory panel builder (no database). `errors` maps a ticker to the
    reason its prices could not be fetched."""
    frames = []
    excluded: list[ExcludedTicker] = []

    for ticker in tickers:
        if ticker in errors:
            excluded.append(ExcludedTicker(ticker=ticker, reason=errors[ticker]))
            continue
        points = points_by_ticker.get(ticker, [])
        if not points:
            excluded.append(ExcludedTicker(ticker=ticker, reason=NO_DATA_REASON))
            continue
        if len(points) < MIN_PANEL_ROWS:
            excluded.append(
                ExcludedTicker(
                    ticker=ticker,
                    reason=(
                        f"only {len(points)} trading day(s) of history; at least "
                        f"{MIN_PANEL_ROWS} are needed"
                    ),
                )
            )
            continue

        prices = prices_to_frame(points)
        frame = compute_features(prices).loc[prices.index[MIN_FEATURE_HISTORY]:]
        frame[LABEL_COLUMN] = forward_return(prices["close"], horizon).loc[frame.index]
        frame[BASELINE_COLUMN] = historical_mean_forecast(prices["close"], horizon).loc[frame.index]
        frame.insert(0, "ticker", ticker)
        frames.append(frame.reset_index())

    columns = ["date", "ticker", *FEATURE_COLUMNS, LABEL_COLUMN, BASELINE_COLUMN]
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    return FeaturePanel(
        panel=panel[columns].sort_values(["date", "ticker"], ignore_index=True),
        excluded=excluded,
    )


def build_feature_panel(
    db: Session,
    tickers: list[str],
    start: date,
    end: date,
    horizon: int = DEFAULT_HORIZON,
) -> FeaturePanel:
    """Panel for [start, end) (end exclusive), read through the price cache."""
    # Imported here so this module stays importable without a database; the
    # offline evaluation script uses build_panel_from_prices directly.
    from app.services import price_history

    history = price_history.get_price_history(db, tickers, start, end)
    errors = {ticker: exc.reason for ticker, exc in history.errors.items()}
    return build_panel_from_prices(tickers, history.points, errors, horizon)
