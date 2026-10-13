"""Causal pivots and Dow Theory structure features."""

import numpy as np
import pytest

from app.ml.feature_groups import dow
from app.ml.feature_groups.pivots import HIGH, LOW, Pivot, SwingTracker, find_pivots, pivots_by_confirmation
from ohlcv_fakes import ohlcv_frame


def zigzag(turns, leg=6):
    """Piecewise-linear closes through the turning points, `leg` bars per leg."""
    path = [turns[0]]
    for a, b in zip(turns, turns[1:]):
        path.extend(np.linspace(a, b, leg + 1)[1:])
    return np.array(path, dtype=float)


def _frame(close):
    return ohlcv_frame(close, high=close * 1.001, low=close * 0.999)


def _scripted_scale_features(monkeypatch, close, pivots):
    """Run the state machine against explicit causal pivot timestamps."""
    monkeypatch.setattr(dow, "find_pivots", lambda high, low, k: pivots)
    return dow.scale_features(_frame(np.asarray(close, dtype=float)), k=2)


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
    assert f["dow_k2_strength_valid"] == 1
    assert f["dow_k2_dist_high_valid"] == 1
    assert f["dow_k2_dist_low_valid"] == 1


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


def test_persistent_uptrend_starts_only_after_complete_structure_and_then_persists():
    features = dow.compute(_frame(UP))
    state = features["dow_k2_persistent_state"].to_numpy()
    first_up = np.flatnonzero(state == 1)[0]

    assert (state[:first_up] == 0).all()  # no invented state before HH + HL
    assert (state[first_up:] == 1).all()
    assert features["dow_k2_bars_since_state_change"].iloc[first_up] == 0
    assert features["dow_k2_bars_since_state_change"].iloc[first_up + 1] == 1
    assert features["dow_k2_bars_since_state_change"].iloc[-1] == len(features) - 1 - first_up
    assert (features["dow_k2_reversal_confirmed"] == 0).all()


def test_persistent_downtrend_starts_only_after_complete_structure_and_then_persists():
    features = dow.compute(_frame(DOWN))
    state = features["dow_k2_persistent_state"].to_numpy()
    first_down = np.flatnonzero(state == -1)[0]

    assert (state[:first_down] == 0).all()  # no invented state before LH + LL
    assert (state[first_down:] == -1).all()
    assert features["dow_k2_bars_since_state_change"].iloc[first_down] == 0
    assert (features["dow_k2_reversal_confirmed"] == 0).all()


def test_persistent_uptrend_survives_a_break_until_opposite_structure_is_confirmed():
    close = np.concatenate([UP, np.linspace(UP[-1], 110, 4)[1:]])
    features = dow.compute(_frame(close))

    assert features["dow_k2_break"].iloc[-1] == -1
    assert features["dow_k2_persistent_state"].iloc[-1] == 1
    assert (features["dow_k2_reversal_confirmed"] == 0).all()


def test_persistent_state_reverses_only_after_break_and_later_confirmed_opposite_pivot():
    # The close first breaks the protected higher low (125). The low at 110
    # and then lower high at 120 are confirmed later, completing LH + LL.
    reversal = zigzag([UP[-1], 110, 120, 100, 105])
    close = np.concatenate([UP, reversal[1:]])
    features = dow.compute(_frame(close))
    event = np.flatnonzero(features["dow_k2_reversal_confirmed"].to_numpy() == -1)

    assert len(event) == 1
    reversal_bar = event[0]
    first_up = np.flatnonzero(features["dow_k2_persistent_state"].to_numpy() == 1)[0]
    assert (features["dow_k2_persistent_state"].iloc[first_up:reversal_bar] == 1).all()
    assert (features["dow_k2_persistent_state"].iloc[reversal_bar:] == -1).all()
    assert features["dow_k2_bars_since_state_change"].iloc[reversal_bar] == 0
    assert features["dow_k2_bars_since_state_change"].iloc[reversal_bar + 1] == 1


def test_newer_higher_low_replaces_the_protected_level(monkeypatch):
    # The close at bar 12 is below the newer HL (65) but above the superseded
    # HL (60). It must therefore start a pending reversal and permit the
    # later, fully post-break LH + LL structure to reverse the state.
    pivots = [
        Pivot(HIGH, 0, 2, 100), Pivot(LOW, 1, 3, 50),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 60),  # establish HH + HL
        Pivot(LOW, 8, 10, 65), Pivot(HIGH, 9, 11, 120),  # refresh to HL 65
        Pivot(HIGH, 13, 15, 115), Pivot(LOW, 14, 16, 55),  # post-break LH + LL
    ]
    close = np.full(18, 100.0)
    close[12] = 62.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][12] == 1
    assert features["reversal_confirmed"][16] == -1
    assert features["persistent_state"][16] == -1


