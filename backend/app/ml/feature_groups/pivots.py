"""Causal swing-pivot detection shared by the structure, pattern and geometry groups.

Fractal pivot of order k (k fixed per scale, PIVOT_SCALES):
- bar i is a pivot HIGH if high[i] is strictly greater than each of the k
  bars before it and greater than or equal to each of the k bars after it;
- bar i is a pivot LOW if low[i] is strictly less than each of the k bars
  before it and less than or equal to each of the k bars after it.
Ties: among equal extremes inside a window the EARLIEST bar is the pivot
(strict on the left, non-strict on the right), so the result is deterministic.

A pivot OCCURS at bar i but is CONFIRMED only at bar i + k, when the k later
bars have closed. Features at bar t may use only pivots with confirmed <= t.
Because k is constant, pivots are confirmed in order of occurrence.

The alternating swing sequence (high, low, high, ...) used by the pattern and
geometry groups is built from confirmed pivots in confirmation order: a new
pivot of the same kind as the last one replaces it only if it is more
extreme (strictly higher high or strictly lower low); a bar that is both a
pivot high and a pivot low adds the kind that alternates with the sequence.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.features import ATR_WINDOW, wilder_smooth

HIGH = 1
LOW = -1

# Pivot orders for the short, medium and long scales; fixed before evaluation.
PIVOT_SCALES = (2, 5, 10)


@dataclass(frozen=True)
class Pivot:
    kind: int  # HIGH or LOW
    occurred: int  # row position of the extreme bar
    confirmed: int  # occurred + k: first row at which it may be used
    price: float


def find_pivots(high: np.ndarray, low: np.ndarray, k: int) -> list[Pivot]:
    """All pivots of order k, sorted by (confirmed, kind high-first)."""
    n = len(high)
    pivots = []
    for i in range(k, n - k):
        left_h, right_h = high[i - k : i], high[i + 1 : i + k + 1]
        if high[i] > left_h.max() and high[i] >= right_h.max():
            pivots.append(Pivot(HIGH, i, i + k, float(high[i])))
        left_l, right_l = low[i - k : i], low[i + 1 : i + k + 1]
        if low[i] < left_l.min() and low[i] <= right_l.min():
            pivots.append(Pivot(LOW, i, i + k, float(low[i])))
    return pivots


class SwingTracker:
    """Incrementally maintained alternating swing sequence (see module docstring)."""

    def __init__(self):
        self.swings: list[Pivot] = []

    def add(self, pivot: Pivot) -> None:
        if not self.swings:
            self.swings.append(pivot)
            return
        last = self.swings[-1]
        if pivot.kind != last.kind:
            self.swings.append(pivot)
        elif (pivot.kind == HIGH and pivot.price > last.price) or (pivot.kind == LOW and pivot.price < last.price):
            self.swings[-1] = pivot

    def add_bar(self, pivots_at_bar: list[Pivot]) -> None:
        """Add the pivots confirmed on one bar; with both kinds, the one that
        alternates with the current sequence goes first."""
        if len(pivots_at_bar) > 1 and self.swings:
            pivots_at_bar = sorted(pivots_at_bar, key=lambda p: p.kind == self.swings[-1].kind)
        for p in pivots_at_bar:
            self.add(p)


def pivots_by_confirmation(pivots: list[Pivot], n: int) -> list[list[Pivot]]:
    """bucket[t] = pivots confirmed exactly at row t."""
    buckets: list[list[Pivot]] = [[] for _ in range(n)]
    for p in pivots:
        if p.confirmed < n:
            buckets[p.confirmed].append(p)
    return buckets


def atr_abs(prices: pd.DataFrame, window: int = ATR_WINDOW) -> np.ndarray:
    """Wilder ATR in price units (features.atr divides by close)."""
    high, low, close = prices["high"], prices["low"], prices["close"]
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1, skipna=False
    )
    return wilder_smooth(true_range, window).to_numpy(dtype=float)


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return default
    return numerator / denominator


def clip(value: float, bound: float) -> float:
    return float(min(max(value, -bound), bound))
