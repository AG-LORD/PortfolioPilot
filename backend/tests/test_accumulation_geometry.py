"""Accumulation/distribution scores and geometric measurements."""

import math

import numpy as np
import pytest

from app.ml.feature_groups import accumulation, geometry
from app.ml.feature_groups.pivots import HIGH, LOW, Pivot
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
    for column in (
        "range_position_valid",
        "ad_money_flow_valid",
        "volume_imbalance_valid",
        "ad_relative_volume_valid",
        "ad_effort_result_valid",
        "volatility_compression_valid",
        "ad_dist_range_high_valid",
        "ad_dist_range_low_valid",
        "accumulation_score_valid",
        "distribution_score_valid",
    ):
        assert (f[column] == 0).all()


@pytest.mark.parametrize("bad_volume", [0.0, np.nan, -1.0])
def test_breakout_ratio_is_invalid_when_breakout_volume_is_unavailable(bad_volume):
    close = np.full(300, 100.0)
    close[270] = 110.0
    volume = np.full(300, 1000.0)
    volume[270] = bad_volume
    frame = ohlcv_frame(close, high=close, low=close, volume=volume)
    f = accumulation.compute(frame)
    assert f["breakout_volume_ratio"].iloc[270] == 0
    assert f["breakout_volume_ratio_valid"].iloc[270] == 0


def test_breakout_ratio_is_invalid_when_baseline_volume_window_has_missing_input():
    close = np.full(300, 100.0)
    close[270] = 110.0
    volume = np.full(300, 1000.0)
    volume[250] = np.nan
    f = accumulation.compute(ohlcv_frame(close, high=close, low=close, volume=volume))
    assert f["breakout_volume_ratio"].iloc[270] == 0
    assert f["breakout_volume_ratio_valid"].iloc[270] == 0


def test_accumulation_flags_reject_missing_current_or_historical_inputs():
    close = np.full(320, 100.0)
    close[270] = np.nan
    close[240] = np.nan
    frame = ohlcv_frame(close, high=np.full(320, 101.0), low=np.full(320, 99.0), volume=np.full(320, 1000.0))
    f = accumulation.compute(frame)

    for name in (
        "ad_money_flow",
        "volume_imbalance",
        "ad_effort_result",
        "accumulation_score",
        "distribution_score",
    ):
        assert not np.isfinite(f[name].iloc[270])
        assert f[f"{name}_valid"].iloc[270] == 0
    assert f["breakout_volume_ratio"].iloc[270] == 0
    assert f["breakout_volume_ratio_valid"].iloc[270] == 0
    assert f["failed_breakout_flag"].iloc[270] == 0
    assert f["failed_breakout_flag_valid"].iloc[270] == 0
    assert f["ad_money_flow_valid"].iloc[259] == 0
    assert f["volume_imbalance_valid"].iloc[259] == 0
    assert f["ad_effort_result_valid"].iloc[260] == 0  # close[t - R] is missing
    assert f["range_position_valid"].iloc[270] == 0
    assert f["ad_dist_range_high_valid"].iloc[270] == 0
    assert f["ad_dist_range_low_valid"].iloc[270] == 0


def test_accumulation_flags_reject_invalid_volume_and_unavailable_ranges():
    close = np.full(320, 100.0)
    volume = np.full(320, 1000.0)
    volume[270] = np.nan
    high = np.full(320, 101.0)
    low = np.full(320, 99.0)
    high[279] = np.nan
    frame = ohlcv_frame(close, high=high, low=low, volume=volume)
    f = accumulation.compute(frame)

    assert f["ad_money_flow_valid"].iloc[270] == 0
    assert f["volume_imbalance_valid"].iloc[270] == 0
    assert f["ad_effort_result_valid"].iloc[270] == 0
    assert f["accumulation_score_valid"].iloc[270] == 0
    assert f["distribution_score_valid"].iloc[270] == 0
    assert f["range_position_valid"].iloc[280] == 0
    assert f["ad_dist_range_high_valid"].iloc[280] == 0
    assert f["ad_dist_range_low_valid"].iloc[280] == 0
    assert f["breakout_volume_ratio_valid"].iloc[280] == 0
    assert f["failed_breakout_flag_valid"].iloc[280] == 0


