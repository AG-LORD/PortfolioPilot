"""Dow Theory market structure from confirmed swing pivots (research group "dow").

Per pivot scale k in PIVOT_SCALES (2, 5, 10) with a counting window W
(WINDOWS: 20, 60, 120 trading days), at each bar t using only pivots
confirmed on or before t (pivots.py):

Each confirmed pivot is classified against the previous confirmed pivot of
the same kind: a high is HH (higher) or LH (lower); a low is HL or LL. Equal
prices are "equal" and count as neither. The first pivot of a kind has no
class.

dow_k{k}_trend         +1 if the latest high is HH and the latest low is HL,
                       -1 if LH and LL, else 0 (also 0 before both exist).
dow_k{k}_hh/hl/lh/ll   number of pivots of that class confirmed in (t-W, t].
dow_k{k}_strength      (HH + HL - LH - LL) / (HH + HL + LH + LL) over the
                       same window; 0 when the window has no classified pivot.
dow_k{k}_run           signed length of the current run of bullish (HH/HL,
                       +) or bearish (LH/LL, -) classifications in pivot
                       order; an "equal" pivot resets it to 0; clipped to +-10.
dow_k{k}_dist_high     (close_t - last confirmed swing high) / ATR14_t,
dow_k{k}_dist_low      (close_t - last confirmed swing low) / ATR14_t; 0 when
                       there is no such pivot or ATR is 0/undefined; clipped
                       to +-10.
dow_k{k}_bars_since    bars since the last pivot confirmation, capped at W
                       (W when none yet).
dow_k{k}_break         -1 when the trend is +1 and close_t is below the last
                       confirmed (higher) low; +1 when the trend is -1 and
                       close_t is above the last confirmed (lower) high; else
                       0. A break is a flag only: the trend state changes
                       only when a new pivot is confirmed.
dow_k{k}_has_structure 1 once at least two highs and two lows are confirmed.
dow_k{k}_persistent_state  -1 downtrend, 0 neutral/insufficient confirmed
                       structure, +1 uptrend. Neutral becomes directional only
                       on HH+HL or LH+LL. An established state reverses only
                       after a close breaks its protected HL/LH and a later
                       confirmed opposite structure completes LH+LL or HH+HL,
                       respectively. Both pivots in that structure must occur
                       strictly after the break and be confirmed after it. A
                       pending break is cancelled only by an equally post-break
                       re-establishment of the original complete structure.
dow_k{k}_bars_since_state_change  bars since the most recent directional
                       state establishment or reversal; 0 while neutral.
dow_k{k}_reversal_confirmed  +1 / -1 on the one bar an established down/up
                       state reverses; 0 otherwise. Establishment from neutral
                       is not a reversal.
dow_trend_agreement    mean of the three trend states, in [-1, 1].
"""

import numpy as np
import pandas as pd

from app.ml.feature_groups.pivots import (
    HIGH,
    PIVOT_SCALES,
    Pivot,
    atr_abs,
    clip,
    find_pivots,
    pivots_by_confirmation,
    safe_div,
)

GROUP = "dow"
WINDOWS = {2: 20, 5: 60, 10: 120}
DIST_CLIP = 10.0
RUN_CLIP = 10

HH, LH, HL, LL, EQUAL = "hh", "lh", "hl", "ll", "equal"
BULLISH, BEARISH = {HH, HL}, {LH, LL}
PER_SCALE = (
    "trend", "hh", "hl", "lh", "ll", "strength", "run", "dist_high", "dist_low", "bars_since", "break",
    "has_structure", "persistent_state", "bars_since_state_change", "reversal_confirmed",
)
AGREEMENT = "dow_trend_agreement"
COLUMNS = (*(f"dow_k{k}_{name}" for k in PIVOT_SCALES for name in PER_SCALE), AGREEMENT)


def _classify(price: float, previous: float | None, kind: int) -> str | None:
    if previous is None:
        return None
    if price == previous:
        return EQUAL
    if kind == HIGH:
        return HH if price > previous else LH
    return HL if price > previous else LL


