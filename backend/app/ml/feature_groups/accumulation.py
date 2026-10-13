"""Accumulation/distribution-like conditions from observable OHLCV (research group "accdist").

These are rule-based descriptions of price and volume, not knowledge of who
is buying or selling: a high accumulation_score means "conditions that
accumulation is often described with", not that a stock IS being accumulated.
No score is fitted to data; every weight below is fixed.

Windows: R = 20 bars for the trading range, L = 120 bars for the baseline of
range width and volume, M = 5 bars for a breakout to fail. H_R and L_R are
the highest high and lowest low of the last R bars INCLUDING t; "prior range"
is the same over the R bars BEFORE t.

ad_range_width          (H_R - L_R) / close_t.
range_position          (close_t - L_R) / (H_R - L_R) in [0, 1]; 0.5 when the
                        range has zero width.
ad_money_flow           sum(CLV * volume) / sum(volume) over R, in [-1, 1],
                        CLV = ((close - low) - (high - close)) / (high - low),
                        0 on a bar with high == low; 0 when there is no volume.
volume_imbalance        (volume on up closes - volume on down closes) /
                        total volume over R, in [-1, 1]; 0 without volume.
ad_relative_volume      log(mean volume over 5 bars / mean volume over L),
                        clipped to +-3; 0 when either mean is 0.
ad_effort_result        R-bar return / max(mean volume R / mean volume L, 0.25),
                        clipped to +-1 (price progress per unit of relative
                        volume).
volatility_compression  log((H_R - L_R) / median of (H_R - L_R) over the
                        previous L bars), clipped to +-3; negative means a
                        narrower range than usual; 0 when undefined.
breakout_volume_ratio   for the latest close beyond the prior range within the
                        last R bars: log(volume that day / mean volume of the
                        R bars before it), clipped to +-3; 0 if none.
failed_breakout_flag    +1 if a close below the prior-range low was followed,
                        within M bars, by a close back above that low (failed
                        downside break), -1 for the mirror case above the
                        prior-range high; set from the bar the close returns
                        inside and kept for M bars; 0 otherwise. The latest
                        failure wins.
ad_dist_range_high      (H_R - close_t) / ATR14_t, clipped to [0, 10].
ad_dist_range_low       (close_t - L_R) / ATR14_t, clipped to [0, 10].
accumulation_score      mean of [(money_flow + 1) / 2, (volume_imbalance + 1) / 2,
                        (1 - tanh(volatility_compression)) / 2,
                        1 if failed_breakout_flag == +1 else 0], in [0, 1].
distribution_score      mean of [(1 - money_flow) / 2, (1 - volume_imbalance) / 2,
                        (1 - tanh(volatility_compression)) / 2,
                        1 if failed_breakout_flag == -1 else 0], in [0, 1].
"""

import numpy as np
import pandas as pd

from app.ml.feature_groups.pivots import atr_abs

GROUP = "accdist"
RANGE_WINDOW = 20
BASELINE_WINDOW = 120
FAIL_WINDOW = 5
SHORT_VOLUME_WINDOW = 5
LOG_CLIP = 3.0
DIST_CLIP = 10.0

COLUMNS = (
    "ad_range_width",
    "range_position",
    "ad_money_flow",
    "volume_imbalance",
    "ad_relative_volume",
    "ad_effort_result",
    "volatility_compression",
    "breakout_volume_ratio",
    "failed_breakout_flag",
    "ad_dist_range_high",
    "ad_dist_range_low",
    "accumulation_score",
    "distribution_score",
)


def _ratio(numerator: pd.Series, denominator: pd.Series, default: float = 0.0) -> pd.Series:
    """numerator / denominator with `default` where the denominator is 0 (NaN stays NaN)."""
    out = numerator / denominator.where(denominator != 0)
    return out.mask((denominator == 0) & numerator.notna(), default)


def _log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = (numerator > 0) & (denominator > 0)
    out = np.log(numerator.where(valid) / denominator.where(valid)).clip(-LOG_CLIP, LOG_CLIP)
    return out.mask(~valid & numerator.notna() & denominator.notna(), 0.0)


