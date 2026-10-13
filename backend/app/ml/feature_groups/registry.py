"""Registry of feature groups and the feature configurations built from them.

A group's compute(prices) takes one ticker's OHLCV frame (prices_to_frame,
indexed by trading date, ascending) and returns a frame with exactly the
group's columns on the same index. Every value at date t may depend only on
rows dated <= t. Values before MIN_FEATURE_HISTORY rows may be NaN (warm-up);
from there on every column must be finite, so every configuration is scored
on the same panel rows.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from app.services.features import FEATURE_COLUMNS, compute_features

TECHNICAL = "technical"
# The configuration the live model uses; reproduces the original 12 columns.
DEFAULT_GROUPS: tuple[str, ...] = (TECHNICAL,)


@dataclass(frozen=True)
class FeatureGroup:
    name: str
    columns: tuple[str, ...]
    compute: Callable[[pd.DataFrame], pd.DataFrame]


def _technical(prices: pd.DataFrame) -> pd.DataFrame:
    return compute_features(prices).reindex(prices.index)


_GROUPS: dict[str, FeatureGroup] = {
    TECHNICAL: FeatureGroup(TECHNICAL, tuple(FEATURE_COLUMNS), _technical),
}


def register(group: FeatureGroup) -> None:
    if group.name in _GROUPS:
        raise ValueError(f"Feature group '{group.name}' is already registered.")
    clash = set(group.columns) & {c for g in _GROUPS.values() for c in g.columns}
    if clash:
        raise ValueError(f"Columns already used by another group: {sorted(clash)}")
    _GROUPS[group.name] = group


def _load_research_groups() -> None:
    # Research groups, in the order their columns appear in a combined config.
    from app.ml.feature_groups import accumulation, dow, geometry, patterns

    register(FeatureGroup(dow.GROUP, dow.COLUMNS, dow.compute))
    register(FeatureGroup(accumulation.GROUP, accumulation.COLUMNS, accumulation.compute))
    register(FeatureGroup(patterns.GROUP, patterns.COLUMNS, patterns.compute))
    register(FeatureGroup(geometry.GROUP, geometry.COLUMNS, geometry.compute))
    # Descriptive only; not part of the ablation's combined configurations.
    register(FeatureGroup(geometry.FIB_GROUP, geometry.FIB_COLUMNS, geometry.compute_fibonacci))


def group_names() -> list[str]:
    return list(_GROUPS)


def get_group(name: str) -> FeatureGroup:
    try:
        return _GROUPS[name]
    except KeyError:
        raise ValueError(f"Unknown feature group '{name}'. Known: {', '.join(_GROUPS)}") from None


def resolve_groups(groups) -> tuple[str, ...]:
    """Validated, de-duplicated group names in registry order."""
    requested = set(groups)
    for name in requested:
        get_group(name)
    if not requested:
        raise ValueError("At least one feature group is required.")
    return tuple(name for name in _GROUPS if name in requested)


def feature_columns(groups=DEFAULT_GROUPS) -> list[str]:
    return [c for name in resolve_groups(groups) for c in _GROUPS[name].columns]


def compute_group_features(prices: pd.DataFrame, groups=DEFAULT_GROUPS) -> pd.DataFrame:
    frames = []
    for name in resolve_groups(groups):
        group = _GROUPS[name]
        frame = group.compute(prices)
        if list(frame.columns) != list(group.columns) or not frame.index.equals(prices.index):
            raise ValueError(f"Feature group '{name}' returned unexpected columns or index.")
        frames.append(frame)
    return pd.concat(frames, axis=1)


_load_research_groups()
