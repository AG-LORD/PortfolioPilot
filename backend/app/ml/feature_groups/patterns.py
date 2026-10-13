"""Rule-based geometric chart patterns from confirmed swings (research group "patterns").

Patterns are read from the alternating swing sequence of pivot scale k = 5
(pivots.py), so a pattern can only be DETECTED on the bar its last required
pivot is confirmed (k bars after that pivot occurred). From then on it is a
CANDIDATE until either:
- a CLOSE beyond its breakout level on bar t CONFIRMS it (breakout bar = t);
- a close beyond its invalidation level cancels it; or
- MAX_PENDING bars pass without a breakout (expired).
A confirmed pattern stays visible for CONFIRMED_HOLD bars. Nothing about a
later breakout or outcome is visible before the bar on which it happens.

Tolerances are in ATR14 units at the detection bar, so "equal" adapts to each
stock's own daily range instead of a universal percentage: two swing prices
within EQUAL_TOL = 0.5 ATR are treated as equal (half a typical day's range is
within normal noise); a pattern must be at least MIN_HEIGHT = 2 ATR tall to
stand out from noise; it must span MIN_WIDTH..MAX_WIDTH = 10..120 bars.
These values are fixed before evaluation and are not tuned on test data.

Patterns (S = swings, oldest first; H = swing high, L = swing low):
double_top        H1 L H2: |H1 - H2| <= tol; min(H1, H2) - L >= min height.
                  Breaks DOWN below L; invalid above max(H1, H2).
double_bottom     mirror of double_top.
head_shoulders    H1 L1 H2 L2 H3: head H2 above both shoulders by >= tol;
                  |H1 - H3| <= 2 tol; H2 - max(L1, L2) >= min height.
                  Neckline through L1 and L2; breaks DOWN below the
                  neckline's value at t; invalid above H2.
inv_head_shoulders mirror of head_shoulders.
asc_triangle      last two highs equal (<= tol) and last two lows rising
                  (>= tol). Breaks UP above the higher high; invalid below
                  the last low.
desc_triangle     mirror: lows equal, highs falling; breaks DOWN.
sym_triangle      highs falling and lows rising (each by >= tol). Breaks UP
                  above the resistance line or DOWN below the support line
                  (lines through the two highs / two lows, value at t);
                  invalid never (expires instead).
range             last two highs equal and last two lows equal (<= tol),
                  height >= min height. Breaks UP above the higher high or
                  DOWN below the lower low.
Bull/bear flags are not implemented: a flag needs a "pole" (a sharp prior
move) whose size and speed we could not define without tuning thresholds on
the same data the ablation evaluates.

Per pattern P:
pat_{P}_state      0 none, 1 candidate, 2 confirmed breakout.
pat_{P}_age        bars since detection / 60, clipped to [0, 2]; 0 when none.
pat_{P}_boundary   (close_t - breakout level at t) / ATR14_t, clipped +-10
                   (for two-sided patterns: the nearer level); 0 when none.
pat_{P}_confidence mean of the criteria margins in [0, 1] (how far inside
                   each tolerance the geometry is); 0 when none.
For the most recently detected active pattern of any type:
pat_height         pattern height / ATR at detection, clipped [0, 30].
pat_width          bars from first to last swing / 60, clipped [0, 3].
pat_symmetry       min/max of the two compared swing legs, in [0, 1].
pat_swing_diff     (second compared extreme - first) / ATR, clipped +-5.
pat_completeness   candidate: share of the way from the last swing to the
                   breakout level, in [0, 1]; 1 once confirmed.
pat_breakout_dir   +1 / -1 for a confirmed upward / downward breakout, else 0.
pat_active_count   number of patterns currently candidate or confirmed.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.feature_groups.pivots import (
    HIGH,
    LOW,
    Pivot,
    SwingTracker,
    atr_abs,
    clip,
    find_pivots,
    pivots_by_confirmation,
    safe_div,
)

GROUP = "patterns"
SWING_SCALE = 5
EQUAL_TOL = 0.5
MIN_HEIGHT = 2.0
MIN_WIDTH = 10
MAX_WIDTH = 120
MAX_PENDING = 40
CONFIRMED_HOLD = 20
CLIP = 10.0

PATTERNS = (
    "double_top",
    "double_bottom",
    "head_shoulders",
    "inv_head_shoulders",
    "asc_triangle",
    "desc_triangle",
    "sym_triangle",
    "range",
)
PER_PATTERN = ("state", "age", "boundary", "confidence")
SUMMARY = ("pat_height", "pat_width", "pat_symmetry", "pat_swing_diff", "pat_completeness", "pat_breakout_dir", "pat_active_count")
COLUMNS = (*(f"pat_{p}_{c}" for p in PATTERNS for c in PER_PATTERN), *SUMMARY)

CANDIDATE, CONFIRMED = 1, 2


@dataclass
class Detection:
    """A pattern found on bar `detected`. Levels are functions of the bar so
    sloped necklines and trendlines are evaluated at t, never fitted later."""

    pattern: str
    detected: int
    start: int  # occurrence bar of its first swing
    up_level: object  # callable(t) -> price, or None
    down_level: object
    invalid_above: float | None
    invalid_below: float | None
    height: float  # price units
    width: int
    symmetry: float
    swing_diff: float  # price units
    confidence: float
    origin: float  # price of the last swing, for completeness
    state: int = CANDIDATE
    breakout: int | None = None
    direction: int = 0


def _flat(level):
    return lambda t: level


def _line(a: Pivot, b: Pivot):
    slope = safe_div(b.price - a.price, b.occurred - a.occurred)
    return lambda t: b.price + slope * (t - b.occurred)


def _margin(value: float, limit: float) -> float:
    """1 at the ideal, 0 at the tolerance limit."""
    return max(0.0, 1.0 - safe_div(value, limit, default=1.0))


def _ratio(a: float, b: float) -> float:
    a, b = abs(a), abs(b)
    return safe_div(min(a, b), max(a, b))


def _detect(swings: list[Pivot], t: int, atr: float) -> list[Detection]:
    if not np.isfinite(atr) or atr <= 0:
        return []
    tol, min_h = EQUAL_TOL * atr, MIN_HEIGHT * atr
    found = []

    def width_ok(first: Pivot, last: Pivot) -> bool:
        return MIN_WIDTH <= last.occurred - first.occurred <= MAX_WIDTH

    def height_score(height: float) -> float:
        return min(height / (2 * min_h), 1.0)

    if len(swings) >= 3:
        a, b, c = swings[-3:]
        if a.kind == HIGH and width_ok(a, c):
            height = min(a.price, c.price) - b.price
            if abs(a.price - c.price) <= tol and height >= min_h:
                found.append(Detection(
                    "double_top", t, a.occurred, None, _flat(b.price), max(a.price, c.price), None, height,
                    c.occurred - a.occurred, _ratio(a.price - b.price, c.price - b.price), c.price - a.price,
                    (_margin(abs(a.price - c.price), tol) + height_score(height)) / 2, c.price,
                ))
        if a.kind == LOW and width_ok(a, c):
            height = b.price - max(a.price, c.price)
            if abs(a.price - c.price) <= tol and height >= min_h:
                found.append(Detection(
                    "double_bottom", t, a.occurred, _flat(b.price), None, None, min(a.price, c.price), height,
                    c.occurred - a.occurred, _ratio(b.price - a.price, b.price - c.price), c.price - a.price,
                    (_margin(abs(a.price - c.price), tol) + height_score(height)) / 2, c.price,
                ))

    if len(swings) >= 5:
        s1, s2, s3, s4, s5 = swings[-5:]
        if s1.kind == HIGH and width_ok(s1, s5):
            head_margin = s3.price - max(s1.price, s5.price)
            height = s3.price - max(s2.price, s4.price)
            if head_margin >= tol and abs(s1.price - s5.price) <= 2 * tol and height >= min_h:
                found.append(Detection(
                    "head_shoulders", t, s1.occurred, None, _line(s2, s4), s3.price, None, height,
                    s5.occurred - s1.occurred,
                    _ratio(s1.price - s2.price, s5.price - s4.price) * _ratio(s3.occurred - s1.occurred, s5.occurred - s3.occurred),
                    s5.price - s1.price,
                    (_margin(abs(s1.price - s5.price), 2 * tol) + min(head_margin / (2 * tol), 1.0) + height_score(height)) / 3,
                    s5.price,
                ))
        if s1.kind == LOW and width_ok(s1, s5):
            head_margin = min(s1.price, s5.price) - s3.price
            height = min(s2.price, s4.price) - s3.price
            if head_margin >= tol and abs(s1.price - s5.price) <= 2 * tol and height >= min_h:
                found.append(Detection(
                    "inv_head_shoulders", t, s1.occurred, _line(s2, s4), None, None, s3.price, height,
                    s5.occurred - s1.occurred,
                    _ratio(s2.price - s1.price, s4.price - s5.price) * _ratio(s3.occurred - s1.occurred, s5.occurred - s3.occurred),
                    s5.price - s1.price,
                    (_margin(abs(s1.price - s5.price), 2 * tol) + min(head_margin / (2 * tol), 1.0) + height_score(height)) / 3,
                    s5.price,
                ))

    if len(swings) >= 4 and width_ok(swings[-4], swings[-1]):
        last4 = swings[-4:]
        h1, h2 = [p for p in last4 if p.kind == HIGH]
        l1, l2 = [p for p in last4 if p.kind == LOW]
        dh, dl = h2.price - h1.price, l2.price - l1.price
        height = max(h1.price, h2.price) - min(l1.price, l2.price)
        width = swings[-1].occurred - swings[-4].occurred
        symmetry = _ratio(h2.occurred - h1.occurred, l2.occurred - l1.occurred)
        common = dict(detected=t, start=swings[-4].occurred, height=height, width=width, symmetry=symmetry, origin=swings[-1].price)
        if abs(dh) <= tol and dl >= tol and height >= min_h:
            found.append(Detection(
                pattern="asc_triangle", up_level=_flat(max(h1.price, h2.price)), down_level=None, invalid_above=None,
                invalid_below=l2.price, swing_diff=dl, confidence=(_margin(abs(dh), tol) + min(dl / (2 * tol), 1.0)) / 2,
                **common,
            ))
        if abs(dl) <= tol and dh <= -tol and height >= min_h:
            found.append(Detection(
                pattern="desc_triangle", up_level=None, down_level=_flat(min(l1.price, l2.price)), invalid_above=h2.price,
                invalid_below=None, swing_diff=dh, confidence=(_margin(abs(dl), tol) + min(-dh / (2 * tol), 1.0)) / 2, **common,
            ))
        if dh <= -tol and dl >= tol and height >= min_h:
            found.append(Detection(
                pattern="sym_triangle", up_level=_line(h1, h2), down_level=_line(l1, l2), invalid_above=None,
                invalid_below=None, swing_diff=dl + dh, confidence=(min(-dh / (2 * tol), 1.0) + min(dl / (2 * tol), 1.0)) / 2,
                **common,
            ))
        if abs(dh) <= tol and abs(dl) <= tol and height >= min_h:
            found.append(Detection(
                pattern="range", up_level=_flat(max(h1.price, h2.price)), down_level=_flat(min(l1.price, l2.price)),
                invalid_above=None, invalid_below=None, swing_diff=dh,
                confidence=(_margin(abs(dh), tol) + _margin(abs(dl), tol) + height_score(height)) / 3, **common,
            ))
    return found


def _boundary(d: Detection, t: int, close: float, atr: float) -> float:
    distances = []
    if d.up_level is not None:
        distances.append(close - d.up_level(t))
    if d.down_level is not None:
        distances.append(close - d.down_level(t))
    nearest = min(distances, key=abs)
    return clip(safe_div(nearest, atr), CLIP)


def _completeness(d: Detection, t: int, close: float) -> float:
    if d.state == CONFIRMED:
        return 1.0
    shares = []
    for level in (d.up_level, d.down_level):
        if level is not None:
            span = level(t) - d.origin
            shares.append(min(max(safe_div(close - d.origin, span), 0.0), 1.0))
    return max(shares) if shares else 0.0


def compute(prices: pd.DataFrame) -> pd.DataFrame:
    high = prices["high"].to_numpy(dtype=float)
    low = prices["low"].to_numpy(dtype=float)
    close = prices["close"].to_numpy(dtype=float)
    atr = atr_abs(prices)
    n = len(close)
    data = {c: np.zeros(n) for c in COLUMNS}
    buckets = pivots_by_confirmation(find_pivots(high, low, SWING_SCALE), n)
    tracker = SwingTracker()
    active: dict[str, Detection] = {}

    for t in range(n):
        if buckets[t]:
            tracker.add_bar(buckets[t])
            for d in _detect(tracker.swings, t, atr[t]):
                active[d.pattern] = d  # a new detection replaces an older one of the same type

        for name in list(active):
            d = active[name]
            if d.state == CANDIDATE:
                up = d.up_level is not None and close[t] > d.up_level(t)
                down = d.down_level is not None and close[t] < d.down_level(t)
                if up or down:
                    d.state, d.breakout, d.direction = CONFIRMED, t, 1 if up else -1
                elif (d.invalid_above is not None and close[t] > d.invalid_above) or (
                    d.invalid_below is not None and close[t] < d.invalid_below
                ) or t - d.detected >= MAX_PENDING:
                    del active[name]
            elif t - d.breakout >= CONFIRMED_HOLD:
                del active[name]

        for name, d in active.items():
            data[f"pat_{name}_state"][t] = d.state
            data[f"pat_{name}_age"][t] = min((t - d.detected) / 60, 2.0)
            data[f"pat_{name}_boundary"][t] = _boundary(d, t, close[t], atr[t])
            data[f"pat_{name}_confidence"][t] = d.confidence
        if active:
            latest = max(active.values(), key=lambda d: (d.detected, PATTERNS.index(d.pattern)))
            atr_at = atr[latest.detected]
            data["pat_height"][t] = min(max(safe_div(latest.height, atr_at), 0.0), 30.0)
            data["pat_width"][t] = min(latest.width / 60, 3.0)
            data["pat_symmetry"][t] = latest.symmetry
            data["pat_swing_diff"][t] = clip(safe_div(latest.swing_diff, atr_at), 5.0)
            data["pat_completeness"][t] = _completeness(latest, t, close[t])
            data["pat_breakout_dir"][t] = latest.direction
            data["pat_active_count"][t] = len(active)

    return pd.DataFrame(data, index=prices.index)[list(COLUMNS)]