def _breakouts(close, prior_high, prior_low, volume, prior_volume_mean):
    """(breakout_volume_ratio, failed_breakout_flag) arrays; one causal pass."""
    n = len(close)
    ratio = np.zeros(n)
    flag = np.zeros(n)
    last_breakout = None  # (bar, log volume ratio)
    pending = None  # (bar, direction, level): a breakout that may still fail
    last_failure = None  # (bar, flag value)
    for t in range(n):
        if np.isfinite(prior_high[t]) and np.isfinite(prior_low[t]):
            if pending is not None:
                bar, direction, level = pending
                if direction > 0 and close[t] < level:
                    last_failure, pending = (t, -1.0), None
                elif direction < 0 and close[t] > level:
                    last_failure, pending = (t, 1.0), None
                elif t - bar >= FAIL_WINDOW:
                    pending = None
            direction = 1 if close[t] > prior_high[t] else -1 if close[t] < prior_low[t] else 0
            if direction:
                level = prior_high[t] if direction > 0 else prior_low[t]
                pending = (t, direction, level)
                v, m = volume[t], prior_volume_mean[t]
                log_ratio = float(np.clip(np.log(v / m), -LOG_CLIP, LOG_CLIP)) if v > 0 and m > 0 else 0.0
                last_breakout = (t, log_ratio)
        if last_breakout is not None and t - last_breakout[0] < RANGE_WINDOW:
            ratio[t] = last_breakout[1]
        if last_failure is not None and t - last_failure[0] < FAIL_WINDOW:
            flag[t] = last_failure[1]
    return ratio, flag


def compute(prices: pd.DataFrame) -> pd.DataFrame:
    high, low, close = prices["high"], prices["low"], prices["close"]
    volume = prices["volume"].astype(float)
    r, l_win = RANGE_WINDOW, BASELINE_WINDOW

    range_high = high.rolling(r, min_periods=r).max()
    range_low = low.rolling(r, min_periods=r).min()
    width = range_high - range_low
    prior_high = range_high.shift(1)
    prior_low = range_low.shift(1)

    spread = high - low
    clv = _ratio((close - low) - (high - close), spread)
    volume_sum = volume.rolling(r, min_periods=r).sum()
    money_flow = _ratio((clv * volume).rolling(r, min_periods=r).sum(), volume_sum)

    change = close.diff()
    signed_volume = volume * np.sign(change)
    imbalance = _ratio(signed_volume.rolling(r, min_periods=r).sum(), volume_sum)

    volume_long = volume.rolling(l_win, min_periods=l_win).mean()
    relative_volume = _log_ratio(volume.rolling(SHORT_VOLUME_WINDOW, min_periods=SHORT_VOLUME_WINDOW).mean(), volume_long)
    relative_volume_r = _ratio(volume.rolling(r, min_periods=r).mean(), volume_long, default=np.nan)
    effort = (close / close.shift(r) - 1) / relative_volume_r.clip(lower=0.25)
    effort = effort.clip(-1, 1).mask(relative_volume_r.isna() & effort.isna() & volume_long.notna(), 0.0)

    width_median = width.shift(1).rolling(l_win, min_periods=l_win).median()
    compression = _log_ratio(width, width_median)

    atr = pd.Series(atr_abs(prices), index=prices.index)
    position = _ratio(close - range_low, width, default=0.5)
    dist_high = _ratio(range_high - close, atr).clip(0, DIST_CLIP)
    dist_low = _ratio(close - range_low, atr).clip(0, DIST_CLIP)

    prior_volume_mean = volume.rolling(r, min_periods=r).mean().shift(1)
    breakout_ratio, failed = _breakouts(
        close.to_numpy(float), prior_high.to_numpy(float), prior_low.to_numpy(float),
        volume.to_numpy(float), prior_volume_mean.to_numpy(float),
    )
    failed = pd.Series(failed, index=prices.index)

    calm = (1 - np.tanh(compression)) / 2
    accumulation = pd.concat(
        [(money_flow + 1) / 2, (imbalance + 1) / 2, calm, (failed == 1).astype(float)], axis=1
    ).mean(axis=1, skipna=False)
    distribution = pd.concat(
        [(1 - money_flow) / 2, (1 - imbalance) / 2, calm, (failed == -1).astype(float)], axis=1
    ).mean(axis=1, skipna=False)

    frame = pd.DataFrame(
        {
            "ad_range_width": width / close,
            "range_position": position,
            "ad_money_flow": money_flow,
            "volume_imbalance": imbalance,
            "ad_relative_volume": relative_volume,
            "ad_effort_result": effort,
            "volatility_compression": compression,
            "breakout_volume_ratio": breakout_ratio,
            "failed_breakout_flag": failed,
            "ad_dist_range_high": dist_high,
            "ad_dist_range_low": dist_low,
            "accumulation_score": accumulation,
            "distribution_score": distribution,
        },
        index=prices.index,
    )
    return frame[list(COLUMNS)]
