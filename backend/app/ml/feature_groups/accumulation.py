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
                        range has zero width; range_position_valid is 0 when
                        the rolling range is unavailable or has zero width.
ad_money_flow           sum(CLV * volume) / sum(volume) over R, in [-1, 1],
                        CLV = ((close - low) - (high - close)) / (high - low),
                        0 on a bar with high == low; 0 when there is no volume.
                        ad_money_flow_valid is 0 when total volume is zero or
                        the window is incomplete.
volume_imbalance        (volume on up closes - volume on down closes) /
                        total volume over R, in [-1, 1]; 0 without volume.
                        volume_imbalance_valid is 0 when total volume is zero
                        or the window is incomplete.
ad_relative_volume      log(mean volume over 5 bars / mean volume over L),
                        clipped to +-3; 0 when either mean is 0.
                        ad_relative_volume_valid requires both means positive.
ad_effort_result        R-bar return / max(mean volume R / mean volume L, 0.25),
                        clipped to +-1 (price progress per unit of relative
                        volume); ad_effort_result_valid requires both volume
                        means and the price return to be available.
volatility_compression  log((H_R - L_R) / median of (H_R - L_R) over the
                        previous L bars), clipped to +-3; negative means a
                        narrower range than usual; 0 when either width is zero
                        or unavailable. volatility_compression_valid requires
                        both widths positive and available.
breakout_volume_ratio   for the latest close beyond the prior range within the
                        last R bars: log(volume that day / mean volume of the
                        R bars before it), clipped to +-3; 0 if none.
                        breakout_volume_ratio_valid is 0 before the prior range
                        is available or when an active breakout has zero or
                        unavailable volume / baseline volume; otherwise 1.
failed_breakout_flag    +1 if a close below the prior-range low was followed,
                        within M bars, by a close back above that low (failed
                        downside break), -1 for the mirror case above the
                        prior-range high; set from the bar the close returns
                        inside and kept for M bars; 0 otherwise. The latest
                        failure wins. failed_breakout_flag_valid requires a
                        finite close and an available prior range, except a
                        previously observed failure remains valid while held.
ad_dist_range_high      (H_R - close_t) / ATR14_t, clipped to [0, 10].
ad_dist_range_low       (close_t - L_R) / ATR14_t, clipped to [0, 10].
                        Matching *_valid columns require an available range
                        and positive finite ATR.
accumulation_score      mean of [(money_flow + 1) / 2, (volume_imbalance + 1) / 2,
                        (1 - tanh(volatility_compression)) / 2,
                        1 if failed_breakout_flag == +1 else 0], in [0, 1].
distribution_score      mean of [(1 - money_flow) / 2, (1 - volume_imbalance) / 2,
                        (1 - tanh(volatility_compression)) / 2,
                        1 if failed_breakout_flag == -1 else 0], in [0, 1].
                        accumulation_score_valid and distribution_score_valid
                        require valid money flow, volume imbalance, volatility
                        compression, and failed_breakout_flag_valid.
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
    "ad_range_width_valid",
    "range_position",
    "range_position_valid",
    "ad_money_flow",
    "ad_money_flow_valid",
    "volume_imbalance",
    "volume_imbalance_valid",
    "ad_relative_volume",
    "ad_relative_volume_valid",
    "ad_effort_result",
    "ad_effort_result_valid",
    "volatility_compression",
    "volatility_compression_valid",
    "breakout_volume_ratio",
    "breakout_volume_ratio_valid",
    "failed_breakout_flag",
    "failed_breakout_flag_valid",
    "ad_dist_range_high",
    "ad_dist_range_high_valid",
    "ad_dist_range_low",
    "ad_dist_range_low_valid",
    "accumulation_score",
    "accumulation_score_valid",
    "distribution_score",
    "distribution_score_valid",
)


def _ratio(numerator: pd.Series, denominator: pd.Series, default: float = 0.0) -> pd.Series:
    """numerator / denominator with `default` where the denominator is 0 (NaN stays NaN)."""
    out = numerator / denominator.where(denominator != 0)
    return out.mask((denominator == 0) & numerator.notna(), default)


