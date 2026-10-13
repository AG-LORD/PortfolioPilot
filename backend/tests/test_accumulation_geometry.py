"""Accumulation/distribution scores and geometric measurements."""

import math

import numpy as np
import pytest

from app.ml.feature_groups import accumulation, geometry
from ohlcv_fakes import ohlcv_frame, random_ohlcv
from test_dow_structure import zigzag

WARM = 260  # past every window used by these groups


# --- accumulation / distribution ------------------------------------------------------


def test_scores_and_bounded_features_stay_in_range():
    f = accumulation.compute(random_ohlcv(600, seed=1)).iloc[WARM:]
    for column in ("accumulation_score", "distribution_score", "range_position"):
        assert f[column].between(0, 1).all()
    for column in ("ad_money_flow", "volume_imbalance", "failed_breakout_flag", "ad_effort_result"):
        assert f[column].between(-1, 1).all()
    for column in ("ad_relative_volume", "volatility_compression", "breakout_volume_ratio"):
        assert f[column].abs().max() <= accumulation.LOG_CLIP
    assert f["ad_dist_range_high"].between(0, accumulation.DIST_CLIP).all()


def test_zero_volume_and_flat_prices_give_finite_neutral_values():
    flat = ohlcv_frame(np.full(400, 100.0), high=np.full(400, 100.0), low=np.full(400, 100.0), volume=np.zeros(400))
    f = accumulation.compute(flat).iloc[WARM:]
    assert np.isfinite(f.to_numpy()).all()
    assert (f["range_position"] == 0.5).all()
    assert (f[["ad_money_flow", "volume_imbalance", "ad_relative_volume", "breakout_volume_ratio"]] == 0).all().all()


def test_buying_pressure_raises_accumulation_over_distribution():
    rng = np.random.default_rng(0)
    n = 400
    close = 100 + rng.normal(0, 0.3, n).cumsum() * 0.1
    up = np.r_[False, np.diff(close) > 0]
    volume = np.where(up, 3000.0, 1000.0)  # heavier volume on up closes
    frame = ohlcv_frame(close, high=close + 0.5, low=close - 0.5, volume=volume)
    frame["close"] = frame["high"] - 0.1  # closes near the high: positive money flow
    f = accumulation.compute(frame).iloc[WARM:]
    assert (f["volume_imbalance"] > 0).mean() > 0.9
    assert (f["accumulation_score"] > f["distribution_score"]).mean() > 0.9


def test_failed_upside_breakout_is_flagged_on_the_bar_it_returns_inside():
    close = np.full(300, 100.0)
    close[260:262] = 105.0  # closes above the prior 20-bar high...
    close[262] = 100.05  # ...and back below that level (inside the range) two bars later
    frame = ohlcv_frame(close, high=close * 1.001, low=close * 0.999)
    f = accumulation.compute(frame)
    flag = f["failed_breakout_flag"]
    assert (flag.iloc[:262] == 0).all()
    assert (flag.iloc[262 : 262 + accumulation.FAIL_WINDOW] == -1).all()
    assert flag.iloc[262 + accumulation.FAIL_WINDOW] == 0
    assert f["breakout_volume_ratio"].iloc[260] == 0  # equal volume: log ratio 0


def test_breakout_volume_ratio_measures_the_breakout_bar():
    close = np.full(300, 100.0)
    close[270] = 106.0
    volume = np.full(300, 1000.0)
    volume[270] = 4000.0
    f = accumulation.compute(ohlcv_frame(close, high=close * 1.001, low=close * 0.999, volume=volume))
    assert f["breakout_volume_ratio"].iloc[275] == pytest.approx(math.log(4))
    assert f["breakout_volume_ratio"].iloc[269] == 0


