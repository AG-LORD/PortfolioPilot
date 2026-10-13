"""Feature-group registry and the leakage invariants every group must satisfy."""

import numpy as np
import pandas as pd
import pytest

from app.ml.evaluation import EvaluationError, run_walk_forward
from app.ml.feature_groups.registry import (
    DEFAULT_GROUPS,
    TECHNICAL,
    compute_group_features,
    feature_columns,
    group_names,
    resolve_groups,
)
from app.ml.baseline import BASELINE_COLUMN
from app.services.features import FEATURE_COLUMNS, LABEL_COLUMN, MIN_FEATURE_HISTORY, build_panel_from_prices
from ohlcv_fakes import frame_to_points, random_ohlcv

ALL_GROUPS = group_names()


def _panel_inputs(n_tickers=4, n=420):
    tickers = [f"T{i}" for i in range(n_tickers)]
    return tickers, {t: frame_to_points(random_ohlcv(n, seed=i)) for i, t in enumerate(tickers)}


# --- registry and baseline compatibility -------------------------------------------


def test_default_configuration_is_the_live_technical_set():
    assert DEFAULT_GROUPS == (TECHNICAL,)
    assert feature_columns() == FEATURE_COLUMNS
    assert feature_columns(DEFAULT_GROUPS) == FEATURE_COLUMNS


def test_panel_with_default_groups_is_identical_to_the_original_panel():
    tickers, points = _panel_inputs()
    original = build_panel_from_prices(tickers, points, errors={}).panel
    grouped = build_panel_from_prices(tickers, points, errors={}, groups=DEFAULT_GROUPS).panel
    pd.testing.assert_frame_equal(original, grouped, check_exact=True)


def test_unknown_or_empty_group_is_rejected():
    with pytest.raises(ValueError):
        resolve_groups(["no_such_group"])
    with pytest.raises(ValueError):
        resolve_groups([])


def test_groups_are_resolved_in_registry_order_without_duplicates():
    assert resolve_groups([TECHNICAL, TECHNICAL]) == (TECHNICAL,)
    assert resolve_groups(list(reversed(ALL_GROUPS))) == tuple(ALL_GROUPS)


def test_group_columns_are_disjoint_and_never_label_or_identifiers():
    columns = feature_columns(ALL_GROUPS)
    assert len(columns) == len(set(columns))
    assert not {LABEL_COLUMN, BASELINE_COLUMN, "date", "ticker"} & set(columns)


def test_walk_forward_rejects_label_or_identifier_inputs():
    tickers, points = _panel_inputs(n_tickers=6, n=600)
    panel = build_panel_from_prices(tickers, points, errors={}).panel
    for leaked in (LABEL_COLUMN, BASELINE_COLUMN):
        with pytest.raises(EvaluationError):
            run_walk_forward(panel, n_blocks=2, feature_columns=[*FEATURE_COLUMNS, leaked])


def test_feature_subsets_on_one_panel_are_scored_on_identical_rows():
    tickers, points = _panel_inputs(n_tickers=6, n=600)
    panel = build_panel_from_prices(tickers, points, errors={}, groups=ALL_GROUPS).panel
    results = [
        run_walk_forward(panel, n_blocks=2, feature_columns=feature_columns([name])) for name in ALL_GROUPS
    ]
    keys = [r.predictions[["date", "ticker"]].reset_index(drop=True) for r in results]
    for other in keys[1:]:
        pd.testing.assert_frame_equal(keys[0], other)


# --- invariants for every group ------------------------------------------------------


@pytest.mark.parametrize("group", ALL_GROUPS)
def test_columns_index_and_finite_after_min_feature_history(group):
    prices = random_ohlcv(420, seed=3)
    features = compute_group_features(prices, [group])
    assert list(features.columns) == feature_columns([group])
    assert features.index.equals(prices.index)
    after = features.iloc[MIN_FEATURE_HISTORY:].to_numpy(dtype=float)
    assert np.isfinite(after).all()


@pytest.mark.parametrize("group", ALL_GROUPS)
def test_future_data_does_not_change_features_up_to_t(group):
    # Identical through row t, different afterwards (a crash plus a volume spike).
    prices = random_ohlcv(400, seed=5)
    t = 330
    shocked = prices.copy()
    shocked.iloc[t + 1 :, :4] *= 0.6
    shocked.iloc[t + 1 :, 4] *= 5
    base = compute_group_features(prices, [group]).iloc[: t + 1]
    other = compute_group_features(shocked, [group]).iloc[: t + 1]
    pd.testing.assert_frame_equal(base, other, check_exact=True)


@pytest.mark.parametrize("group", ALL_GROUPS)
@pytest.mark.parametrize("cutoff", [300, 351, 399])
def test_truncating_the_series_does_not_change_earlier_features(group, cutoff):
    prices = random_ohlcv(400, seed=7)
    full = compute_group_features(prices, [group]).iloc[:cutoff]
    truncated = compute_group_features(prices.iloc[:cutoff], [group])
    pd.testing.assert_frame_equal(full, truncated, check_exact=True)


@pytest.mark.parametrize("group", ALL_GROUPS)
def test_features_are_deterministic(group):
    prices = random_ohlcv(400, seed=9)
    pd.testing.assert_frame_equal(
        compute_group_features(prices, [group]), compute_group_features(prices.copy(), [group]), check_exact=True
    )


@pytest.mark.parametrize("group", ALL_GROUPS)
def test_features_do_not_depend_on_price_or_volume_scale(group):
    prices = random_ohlcv(400, seed=11)
    scaled = prices.copy()
    scaled[["open", "high", "low", "close"]] *= 37.5
    scaled["volume"] *= 8
    base = compute_group_features(prices, [group]).iloc[MIN_FEATURE_HISTORY:]
    other = compute_group_features(scaled, [group]).iloc[MIN_FEATURE_HISTORY:]
    np.testing.assert_allclose(other.to_numpy(), base.to_numpy(), rtol=1e-9, atol=1e-9)