def _log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = (numerator > 0) & (denominator > 0)
    out = np.log(numerator.where(valid) / denominator.where(valid)).clip(-LOG_CLIP, LOG_CLIP)
    return out.mask(~valid & numerator.notna() & denominator.notna(), 0.0)


def _breakouts(close, prior_high, prior_low, volume, prior_volume_mean, prior_volume_valid):
    """(ratio, ratio validity, failed flag, flag validity) arrays; one causal pass."""
    n = len(close)
    ratio = np.zeros(n)
    ratio_valid = np.zeros(n)
    flag = np.zeros(n)
    flag_valid = np.zeros(n)
    last_breakout = None  # (bar, log volume ratio, ratio validity)
    pending = None  # (bar, direction, level): a breakout that may still fail
    last_failure = None  # (bar, flag value)
    for t in range(n):
        if pending is not None and t - pending[0] > FAIL_WINDOW:
            pending = None
        range_known = np.isfinite(prior_high[t]) and np.isfinite(prior_low[t])
        close_known = np.isfinite(close[t])
        if range_known and close_known:
            if pending is not None:
                _, direction, level = pending
                if direction > 0 and close[t] < level:
                    last_failure, pending = (t, -1.0), None
                elif direction < 0 and close[t] > level:
                    last_failure, pending = (t, 1.0), None
            direction = 1 if close[t] > prior_high[t] else -1 if close[t] < prior_low[t] else 0
            if direction:
                level = prior_high[t] if direction > 0 else prior_low[t]
                pending = (t, direction, level)
                v, m = volume[t], prior_volume_mean[t]
                valid_ratio = (
                    np.isfinite(v) and v > 0 and np.isfinite(m) and m > 0 and prior_volume_valid[t]
                )
                log_ratio = float(np.clip(np.log(v / m), -LOG_CLIP, LOG_CLIP)) if valid_ratio else 0.0
                last_breakout = (t, log_ratio, valid_ratio)
        if last_breakout is not None and t - last_breakout[0] < RANGE_WINDOW:
            ratio[t] = last_breakout[1]
            ratio_valid[t] = float(last_breakout[2])
        elif range_known and close_known:
            ratio_valid[t] = 1.0
        if last_failure is not None and t - last_failure[0] < FAIL_WINDOW:
            flag[t] = last_failure[1]
            flag_valid[t] = 1.0
        else:
            flag_valid[t] = float(range_known and close_known)
    return ratio, ratio_valid, flag, flag_valid


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
    finite_close = pd.Series(np.isfinite(close.to_numpy(dtype=float)), index=prices.index)
    finite_high_low = pd.Series(
        np.isfinite(high.to_numpy(dtype=float)) & np.isfinite(low.to_numpy(dtype=float)), index=prices.index
    )
    finite_volume = pd.Series(np.isfinite(volume.to_numpy(dtype=float)) & volume.ge(0).to_numpy(), index=prices.index)
    valid_volume_window = finite_volume.rolling(r, min_periods=r).sum().eq(r)
    valid_clv_window = np.isfinite(clv).rolling(r, min_periods=r).sum().eq(r)
    valid_close_changes = (finite_close & finite_close.shift(1, fill_value=False)).rolling(
        r, min_periods=r
    ).sum().eq(r)
    valid_short_volume = finite_volume.rolling(SHORT_VOLUME_WINDOW, min_periods=SHORT_VOLUME_WINDOW).sum().eq(
        SHORT_VOLUME_WINDOW
    )
    valid_long_volume = finite_volume.rolling(l_win, min_periods=l_win).sum().eq(l_win)
    valid_range_window = finite_high_low.rolling(r, min_periods=r).sum().eq(r)
    range_available = (
        range_high.notna() & range_low.notna() & np.isfinite(range_high) & np.isfinite(range_low)
        & finite_close & valid_range_window
    )
    positive_atr = pd.Series(np.isfinite(atr) & (atr > 0), index=prices.index)
    position_valid = range_available & np.isfinite(width) & width.gt(0) & np.isfinite(position)
    money_flow_valid = (
        valid_clv_window & valid_volume_window & volume_sum.gt(0) & money_flow.notna() & np.isfinite(money_flow)
    )
    imbalance_valid = (
        valid_close_changes & valid_volume_window & volume_sum.gt(0) & imbalance.notna() & np.isfinite(imbalance)
    )
    short_volume_mean = volume.rolling(SHORT_VOLUME_WINDOW, min_periods=SHORT_VOLUME_WINDOW).mean()
    relative_volume_valid = (
        valid_short_volume & valid_long_volume & short_volume_mean.gt(0) & volume_long.gt(0)
        & relative_volume.notna() & np.isfinite(relative_volume)
    )
    effort_inputs_valid = (
        finite_close & finite_close.shift(r, fill_value=False) & close.shift(r).ne(0)
        & valid_volume_window & valid_long_volume & volume_long.gt(0) & relative_volume_r.notna()
    )
    effort_valid = effort_inputs_valid & effort.notna() & np.isfinite(effort)
    compression_valid = (
        valid_range_window & np.isfinite(width) & width.gt(0) & np.isfinite(width_median) & width_median.gt(0)
        & compression.notna() & np.isfinite(compression)
    )
    range_width = width / close
    range_width_valid = (
        valid_range_window & np.isfinite(range_high) & np.isfinite(range_low)
        & finite_close & close.ne(0) & np.isfinite(range_width)
    )

    prior_volume_mean = volume.rolling(r, min_periods=r).mean().shift(1)
    prior_volume_valid = valid_volume_window.shift(1, fill_value=False).to_numpy(dtype=bool)
    breakout_ratio, breakout_ratio_valid, failed, failed_valid = _breakouts(
        close.to_numpy(float), prior_high.to_numpy(float), prior_low.to_numpy(float),
        volume.to_numpy(float), prior_volume_mean.to_numpy(float), prior_volume_valid,
    )
    failed = pd.Series(failed, index=prices.index)
    failed_valid = pd.Series(failed_valid, index=prices.index)

    calm = (1 - np.tanh(compression)) / 2
    accumulation = pd.concat(
        [(money_flow + 1) / 2, (imbalance + 1) / 2, calm, (failed == 1).astype(float)], axis=1
    ).mean(axis=1, skipna=False)
    distribution = pd.concat(
        [(1 - money_flow) / 2, (1 - imbalance) / 2, calm, (failed == -1).astype(float)], axis=1
    ).mean(axis=1, skipna=False)

    frame = pd.DataFrame(
        {
            "ad_range_width": range_width,
            "ad_range_width_valid": range_width_valid.astype(float),
            "range_position": position,
            "range_position_valid": position_valid.astype(float),
            "ad_money_flow": money_flow,
            "ad_money_flow_valid": money_flow_valid.astype(float),
            "volume_imbalance": imbalance,
            "volume_imbalance_valid": imbalance_valid.astype(float),
            "ad_relative_volume": relative_volume,
            "ad_relative_volume_valid": relative_volume_valid.astype(float),
            "ad_effort_result": effort,
            "ad_effort_result_valid": effort_valid.astype(float),
            "volatility_compression": compression,
            "volatility_compression_valid": compression_valid.astype(float),
            "breakout_volume_ratio": breakout_ratio,
            "breakout_volume_ratio_valid": breakout_ratio_valid,
            "failed_breakout_flag": failed,
            "failed_breakout_flag_valid": failed_valid.astype(float),
            "ad_dist_range_high": dist_high,
            "ad_dist_range_high_valid": (
                range_available & positive_atr & np.isfinite(dist_high)
            ).astype(float),
            "ad_dist_range_low": dist_low,
            "ad_dist_range_low_valid": (
                range_available & positive_atr & np.isfinite(dist_low)
            ).astype(float),
            "accumulation_score": accumulation,
            "accumulation_score_valid": (
                money_flow_valid & imbalance_valid & compression_valid & failed_valid
                & accumulation.notna() & np.isfinite(accumulation)
            ).astype(float),
            "distribution_score": distribution,
            "distribution_score_valid": (
                money_flow_valid & imbalance_valid & compression_valid & failed_valid
                & distribution.notna() & np.isfinite(distribution)
            ).astype(float),
        },
        index=prices.index,
    )
    return frame[list(COLUMNS)]