def test_accumulation_validity_marks_defined_range_and_volume_features():
    f = accumulation.compute(random_ohlcv(400, seed=12)).iloc[WARM:]
    for column in (
        "range_position_valid",
        "ad_money_flow_valid",
        "volume_imbalance_valid",
        "ad_relative_volume_valid",
        "ad_effort_result_valid",
        "volatility_compression_valid",
        "breakout_volume_ratio_valid",
        "failed_breakout_flag_valid",
        "ad_dist_range_high_valid",
        "ad_dist_range_low_valid",
        "accumulation_score_valid",
        "distribution_score_valid",
    ):
        assert f[column].eq(1).all()


def test_zero_width_range_keeps_midpoint_fallback_but_marks_position_invalid():
    flat = ohlcv_frame(
        np.full(300, 100.0),
        high=np.full(300, 100.0),
        low=np.full(300, 100.0),
        volume=np.full(300, 1000.0),
    )
    f = accumulation.compute(flat)
    assert (f["range_position"].iloc[accumulation.RANGE_WINDOW - 1 :] == 0.5).all()
    assert (f["range_position_valid"] == 0).all()
    assert (f["volatility_compression_valid"] == 0).all()


@pytest.mark.parametrize("bad_close", [np.nan, np.inf, 0.0])
def test_range_width_is_invalid_when_current_close_is_unusable(bad_close):
    close = np.full(200, 100.0)
    close[-1] = bad_close
    frame = ohlcv_frame(
        close,
        high=np.full(200, 101.0),
        low=np.full(200, 99.0),
        volume=np.full(200, 1000.0),
    )
    f = accumulation.compute(frame)

    assert f["ad_range_width_valid"].iloc[-1] == 0


def test_range_width_is_invalid_when_rolling_range_is_unavailable():
    close = np.full(200, 100.0)
    high = np.full(200, 101.0)
    high[-1] = np.nan
    frame = ohlcv_frame(close, high=high, low=np.full(200, 99.0), volume=np.full(200, 1000.0))
    f = accumulation.compute(frame)

    assert f["ad_range_width_valid"].iloc[-1] == 0


def test_zero_width_range_is_a_valid_zero_range_width():
    frame = ohlcv_frame(
        np.full(200, 100.0),
        high=np.full(200, 100.0),
        low=np.full(200, 100.0),
        volume=np.full(200, 1000.0),
    )
    f = accumulation.compute(frame)

    assert f["ad_range_width"].iloc[-1] == 0
    assert f["ad_range_width_valid"].iloc[-1] == 1


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
    assert f["breakout_volume_ratio_valid"].iloc[260] == 1


@pytest.mark.parametrize(
    ("return_age", "expected_flag"),
    [
        (accumulation.FAIL_WINDOW - 1, -1.0),
        (accumulation.FAIL_WINDOW, -1.0),
        (accumulation.FAIL_WINDOW + 1, 0.0),
    ],
)
def test_pending_breakout_expires_by_elapsed_bars_across_missing_closes(return_age, expected_flag):
    return_bar = 1 + return_age
    close = np.full(return_bar + accumulation.FAIL_WINDOW + 1, 95.0)
    close[1] = 101.0
    close[2:return_bar] = np.nan
    close[return_bar] = 99.0
    prior_high = np.full(len(close), 100.0)
    prior_low = np.full(len(close), 90.0)
    volume = np.full(len(close), 1000.0)
    prior_volume_mean = np.full(len(close), 1000.0)
    prior_volume_valid = np.ones(len(close), dtype=bool)

    _, _, failed, failed_valid = accumulation._breakouts(
        close, prior_high, prior_low, volume, prior_volume_mean, prior_volume_valid
    )

    assert failed[return_bar] == expected_flag
    assert failed_valid[return_bar] == 1
    if expected_flag:
        assert (failed[return_bar : return_bar + accumulation.FAIL_WINDOW] == -1).all()
        assert failed[return_bar + accumulation.FAIL_WINDOW] == 0
    else:
        assert (failed[return_bar:] == 0).all()


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
    for column in (
        "geo_slope_20_valid",
        "geo_r2_20_valid",
        "geo_accel_60_valid",
        "geo_curvature_valid",
        "geo_efficiency_20_valid",
        "geo_retracement_valid",
        "geo_convergence_valid",
        "geo_dist_resistance_valid",
        "geo_dist_support_valid",
    ):
        assert (f[column] == 0).all()


