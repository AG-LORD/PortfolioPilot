"""Feature-group ablation: identical rows, screening rule and diagnostics."""

import math

import pytest

from app.ml import ablation
from app.ml.feature_groups.registry import TECHNICAL, feature_columns
from app.services.features import build_panel_from_prices
from ohlcv_fakes import frame_to_points, random_ohlcv


@pytest.fixture(scope="module")
def panel():
    tickers = [f"T{i}" for i in range(8)]
    points = {t: frame_to_points(random_ohlcv(640, seed=20 + i)) for i, t in enumerate(tickers)}
    groups = sorted({g for c in ablation.CONFIGURATIONS.values() for g in c})
    return build_panel_from_prices(tickers, points, errors={}, groups=groups).panel


@pytest.fixture(scope="module")
def result(panel):
    return ablation.run_ablation(panel, n_blocks=3)


def test_configurations_are_the_agreed_seven():
    c = ablation.CONFIGURATIONS
    assert list(c) == list("ABCDEFG")
    assert c["A"] == (TECHNICAL,)
    assert set(c["F"]) == {"dow", "patterns", "accdist", "geometry"}
    assert set(c["G"]) == {TECHNICAL, *c["F"]}
    assert all("fibonacci" not in groups for groups in c.values())


def test_every_configuration_is_reported_with_its_own_features(result):
    assert [c.name for c in result.configs] == list("ABCDEFG")
    for c in result.configs:
        assert c.n_features == len(feature_columns(c.groups))
        assert set(c.models) == {"ridge", "hist_gradient_boosting"}
        for m in c.models.values():
            assert len(m.block_ics) == 3
            assert math.isfinite(m.mean_ic)


def test_baseline_config_never_passes_its_own_screen(result):
    a = next(c for c in result.configs if c.name == "A")
    assert not any(s["passes"] for s in a.screen.values())
    assert a.screen["hist_gradient_boosting"]["ic_vs_live"] == 0


def test_screen_requires_both_the_margin_and_the_positive_blocks(result):
    a = next(c for c in result.configs if c.name == "A").models["hist_gradient_boosting"]
    threshold = a.mean_ic + ablation.SCREEN_SE_MULTIPLE * a.ic_std_error
    for c in result.configs[1:]:
        for model, m in c.models.items():
            expected = m.mean_ic > threshold and m.positive_blocks >= ablation.SCREEN_MIN_POSITIVE_BLOCKS
            assert c.screen[model]["passes"] == expected


def test_configurations_scored_on_different_rows_are_rejected(panel):
    from app.ml.evaluation import EvaluationError

    # A column that is NaN on some rows would change the rows; the walk-forward refuses it.
    broken = panel.copy()
    broken.loc[broken.index[:5], feature_columns(["dow"])[0]] = float("nan")
    with pytest.raises(EvaluationError):
        ablation.run_ablation(broken, configurations={"A": (TECHNICAL,), "B": ("dow",)}, n_blocks=3)


def test_coverage_reports_shares_in_unit_interval(panel):
    stats = ablation.coverage(panel)
    assert "any_pattern_active" in stats and "dow_k5_has_structure" in stats
    assert all(0 <= v <= 1 for v in stats.values())