def scale_features(prices: pd.DataFrame, k: int) -> dict[str, np.ndarray]:
    high = prices["high"].to_numpy(dtype=float)
    low = prices["low"].to_numpy(dtype=float)
    close = prices["close"].to_numpy(dtype=float)
    atr = atr_abs(prices)
    n, window = len(close), WINDOWS[k]
    buckets = pivots_by_confirmation(find_pivots(high, low, k), n)

    out = {name: np.zeros(n) for name in PER_SCALE}
    events: list[tuple[int, str]] = []  # (confirmed row, class) of classified pivots
    first_in_window = 0
    last_high = last_low = None  # Pivot
    high_class = low_class = None
    highs_seen = lows_seen = 0
    run = 0
    last_confirmed = None
    persistent_state = 0
    last_state_change = None
    pending_break = 0  # -1: uptrend's protected HL broke; +1: downtrend's protected LH broke
    break_bar = None
    protected_low = protected_high = None

    for t in range(n):
        new_pivots: list[tuple[Pivot, str]] = []
        for p in buckets[t]:
            if p.kind == HIGH:
                cls = _classify(p.price, last_high.price if last_high else None, HIGH)
                last_high, high_class, highs_seen = p, cls, highs_seen + 1
            else:
                cls = _classify(p.price, last_low.price if last_low else None, -1)
                last_low, low_class, lows_seen = p, cls, lows_seen + 1
            last_confirmed = t
            if cls is not None:
                new_pivots.append((p, cls))
                events.append((t, cls))
                sign = 1 if cls in BULLISH else -1 if cls in BEARISH else 0
                run = 0 if sign == 0 else (run + sign if run * sign > 0 else sign)

        while first_in_window < len(events) and events[first_in_window][0] <= t - window:
            first_in_window += 1
        counts = {c: 0 for c in (HH, HL, LH, LL)}
        for _, cls in events[first_in_window:]:
            if cls in counts:
                counts[cls] += 1
        total = sum(counts.values())

        trend = 1 if (high_class == HH and low_class == HL) else -1 if (high_class == LH and low_class == LL) else 0

        def structure_completed_after_break(direction: int) -> bool:
            """Whether the current complete structure formed after the break.

            The second of its two pivots must be confirmed on this bar. Both
            occurrence and confirmation bars must be later than `break_bar`,
            so a pivot formed before the break cannot become reversal evidence
            merely because its confirmation arrives afterwards.
            """
            if break_bar is None or trend != direction or last_high is None or last_low is None:
                return False
            structure_pivots = (last_high, last_low)
            return (
                all(p.occurred > break_bar and p.confirmed > break_bar for p in structure_pivots)
                and any(p is last_high or p is last_low for p, _ in new_pivots)
            )

        # Persistent state is deliberately separate from `trend`: a single
        # contrary swing does not erase an established trend. A close through
        # the protected prior HL/LH starts a pending reversal. It is cancelled
        # only when the original structure is re-established after that break;
        # otherwise a post-break opposite structure must complete before state
        # changes.
        reversal = 0
        if persistent_state == 0:
            if trend == 1:
                persistent_state, last_state_change, protected_low = 1, t, last_low
            elif trend == -1:
                persistent_state, last_state_change, protected_high = -1, t, last_high
        elif persistent_state == 1:
            if pending_break == -1 and structure_completed_after_break(-1):
                persistent_state, last_state_change = -1, t
                reversal, pending_break, break_bar = -1, 0, None
                protected_high, protected_low = last_high, None
            elif pending_break == -1 and structure_completed_after_break(1):
                pending_break, break_bar, protected_low = 0, None, last_low
                if close[t] < protected_low.price:
                    pending_break, break_bar = -1, t
            else:
                if pending_break == 0 and any(cls == HL for _, cls in new_pivots):
                    protected_low = last_low
                if pending_break == 0 and protected_low is not None and close[t] < protected_low.price:
                    pending_break, break_bar = -1, t
        else:  # persistent_state == -1
            if pending_break == 1 and structure_completed_after_break(1):
                persistent_state, last_state_change = 1, t
                reversal, pending_break, break_bar = 1, 0, None
                protected_low, protected_high = last_low, None
            elif pending_break == 1 and structure_completed_after_break(-1):
                pending_break, break_bar, protected_high = 0, None, last_high
                if close[t] > protected_high.price:
                    pending_break, break_bar = 1, t
            else:
                if pending_break == 0 and any(cls == LH for _, cls in new_pivots):
                    protected_high = last_high
                if pending_break == 0 and protected_high is not None and close[t] > protected_high.price:
                    pending_break, break_bar = 1, t

        out["trend"][t] = trend
        for c in (HH, HL, LH, LL):
            out[c][t] = counts[c]
        out["strength"][t] = safe_div(counts[HH] + counts[HL] - counts[LH] - counts[LL], total)
        out["run"][t] = max(min(run, RUN_CLIP), -RUN_CLIP)
        out["dist_high"][t] = clip(safe_div(close[t] - last_high.price, atr[t]), DIST_CLIP) if last_high else 0.0
        out["dist_low"][t] = clip(safe_div(close[t] - last_low.price, atr[t]), DIST_CLIP) if last_low else 0.0
        out["bars_since"][t] = window if last_confirmed is None else min(t - last_confirmed, window)
        if trend == 1 and close[t] < last_low.price:
            out["break"][t] = -1
        elif trend == -1 and close[t] > last_high.price:
            out["break"][t] = 1
        out["has_structure"][t] = 1.0 if highs_seen >= 2 and lows_seen >= 2 else 0.0
        out["persistent_state"][t] = persistent_state
        out["bars_since_state_change"][t] = 0 if last_state_change is None else t - last_state_change
        out["reversal_confirmed"][t] = reversal
    return out


def compute(prices: pd.DataFrame) -> pd.DataFrame:
    data = {}
    for k in PIVOT_SCALES:
        for name, values in scale_features(prices, k).items():
            data[f"dow_k{k}_{name}"] = values
    data[AGREEMENT] = np.mean([data[f"dow_k{k}_trend"] for k in PIVOT_SCALES], axis=0)
    return pd.DataFrame(data, index=prices.index)[list(COLUMNS)]