def test_newer_lower_high_replaces_the_protected_level(monkeypatch):
    # Mirror: 108 is above the newer LH (105) but below the superseded LH
    # (110), so only the refreshed protected level starts the reversal.
    pivots = [
        Pivot(HIGH, 0, 2, 120), Pivot(LOW, 1, 3, 80),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 70),  # establish LH + LL
        Pivot(HIGH, 8, 10, 105), Pivot(LOW, 9, 11, 60),  # refresh to LH 105
        Pivot(HIGH, 13, 15, 110), Pivot(LOW, 14, 16, 65),  # post-break HH + HL
    ]
    close = np.full(18, 100.0)
    close[12] = 108.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][12] == -1
    assert features["reversal_confirmed"][16] == 1
    assert features["persistent_state"][16] == 1


def test_pivot_formed_before_break_cannot_confirm_a_later_reversal(monkeypatch):
    # The LL occurs at bar 6, before the break at bar 7, but is confirmed at
    # bar 8. It completes LH + LL after the break only in hindsight, so it is
    # not eligible evidence for the persistent-state transition.
    pivots = [
        Pivot(HIGH, 0, 2, 100), Pivot(LOW, 1, 3, 50),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 60),  # establish HH + HL
        Pivot(HIGH, 5, 7, 105), Pivot(LOW, 6, 8, 55),  # LH then pre-break LL
    ]
    close = np.full(10, 100.0)
    close[7] = 59.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][8] == 1
    assert features["reversal_confirmed"][8] == 0


def test_reestablished_structure_cancels_stale_break_and_allows_later_new_reversal(monkeypatch):
    # A break at 7 is cancelled by post-break HH + HL at 10/11. Later LH +
    # LL alone cannot consume that stale break. A second close break at 16,
    # followed by a wholly post-break LH + LL, is a valid new reversal.
    pivots = [
        Pivot(HIGH, 0, 2, 100), Pivot(LOW, 1, 3, 50),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 60),  # establish HH + HL
        Pivot(LOW, 8, 10, 65), Pivot(HIGH, 9, 11, 120),  # cancel pending break
        Pivot(HIGH, 12, 14, 115), Pivot(LOW, 13, 15, 64),  # no new close break
        Pivot(HIGH, 17, 19, 110), Pivot(LOW, 18, 20, 55),  # valid new LH + LL
    ]
    close = np.full(22, 100.0)
    close[7] = 59.0
    close[16] = 60.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][11] == 1
    assert features["persistent_state"][15] == 1
    assert (features["reversal_confirmed"][:20] == 0).all()
    assert features["reversal_confirmed"][20] == -1
    assert features["persistent_state"][20] == -1


def test_recovery_bar_can_start_a_fresh_uptrend_break(monkeypatch):
    # HH + HL at bar 11 cancels the old break from bar 7, but that same bar
    # closes below the refreshed HL (65). It starts a new break, so only the
    # later wholly post-11 LH + LL structure reverses the state.
    pivots = [
        Pivot(HIGH, 0, 2, 100), Pivot(LOW, 1, 3, 50),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 60),
        Pivot(LOW, 8, 10, 65), Pivot(HIGH, 9, 11, 120),
        Pivot(HIGH, 12, 14, 115), Pivot(LOW, 13, 15, 55),
    ]
    close = np.full(17, 100.0)
    close[7] = 59.0
    close[11] = 64.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][11] == 1
    assert (features["reversal_confirmed"][:15] == 0).all()
    assert features["reversal_confirmed"][15] == -1
    assert features["persistent_state"][15] == -1


def test_recovery_bar_can_start_a_fresh_downtrend_break(monkeypatch):
    # Mirror: LH + LL at bar 11 cancels the old break, but the same close is
    # above the refreshed LH (105), creating a new pending bullish reversal.
    pivots = [
        Pivot(HIGH, 0, 2, 120), Pivot(LOW, 1, 3, 80),
        Pivot(HIGH, 2, 4, 110), Pivot(LOW, 3, 5, 70),
        Pivot(HIGH, 8, 10, 105), Pivot(LOW, 9, 11, 60),
        Pivot(HIGH, 12, 14, 110), Pivot(LOW, 13, 15, 65),
    ]
    close = np.full(17, 100.0)
    close[7] = 111.0
    close[11] = 106.0
    features = _scripted_scale_features(monkeypatch, close, pivots)

    assert features["persistent_state"][11] == -1
    assert (features["reversal_confirmed"][:15] == 0).all()
    assert features["reversal_confirmed"][15] == 1
    assert features["persistent_state"][15] == 1


