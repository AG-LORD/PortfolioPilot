"""Geometric descriptions of the price path (research groups "geometry" and "fibonacci").

Descriptive measurements only; whether any of them helps forecasting is what
the ablation tests. Prices enter as log closes, and distances are divided by
volatility or ATR, so every feature is comparable across stocks and
unchanged when all prices are multiplied by a constant.

sigma_t = std of daily log returns over the last 60 bars (ddof 1). Any
feature whose denominator (sigma, ATR, a leg length) is 0 or undefined is 0.

Rolling fits (w = 20 and 60 bars, x = 0..w-1, y = log close over the window):
geo_slope_{w}      linear slope * sqrt(w) / sigma (fitted move over the window
                   in units of its expected random-walk size), clipped +-10.
geo_r2_{w}         R^2 of that linear fit, in [0, 1]; 0 for a flat window.
geo_accel_{w}      quadratic coefficient * w^2 / (sigma * sqrt(w)), clipped +-10.
geo_slope_change   geo_slope_20 now minus 10 bars ago, clipped +-10.
geo_curvature      (5-bar log return - the 5-bar log return before it) /
                   (sigma * sqrt(5)), a second difference, clipped +-10.
geo_efficiency_{w} |log close_t - log close_{t-w}| / sum of |daily log
                   changes| over w, in [0, 1] (Kaufman efficiency ratio).

From the alternating swings of scale k = 5 (pivots.py; confirmed pivots only),
with S1 the latest swing, S2 and S3 the ones before it:
geo_has_swings     1 once three swings exist (else every swing feature is 0).
geo_retracement    (close_t - S1) / (S2 - S1): how far the move since S1 has
                   gone back over the leg S2 -> S1, clipped to [-1, 2].
geo_leg_ratio      log(|S1 - S2| / |S2 - S3|), clipped +-3.
geo_duration_ratio log(bars S2 -> S1 / bars S3 -> S2), clipped +-3.
geo_leg_symmetry   min/max of the two leg sizes times min/max of their
                   durations, in [0, 1].
geo_leg_height     |S1 - S2| / ATR14_t, clipped to [0, 30].
geo_leg_width      bars S2 -> S1 / 60, clipped to [0, 3].
Trendlines through the last two swing highs (resistance) and the last two
swing lows (support), in log price against bar position:
geo_convergence    (support slope - resistance slope) * 20 / sigma, clipped
                   +-10; positive means the lines converge.
geo_dist_resistance (resistance line at t - close_t) / ATR14_t, clipped +-10.
geo_dist_support    (close_t - support line at t) / ATR14_t, clipped +-10.

Fibonacci (separate group, descriptive only; not assumed predictive):
fib_nearest_dist   |geo_retracement - nearest of 0.382, 0.5, 0.618|; 1 when
                   there are no swings.
"""

import math

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from app.ml.feature_groups.pivots import (
    HIGH,
    SwingTracker,
    atr_abs,
    clip,
    find_pivots,
    pivots_by_confirmation,
    safe_div,
)

GROUP = "geometry"
FIB_GROUP = "fibonacci"
FIT_WINDOWS = (20, 60)
SIGMA_WINDOW = 60
EFFICIENCY_WINDOWS = (20, 60)
SWING_SCALE = 5
CLIP = 10.0
LOG_CLIP = 3.0
FIB_LEVELS = (0.382, 0.5, 0.618)

COLUMNS = (
    *(f"geo_slope_{w}" for w in FIT_WINDOWS),
    *(f"geo_r2_{w}" for w in FIT_WINDOWS),
    *(f"geo_accel_{w}" for w in FIT_WINDOWS),
    "geo_slope_change",
    "geo_curvature",
    *(f"geo_efficiency_{w}" for w in EFFICIENCY_WINDOWS),
    "geo_has_swings",
    "geo_retracement",
    "geo_leg_ratio",
    "geo_duration_ratio",
    "geo_leg_symmetry",
    "geo_leg_height",
    "geo_leg_width",
    "geo_convergence",
    "geo_dist_resistance",
    "geo_dist_support",
)
FIB_COLUMNS = ("fib_nearest_dist",)


def _rolling_fits(y: np.ndarray, w: int):
    """(linear slope, R^2, quadratic coefficient) per bar; NaN before w bars.
    Each window is fitted on its own values only (einsum row by row)."""
    n = len(y)
    slope = np.full(n, np.nan)
    r2 = np.full(n, np.nan)
    quad = np.full(n, np.nan)
    if n < w:
        return slope, r2, quad
    x = np.arange(w, dtype=float)
    xc = x - x.mean()
    windows = sliding_window_view(y, w)
    linear = np.einsum("ij,j->i", windows, xc) / (xc @ xc)
    centered = windows - windows.mean(axis=1, keepdims=True)
    total = np.einsum("ij,ij->i", centered, centered)
    residual = centered - linear[:, None] * xc[None, :]
    rss = np.einsum("ij,ij->i", residual, residual)
    with np.errstate(divide="ignore", invalid="ignore"):
        fit = np.where(total > 0, 1 - rss / total, 0.0)
    pinv = np.linalg.pinv(np.vstack([np.ones(w), x, x**2]).T)
    quadratic = np.einsum("ij,j->i", windows, pinv[2])
    slope[w - 1 :], r2[w - 1 :], quad[w - 1 :] = linear, np.clip(fit, 0, 1), quadratic
    return slope, r2, quad


def _scaled(values: np.ndarray, scale: np.ndarray, bound: float = CLIP) -> np.ndarray:
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values) & np.isfinite(scale)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[ok] = np.where(scale[ok] > 0, np.clip(values[ok] / scale[ok], -bound, bound), 0.0)
    return out