def test_tight_range_reads_as_volatility_compression():
    rng = np.random.default_rng(2)
    wide = 100 + rng.normal(0, 2, 280)
    tight = 100 + rng.normal(0, 0.2, 40)
    close = np.r_[wide, tight]
    f = accumulation.compute(ohlcv_frame(close, high=close + 0.1, low=close - 0.1))
    assert f["volatility_compression"].iloc[-1] < -1


# --- geometry -------------------------------------------------------------------------------


def test_straight_log_trend_has_positive_slope_unit_r2_and_no_acceleration():
    rng = np.random.default_rng(3)
    log_close = np.log(100) + 0.004 * np.arange(300) + rng.normal(0, 0.002, 300)
    f = geometry.compute(ohlcv_frame(np.exp(log_close))).iloc[WARM:]
    assert (f["geo_slope_20"] > 3).all()
    assert f["geo_r2_60"].min() > 0.99
    assert abs(f["geo_accel_60"].mean()) < 1  # noise-sized, while the slope is far larger


def test_accelerating_trend_has_positive_acceleration():
    t = np.arange(300)
    rng = np.random.default_rng(4)
    close = np.exp(np.log(100) + 1e-5 * t**2 + rng.normal(0, 0.003, 300))
    assert geometry.compute(ohlcv_frame(close))["geo_accel_60"].iloc[-1] > 0


def test_flat_prices_give_zero_not_nan():
    f = geometry.compute(ohlcv_frame(np.full(300, 100.0))).iloc[WARM:]
    assert np.isfinite(f.to_numpy()).all()
    assert (f[["geo_slope_20", "geo_accel_60", "geo_efficiency_20", "geo_has_swings", "geo_r2_20"]] == 0).all().all()


def test_swing_legs_ratios_and_symmetry():
    # Up 20, down 10, up 20 (equal 6-bar legs), then flat at the last high.
    close = np.r_[zigzag([100, 120, 110, 130, 120, 140], leg=12), np.full(30, 140.0)]
    frame = ohlcv_frame(close, high=close * 1.0005, low=close * 0.9995)
    f = geometry.compute(frame).iloc[-1]
    assert f["geo_has_swings"] == 1
    # Last swings: high 130 (S3), low 120 (S2), high 140 (S1) (scale 5 pivots).
    assert f["geo_leg_ratio"] == pytest.approx(math.log(20 / 10), abs=0.01)
    assert f["geo_duration_ratio"] == pytest.approx(0, abs=1e-9)
    assert f["geo_leg_symmetry"] == pytest.approx(0.5, abs=0.01)
    assert f["geo_retracement"] == pytest.approx(0, abs=0.01)  # close is back at S1


def test_converging_lines_read_as_convergence():
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 0.05, 400)
    close = np.r_[100 + noise[:200], zigzag([100, 130, 105, 125, 110, 120, 113], leg=12)]
    f = geometry.compute(ohlcv_frame(close, high=close * 1.0005, low=close * 0.9995))
    assert f["geo_convergence"].iloc[-1] > 0


def test_fibonacci_distance_is_bounded_and_defaults_to_one_without_swings():
    flat = geometry.compute_fibonacci(ohlcv_frame(np.full(300, 100.0)))
    assert (flat["fib_nearest_dist"] == 1).all()
    noisy = geometry.compute_fibonacci(random_ohlcv(400, seed=6)).iloc[WARM:]
    assert noisy["fib_nearest_dist"].between(0, 2).all()


def test_outside_bar_that_is_both_swing_high_and_low_does_not_break_leg_ratios():
    # Bar 30 has the highest high AND the lowest low of its neighbourhood.
    rng = np.random.default_rng(8)
    close = 100 + rng.normal(0, 0.2, 300)
    high, low = close + 0.3, close - 0.3
    for bar in (30, 130, 230):
        high[bar], low[bar] = close[bar] + 6, close[bar] - 6
    f = geometry.compute(ohlcv_frame(close, high=high, low=low))
    assert np.isfinite(f.iloc[WARM:].to_numpy()).all()