def test_r2_is_valid_with_a_complete_window_before_volatility_warmup():
    close = np.exp(np.linspace(4.0, 4.2, 30))
    f = geometry.compute(ohlcv_frame(close))

    assert np.isnan(f["geo_r2_20"].iloc[18])
    assert f["geo_r2_20"].iloc[19] == pytest.approx(1.0)
    assert f["geo_r2_20_valid"].iloc[19] == 1
    assert f["geo_slope_20_valid"].iloc[19] == 0


def test_r2_remains_invalid_for_flat_or_incomplete_windows():
    flat = geometry.compute(ohlcv_frame(np.full(25, 100.0)))
    flat_row = flat.iloc[19]
    assert flat_row["geo_r2_20"] == 0
    assert flat_row["geo_r2_20_valid"] == 0

    close = np.exp(np.linspace(4.0, 4.2, 25))
    close[12] = np.nan
    incomplete = geometry.compute(ohlcv_frame(close))
    assert np.isnan(incomplete["geo_r2_20"].iloc[19])
    assert incomplete["geo_r2_20_valid"].iloc[19] == 0


def test_geometry_validity_is_false_before_required_history():
    f = geometry.compute(ohlcv_frame(np.full(40, 100.0)))
    assert (f["geo_slope_20_valid"] == 0).all()
    assert (f["geo_r2_20_valid"] == 0).all()
    assert (f["geo_efficiency_20_valid"] == 0).all()
    assert (f["geo_retracement_valid"] == 0).all()