def _path_features(prices: pd.DataFrame) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """(features, sigma)."""
    log_close = np.log(prices["close"].to_numpy(dtype=float))
    daily = pd.Series(log_close).diff()
    sigma = daily.rolling(SIGMA_WINDOW, min_periods=SIGMA_WINDOW).std(ddof=1).to_numpy()
    out = {}
    for w in FIT_WINDOWS:
        slope, r2, quad = _rolling_fits(log_close, w)
        out[f"geo_slope_{w}"] = _scaled(slope * math.sqrt(w), sigma)
        out[f"geo_r2_{w}"] = np.where(np.isfinite(sigma), r2, np.nan)
        out[f"geo_accel_{w}"] = _scaled(quad * w**2, sigma * math.sqrt(w))
    slope_20 = out["geo_slope_20"]
    change = np.full(len(slope_20), np.nan)
    change[10:] = slope_20[10:] - slope_20[:-10]
    out["geo_slope_change"] = np.clip(change, -CLIP, CLIP)
    r5 = pd.Series(log_close).diff(5).to_numpy()
    second = np.full(len(r5), np.nan)
    second[5:] = r5[5:] - r5[:-5]
    out["geo_curvature"] = _scaled(second, sigma * math.sqrt(5))
    absolute = daily.abs()
    for w in EFFICIENCY_WINDOWS:
        net = pd.Series(log_close).diff(w).abs().to_numpy()
        path = absolute.rolling(w, min_periods=w).sum().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            eff = np.where(path > 0, net / path, 0.0)
        out[f"geo_efficiency_{w}"] = np.where(np.isfinite(path), np.clip(eff, 0, 1), np.nan)
    return out, sigma


def _line_at(a, b, t: int) -> float:
    """Log-price line through swings a and b (by occurrence bar), evaluated at bar t."""
    slope = safe_div(math.log(b.price) - math.log(a.price), b.occurred - a.occurred)
    return math.log(b.price) + slope * (t - b.occurred), slope


def _swing_features(prices: pd.DataFrame, sigma: np.ndarray) -> dict[str, np.ndarray]:
    high = prices["high"].to_numpy(dtype=float)
    low = prices["low"].to_numpy(dtype=float)
    close = prices["close"].to_numpy(dtype=float)
    atr = atr_abs(prices)
    n = len(close)
    names = (
        "geo_has_swings", "geo_retracement", "geo_leg_ratio", "geo_duration_ratio", "geo_leg_symmetry",
        "geo_leg_height", "geo_leg_width", "geo_convergence", "geo_dist_resistance", "geo_dist_support",
    )
    out = {name: np.zeros(n) for name in names}
    buckets = pivots_by_confirmation(find_pivots(high, low, SWING_SCALE), n)
    tracker = SwingTracker()
    for t in range(n):
        tracker.add_bar(buckets[t])
        swings = tracker.swings
        if len(swings) < 3:
            continue
        s3, s2, s1 = swings[-3:]
        leg1, leg2 = s1.price - s2.price, s2.price - s3.price
        d1, d2 = s1.occurred - s2.occurred, s2.occurred - s3.occurred
        out["geo_has_swings"][t] = 1.0
        out["geo_retracement"][t] = min(max(safe_div(close[t] - s1.price, s2.price - s1.price), -1.0), 2.0)
        # A bar that is both a swing high and a swing low gives a zero-length leg.
        if leg1 and leg2 and d1 > 0 and d2 > 0:
            out["geo_leg_ratio"][t] = clip(math.log(abs(leg1) / abs(leg2)), LOG_CLIP)
            out["geo_leg_symmetry"][t] = (min(abs(leg1), abs(leg2)) / max(abs(leg1), abs(leg2))) * (
                min(d1, d2) / max(d1, d2)
            )
        if d1 > 0 and d2 > 0:
            out["geo_duration_ratio"][t] = clip(math.log(d1 / d2), LOG_CLIP)
        out["geo_leg_height"][t] = min(max(safe_div(abs(leg1), atr[t]), 0.0), 30.0)
        out["geo_leg_width"][t] = min(d1 / 60, 3.0)

        highs = [p for p in swings if p.kind == HIGH][-2:]
        lows = [p for p in swings if p.kind != HIGH][-2:]
        if len(highs) == 2 and len(lows) == 2:
            res_t, res_slope = _line_at(highs[0], highs[1], t)
            sup_t, sup_slope = _line_at(lows[0], lows[1], t)
            if np.isfinite(sigma[t]) and sigma[t] > 0:
                out["geo_convergence"][t] = clip((sup_slope - res_slope) * 20 / sigma[t], CLIP)
            out["geo_dist_resistance"][t] = clip(safe_div(math.exp(res_t) - close[t], atr[t]), CLIP)
            out["geo_dist_support"][t] = clip(safe_div(close[t] - math.exp(sup_t), atr[t]), CLIP)
    return out


def compute(prices: pd.DataFrame) -> pd.DataFrame:
    path, sigma = _path_features(prices)
    data = {**path, **_swing_features(prices, sigma)}
    return pd.DataFrame(data, index=prices.index)[list(COLUMNS)]


def compute_fibonacci(prices: pd.DataFrame) -> pd.DataFrame:
    _, sigma = _path_features(prices)
    swings = _swing_features(prices, sigma)
    retracement = swings["geo_retracement"]
    nearest = np.min([np.abs(retracement - level) for level in FIB_LEVELS], axis=0)
    values = np.where(swings["geo_has_swings"] == 1, nearest, 1.0)
    return pd.DataFrame({"fib_nearest_dist": values}, index=prices.index)