def test_persistent_state_is_neutral_with_insufficient_history_or_flat_prices():
    for close in (UP[: 4 * 6 + 2], np.full(300, 100.0)):
        features = dow.compute(_frame(close))
        assert (features["dow_k2_persistent_state"] == 0).all()
        assert (features["dow_k2_bars_since_state_change"] == 0).all()
        assert (features["dow_k2_reversal_confirmed"] == 0).all()


def test_persistent_state_is_truncation_invariant():
    reversal = zigzag([UP[-1], 110, 120, 100, 105])
    close = np.concatenate([UP, reversal[1:]])
    full = dow.compute(_frame(close))
    cutoff = len(close) - 8
    truncated = dow.compute(_frame(close[:cutoff]))
    columns = ["dow_k2_persistent_state", "dow_k2_bars_since_state_change", "dow_k2_reversal_confirmed"]
    np.testing.assert_array_equal(truncated[columns].to_numpy(), full.iloc[:cutoff][columns].to_numpy())


def test_persistent_state_is_future_data_invariant():
    reversal = zigzag([UP[-1], 110, 120, 100, 105])
    close = np.concatenate([UP, reversal[1:]])
    prices = _frame(close)
    shocked = prices.copy()
    cutoff = len(UP) + 4
    shocked.iloc[cutoff + 1 :, :4] *= 0.6
    base = dow.compute(prices).iloc[: cutoff + 1]
    changed = dow.compute(shocked).iloc[: cutoff + 1]
    columns = ["dow_k2_persistent_state", "dow_k2_bars_since_state_change", "dow_k2_reversal_confirmed"]
    np.testing.assert_array_equal(base[columns].to_numpy(), changed[columns].to_numpy())


def test_counts_only_cover_the_window_and_bars_since_is_capped():
    close = np.concatenate([UP, np.full(200, UP[-1])])  # flat after the trend: no new pivots
    last = dow.compute(_frame(close)).iloc[-1]
    assert last["dow_k2_hh"] == last["dow_k2_hl"] == 0
    assert last["dow_k2_strength"] == 0
    assert last["dow_k2_strength_valid"] == 0
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
    for k in dow.PIVOT_SCALES:
        assert (features[f"dow_k{k}_strength_valid"] == 0).all()
        assert (features[f"dow_k{k}_dist_high_valid"] == 0).all()
        assert (features[f"dow_k{k}_dist_low_valid"] == 0).all()


def test_dow_validity_is_false_when_history_has_no_confirmed_pivots():
    features = dow.compute(_frame(np.full(12, 100.0)))
    for k in dow.PIVOT_SCALES:
        assert (features[f"dow_k{k}_strength_valid"] == 0).all()
        assert (features[f"dow_k{k}_dist_high_valid"] == 0).all()
        assert (features[f"dow_k{k}_dist_low_valid"] == 0).all()


@pytest.mark.parametrize(
    ("case", "expected_valid"),
    [
        ("valid", 1.0),
        ("nan_close", 0.0),
        ("inf_close", 0.0),
        ("zero_atr", 0.0),
        ("nan_atr", 0.0),
        ("inf_atr", 0.0),
    ],
)
def test_dow_distance_validity_requires_finite_close_and_positive_finite_atr(
    monkeypatch, case, expected_valid
):
    n = 40
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    pivots = [Pivot(HIGH, 5, 7, 110.0), Pivot(LOW, 10, 12, 90.0)]
    monkeypatch.setattr(dow, "find_pivots", lambda high, low, k: pivots)

    if case == "nan_close":
        close[-1] = np.nan
    elif case == "inf_close":
        close[-1] = np.inf
    elif case == "zero_atr":
        high[:] = close
        low[:] = close
    elif case == "nan_atr":
        high[-1] = np.nan
    elif case == "inf_atr":
        high[-1] = np.inf

    prices = ohlcv_frame(close, high=high, low=low)
    features = dow.scale_features(prices, k=2)
    row = -1

    assert features["dist_high_valid"][row] == expected_valid
    assert features["dist_low_valid"][row] == expected_valid
    if expected_valid:
        assert features["dist_high"][row] == pytest.approx(-5.0)
        assert features["dist_low"][row] == pytest.approx(5.0)
    else:
        assert features["dist_high"][row] == 0
        assert features["dist_low"][row] == 0