def test_zero_swing_leg_makes_retracement_invalid(monkeypatch):
    pivots = [
        Pivot(HIGH, 5, 10, 105),
        Pivot(LOW, 15, 20, 100),
        Pivot(HIGH, 25, 30, 100),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    f = geometry.compute(ohlcv_frame(np.full(50, 100.0)))
    assert f["geo_has_swings"].iloc[30] == 1
    assert f["geo_retracement"].iloc[30] == 0
    assert f["geo_retracement_valid"].iloc[30] == 0
    assert f["geo_leg_ratio_valid"].iloc[30] == 0


def test_coincident_pivot_occurrences_keep_price_features_valid(monkeypatch):
    pivots = [
        Pivot(HIGH, 10, 15, 110),
        Pivot(LOW, 20, 25, 100),
        Pivot(HIGH, 20, 25, 120),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    f = geometry.compute(ohlcv_frame(np.full(50, 100.0)))
    row = f.iloc[25]

    assert row["geo_leg_ratio"] == pytest.approx(math.log(2))
    assert row["geo_leg_ratio_valid"] == 1
    assert row["geo_duration_ratio_valid"] == 0
    assert row["geo_leg_symmetry"] == 0
    assert row["geo_leg_symmetry_valid"] == 1
    assert row["geo_leg_width"] == 0
    assert row["geo_leg_width_valid"] == 1


def test_zero_price_leg_invalidates_log_ratio_but_allows_defined_zero_outputs(monkeypatch):
    pivots = [
        Pivot(HIGH, 5, 10, 110),
        Pivot(LOW, 15, 20, 100),
        Pivot(HIGH, 25, 30, 100),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    f = geometry.compute(ohlcv_frame(np.full(50, 100.0)))
    row = f.iloc[30]

    assert row["geo_leg_ratio"] == 0
    assert row["geo_leg_ratio_valid"] == 0
    assert row["geo_retracement_valid"] == 0
    assert row["geo_leg_symmetry"] == 0
    assert row["geo_leg_symmetry_valid"] == 1
    assert row["geo_leg_height"] == 0
    assert row["geo_leg_height_valid"] == 1


def test_missing_close_invalidates_geometry_features_that_need_it(monkeypatch):
    pivots = [
        Pivot(HIGH, 5, 10, 110),
        Pivot(LOW, 15, 20, 100),
        Pivot(HIGH, 25, 30, 120),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    close = np.full(50, 100.0)
    close[30] = np.nan
    f = geometry.compute(ohlcv_frame(close))
    row = f.iloc[30]

    assert row["geo_has_swings"] == 1
    assert row["geo_retracement"] == 0
    assert row["geo_retracement_valid"] == 0
    assert row["geo_leg_ratio_valid"] == 1
    assert row["geo_leg_width_valid"] == 1


def test_convergence_is_invalid_when_dispersion_is_zero(monkeypatch):
    pivots = [
        Pivot(HIGH, 5, 10, 105),
        Pivot(LOW, 15, 20, 95),
        Pivot(HIGH, 25, 30, 110),
        Pivot(LOW, 35, 40, 100),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    f = geometry.compute(ohlcv_frame(np.full(50, 100.0)))
    assert f["geo_convergence"].iloc[40] == 0
    assert f["geo_convergence_valid"].iloc[40] == 0


@pytest.mark.parametrize("bad_pivot_price", [0.0, np.inf])
def test_trendline_features_reject_nonpositive_or_nonfinite_pivots(monkeypatch, bad_pivot_price):
    pivots = [
        Pivot(HIGH, 5, 10, bad_pivot_price),
        Pivot(LOW, 15, 20, 95),
        Pivot(HIGH, 25, 30, 110),
        Pivot(LOW, 35, 40, 100),
    ]
    monkeypatch.setattr(geometry, "find_pivots", lambda high, low, k: pivots)
    close = np.linspace(100, 110, 80)
    f = geometry.compute(ohlcv_frame(close))
    row = f.iloc[40]

    for name in ("geo_convergence", "geo_dist_resistance", "geo_dist_support"):
        assert row[name] == 0
        assert row[f"{name}_valid"] == 0


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
    assert f["geo_retracement_valid"] == 1
    assert f["geo_leg_ratio_valid"] == 1
    assert f["geo_duration_ratio_valid"] == 1
    assert f["geo_leg_symmetry_valid"] == 1


def test_converging_lines_read_as_convergence():
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 0.05, 400)
    close = np.r_[100 + noise[:200], zigzag([100, 130, 105, 125, 110, 120, 113], leg=12)]
    f = geometry.compute(ohlcv_frame(close, high=close * 1.0005, low=close * 0.9995))
    assert f["geo_convergence"].iloc[-1] > 0
    assert f["geo_convergence_valid"].iloc[-1] == 1


def test_fibonacci_distance_is_bounded_and_defaults_to_one_without_swings():
    flat = geometry.compute_fibonacci(ohlcv_frame(np.full(300, 100.0)))
    assert (flat["fib_nearest_dist"] == 1).all()
    assert (flat["fib_nearest_dist_valid"] == 0).all()
    noisy = geometry.compute_fibonacci(random_ohlcv(400, seed=6)).iloc[WARM:]
    assert noisy["fib_nearest_dist"].between(0, 2).all()
    assert noisy["fib_nearest_dist_valid"].eq(1).all()


def test_outside_bar_that_is_both_swing_high_and_low_does_not_break_leg_ratios():
    # Bar 30 has the highest high AND the lowest low of its neighbourhood.
    rng = np.random.default_rng(8)
    close = 100 + rng.normal(0, 0.2, 300)
    high, low = close + 0.3, close - 0.3
    for bar in (30, 130, 230):
        high[bar], low[bar] = close[bar] + 6, close[bar] - 6
    f = geometry.compute(ohlcv_frame(close, high=high, low=low))
    assert np.isfinite(f.iloc[WARM:].to_numpy()).all()
