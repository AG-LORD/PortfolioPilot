"""Causal pivots and Dow Theory structure features."""

import numpy as np

from app.ml.feature_groups import dow
from app.ml.feature_groups.pivots import HIGH, LOW, SwingTracker, find_pivots, pivots_by_confirmation
from ohlcv_fakes import ohlcv_frame


def zigzag(turns, leg=6):
    """Piecewise-linear closes through the turning points, `leg` bars per leg."""
    path = [turns[0]]
    for a, b in zip(turns, turns[1:]):
        path.extend(np.linspace(a, b, leg + 1)[1:])
    return np.array(path, dtype=float)


def _frame(close):
    return ohlcv_frame(close, high=close * 1.001, low=close * 0.999)


UP = zigzag([100, 110, 105, 115, 110, 120, 115, 125, 120, 130, 125, 135])
DOWN = zigzag([135, 125, 130, 120, 125, 115, 120, 110, 115, 105, 110, 100])


# --- pivots ---------------------------------------------------------------------------


def test_pivot_is_confirmed_k_bars_after_it_occurs():
    close = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3], dtype=float)
    for k in (1, 2, 3):
        highs = [p for p in find_pivots(close, close, k) if p.kind == HIGH]
        assert [(p.occurred, p.confirmed) for p in highs] == [(3, 3 + k)]


def test_pivot_needs_k_bars_on_both_sides_so_the_last_k_bars_are_never_pivots():
    close = np.array([1, 2, 3, 4, 5, 6, 9], dtype=float)  # extreme on the last bar
    assert [p for p in find_pivots(close, close, 2) if p.kind == HIGH] == []


def test_pivot_is_invisible_before_confirmation_and_unchanged_after_more_data():
    close = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3, 4, 5], dtype=float)
    k = 3
    before = find_pivots(close[: 3 + k], close[: 3 + k], k)  # bar 3 + k - 1 is the last bar
    assert [p for p in before if p.kind == HIGH] == []
    at = [p for p in find_pivots(close[: 3 + k + 1], close[: 3 + k + 1], k) if p.kind == HIGH]
    later = [p for p in find_pivots(close, close, k) if p.kind == HIGH]
    assert at == later[:1]


def test_equal_highs_resolve_to_the_earliest_bar():
    close = np.array([1, 2, 5, 3, 5, 2, 1, 1, 1], dtype=float)
    highs = [p.occurred for p in find_pivots(close, close, 2) if p.kind == HIGH]
    assert highs == [2]
    flat = np.array([1, 5, 5, 5, 1, 1], dtype=float)
    assert [p.occurred for p in find_pivots(flat, flat, 1) if p.kind == HIGH] == [1]


def test_flat_prices_have_no_pivots():
    flat = np.full(50, 100.0)
    assert find_pivots(flat, flat, 2) == []


def test_swing_tracker_alternates_and_keeps_the_more_extreme_pivot():
    close = zigzag([100, 110, 105, 112, 104], leg=4)
    pivots = find_pivots(close, close, 2)
    tracker = SwingTracker()
    for bucket in pivots_by_confirmation(pivots, len(close)):
        tracker.add_bar(bucket)
    kinds = [p.kind for p in tracker.swings]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    assert [round(p.price) for p in tracker.swings] == [110, 105, 112]


# --- Dow structure ------------------------------------------------------------------------


def test_uptrend_has_higher_highs_and_higher_lows():
    f = dow.compute(_frame(UP)).iloc[-1]
    assert f["dow_k2_trend"] == 1
    assert f["dow_k2_hh"] > 0 and f["dow_k2_hl"] > 0
    assert f["dow_k2_lh"] == 0 and f["dow_k2_ll"] == 0
    assert f["dow_k2_strength"] == 1
    assert f["dow_k2_run"] > 2
    assert f["dow_k2_has_structure"] == 1


def test_downtrend_has_lower_highs_and_lower_lows():
    f = dow.compute(_frame(DOWN)).iloc[-1]
    assert f["dow_k2_trend"] == -1
    assert f["dow_k2_lh"] > 0 and f["dow_k2_ll"] > 0
    assert f["dow_k2_hh"] == 0 and f["dow_k2_hl"] == 0
    assert f["dow_k2_strength"] == -1
    assert f["dow_k2_run"] < -2


def test_structure_is_not_known_before_pivot_confirmation():
    features = dow.compute(_frame(UP))
    # The first two highs and lows are confirmed only k bars after the 4th turning point.
    fourth_turn = 4 * 6
    assert (features["dow_k2_has_structure"].iloc[: fourth_turn + 2] == 0).all()
    assert features["dow_k2_has_structure"].iloc[fourth_turn + 2] == 1


def test_close_below_last_higher_low_flags_a_break_without_flipping_the_trend():
    close = np.concatenate([UP, np.linspace(UP[-1], 110, 4)[1:]])  # drop below the last low (125)
    features = dow.compute(_frame(close))
    last = features.iloc[-1]
    assert last["dow_k2_break"] == -1
    assert last["dow_k2_trend"] == 1  # no new pivot confirmed yet
    assert last["dow_k2_dist_low"] < 0


def test_counts_only_cover_the_window_and_bars_since_is_capped():
    close = np.concatenate([UP, np.full(200, UP[-1])])  # flat after the trend: no new pivots
    last = dow.compute(_frame(close)).iloc[-1]
    assert last["dow_k2_hh"] == last["dow_k2_hl"] == 0
    assert last["dow_k2_strength"] == 0
    assert last["dow_k2_bars_since"] == dow.WINDOWS[2]


def test_agreement_is_the_mean_trend_across_scales():
    features = dow.compute(_frame(UP))
    expected = features[[f"dow_k{k}_trend" for k in (2, 5, 10)]].mean(axis=1)
    np.testing.assert_allclose(features["dow_trend_agreement"], expected)


def test_flat_prices_give_neutral_finite_features():
    features = dow.compute(_frame(np.full(300, 100.0)))
    assert np.isfinite(features.to_numpy()).all()
    assert (features.filter(like="trend") == 0).all().all()
    assert (features.filter(like="dist") == 0).all().all()
