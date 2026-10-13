"""Geometric chart patterns: constraints, causal detection and breakout confirmation."""

import numpy as np
import pytest

from app.ml.feature_groups import patterns
from ohlcv_fakes import ohlcv_frame
from test_dow_structure import zigzag

LEG = 12
K = patterns.SWING_SCALE


def shape(turns, mirror=False):
    """A smooth, pivot-free 40-bar run-up to the first turn, then the zigzag."""
    lead = np.linspace(turns[0] - 5, turns[0], 40)[:-1]
    close = np.r_[lead, zigzag(turns, leg=LEG)]
    if mirror:
        close = 200 - close
    return close


def compute(close):
    return patterns.compute(ohlcv_frame(close, high=close + 0.05, low=close - 0.05))


def turn_bar(i):
    """Bar index of turning point i in shape()."""
    return 39 + i * LEG


def first(mask):
    hits = np.flatnonzero(np.asarray(mask))
    return int(hits[0]) if len(hits) else None


def assert_detected_then_confirmed(f, name, last_turn, close, crosses):
    state = f[f"pat_{name}_state"].to_numpy()
    detect = turn_bar(last_turn) + K  # the last swing is confirmed K bars after it occurs
    assert (state[:detect] == 0).all(), "visible before its last pivot was confirmed"
    assert state[detect] == 1
    breakout = first(crosses(close) & (np.arange(len(close)) > detect))
    assert (state[detect:breakout] == 1).all(), "confirmed before the breakout close"
    assert state[breakout] == 2
    return breakout


def test_double_top_waits_for_the_second_top_and_confirms_on_the_close_below_the_neckline():
    close = shape([95, 110, 100, 110, 92])
    f = compute(close)
    breakout = assert_detected_then_confirmed(f, "double_top", 3, close, lambda c: c < 100)
    assert f["pat_breakout_dir"].iloc[breakout] == -1
    assert f["pat_completeness"].iloc[breakout] == 1
    assert 0 < f["pat_double_top_confidence"].iloc[breakout] <= 1
    assert f["pat_height"].iloc[breakout] > patterns.MIN_HEIGHT


def test_double_bottom_is_the_mirror_and_breaks_up():
    close = shape([95, 110, 100, 110, 92], mirror=True)
    f = compute(close)
    breakout = assert_detected_then_confirmed(f, "double_bottom", 3, close, lambda c: c > 100)
    assert f["pat_breakout_dir"].iloc[breakout] == 1


def test_unequal_tops_are_not_a_double_top():
    f = compute(shape([95, 110, 100, 116, 92]))
    assert (f["pat_double_top_state"] == 0).all()


def test_head_and_shoulders_needs_a_higher_head_and_breaks_the_neckline():
    close = shape([95, 108, 100, 115, 100, 108, 94])
    f = compute(close)
    assert_detected_then_confirmed(f, "head_shoulders", 5, close, lambda c: c < 100)
    flat_head = compute(shape([95, 108, 100, 108.2, 100, 108, 94]))
    assert (flat_head["pat_head_shoulders_state"] == 0).all()


def test_inverse_head_and_shoulders_breaks_up():
    close = shape([95, 108, 100, 115, 100, 108, 94], mirror=True)
    assert_detected_then_confirmed(compute(close), "inv_head_shoulders", 5, close, lambda c: c > 100)


def test_ascending_triangle_flat_highs_rising_lows_breaks_up():
    close = shape([95, 110, 100, 110, 104, 114])
    f = compute(close)
    assert_detected_then_confirmed(f, "asc_triangle", 4, close, lambda c: c > 110)
    assert (f["pat_sym_triangle_state"] == 0).all()


def test_descending_triangle_is_the_mirror_and_breaks_down():
    close = shape([95, 110, 100, 110, 104, 114], mirror=True)
    assert_detected_then_confirmed(compute(close), "desc_triangle", 4, close, lambda c: c < 90)


def test_symmetrical_triangle_breaks_through_its_sloped_line():
    close = shape([95, 115, 100, 111, 104, 110])  # slow last leg: crosses after detection
    f = compute(close)
    detect = turn_bar(4) + K
    state = f["pat_sym_triangle_state"].to_numpy()
    assert state[detect] == 1
    # Resistance through (turn 1, 115) and (turn 3, 111), evaluated at each bar.
    slope = (111 - 115) / (2 * LEG)
    resistance = 111 + slope * (np.arange(len(close)) - turn_bar(3))
    breakout = first((close > resistance) & (np.arange(len(close)) > detect))
    assert (state[detect:breakout] == 1).all()
    assert state[breakout] == 2
    assert f["pat_breakout_dir"].iloc[breakout] == 1
    assert (f["pat_asc_triangle_state"] == 0).all() and (f["pat_range_state"] == 0).all()


def test_range_with_equal_highs_and_lows_breaks_either_way():
    close = shape([95, 110, 100, 110, 100, 113])
    assert_detected_then_confirmed(compute(close), "range", 4, close, lambda c: c > 110)


def test_close_beyond_the_invalidation_level_cancels_the_candidate():
    close = shape([95, 110, 100, 110, 106, 118])  # back above both tops, no neckline break
    state = compute(close)["pat_double_top_state"].to_numpy()
    detect = turn_bar(3) + K
    assert state[detect] == 1
    above = first((close > 110) & (np.arange(len(close)) > turn_bar(4)))
    assert state[above] == 0


def test_candidate_expires_without_a_breakout_and_confirmed_state_is_held_then_cleared():
    close = np.r_[shape([95, 110, 100, 110, 104]), np.full(80, 104.0)]
    state = compute(close)["pat_double_top_state"].to_numpy()
    detect = turn_bar(3) + K
    assert (state[detect : detect + patterns.MAX_PENDING] == 1).all()
    assert state[detect + patterns.MAX_PENDING] == 0

    close = np.r_[shape([95, 110, 100, 110, 92]), np.full(60, 92.0)]
    state = compute(close)["pat_double_top_state"].to_numpy()
    breakout = first(state == 2)
    assert (state[breakout : breakout + patterns.CONFIRMED_HOLD] == 2).all()
    assert state[breakout + patterns.CONFIRMED_HOLD] == 0


def test_future_bars_never_change_earlier_pattern_features():
    close = shape([95, 110, 100, 110, 92])
    f = compute(close)
    for cutoff in range(turn_bar(3), len(close)):
        truncated = compute(close[:cutoff])
        np.testing.assert_array_equal(truncated.to_numpy(), f.iloc[:cutoff].to_numpy())


@pytest.mark.parametrize("name", patterns.PATTERNS)
def test_no_pattern_on_flat_prices(name):
    f = compute(np.full(300, 100.0))
    assert (f[f"pat_{name}_state"] == 0).all()
    assert np.isfinite(f.to_numpy()).all()
