from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.ml.baseline import BASELINE_COLUMN, BASELINE_LOOKBACK, historical_mean_forecast
from app.ml.evaluation import (
    BASELINE_MODEL,
    evaluate_models,
    ic_standard_errors,
    per_block_ic,
    run_walk_forward,
)
from app.ml.metrics import (
    MIN_IC_TICKERS,
    daily_ic,
    hit_rate,
    ic_standard_error,
    mean_absolute_error,
    mean_ic,
)
from app.ml.models import HIST_GRADIENT_BOOSTING, MODEL_NAMES, RIDGE
from app.ml.splits import walk_forward_splits
from app.schemas.ml import ModelEvaluationRead
from app.services.features import FEATURE_COLUMNS, LABEL_COLUMN

HORIZON = 20


def _panel(n_dates=260, n_tickers=12, signal=0.0, drift=0.0, seed=0):
    """Synthetic long panel. label = signal * 0.05 * momentum_20 + noise.
    `drift` adds a date trend to every feature so fold means differ."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_dates)
    n = n_dates * n_tickers
    frame = pd.DataFrame(
        {
            "date": np.repeat(dates, n_tickers),
            "ticker": np.tile([f"ZZTEST_{i:02d}" for i in range(n_tickers)], n_dates),
        }
    )
    trend = np.repeat(np.arange(n_dates), n_tickers) * drift
    for column in FEATURE_COLUMNS:
        frame[column] = rng.normal(0, 1, n) + trend
    frame[LABEL_COLUMN] = signal * 0.05 * frame["momentum_20"] + rng.normal(0, 0.05, n)
    frame[BASELINE_COLUMN] = rng.normal(0, 0.01, n)
    return frame


# --- splits ------------------------------------------------------------------------


def test_splits_train_precede_test_with_purge_gap_and_cover_without_overlap():
    dates = list(pd.bdate_range("2024-01-01", periods=130))
    splits = walk_forward_splits(dates, n_blocks=5, horizon=5)
    position = {d: i for i, d in enumerate(dates)}

    covered = []
    for split in splits:
        assert split.train_dates and split.test_dates
        assert max(split.train_dates) < min(split.test_dates)
        gap = position[min(split.test_dates)] - position[max(split.train_dates)] - 1
        assert gap >= 5
        covered.extend(split.test_dates)

    block_length = 130 // 6
    assert covered == dates[block_length:]  # contiguous, no overlap, through the last date
    assert len(covered) == len(set(covered))


def test_splits_are_expanding():
    splits = walk_forward_splits(pd.bdate_range("2024-01-01", periods=200), n_blocks=4, horizon=10)
    for earlier, later in zip(splits, splits[1:]):
        assert set(earlier.train_dates) < set(later.train_dates)


def test_splits_reject_too_few_dates():
    with pytest.raises(ValueError):
        walk_forward_splits(pd.bdate_range("2024-01-01", periods=60), n_blocks=5, horizon=20)


def test_split_dates_deduplicated_across_tickers():
    dates = pd.bdate_range("2024-01-01", periods=120)
    per_row = list(np.repeat(dates, 3))
    assert walk_forward_splits(per_row, 3, 5)[0].test_dates == walk_forward_splits(dates, 3, 5)[0].test_dates


# --- leakage -----------------------------------------------------------------------


def test_scaler_is_fit_only_on_training_fold():
    panel = _panel(drift=0.01)
    result = run_walk_forward(panel, n_blocks=3, horizon=HORIZON)
    labeled = panel[panel[LABEL_COLUMN].notna()]

    for split, models in zip(result.splits, result.fitted_models):
        train = labeled[labeled["date"].isin(split.train_dates)]
        scaler = models[RIDGE].named_steps["scaler"]
        np.testing.assert_allclose(scaler.mean_, train[FEATURE_COLUMNS].mean().to_numpy(), rtol=1e-12)
        assert scaler.n_samples_seen_ == len(train)

    # With a date trend, the first fold's mean is clearly below the full-panel mean.
    first_scaler_mean = result.fitted_models[0][RIDGE].named_steps["scaler"].mean_
    assert (labeled[FEATURE_COLUMNS].mean().to_numpy() - first_scaler_mean).min() > 0.5


def test_training_rows_never_come_from_test_block_or_purge_gap():
    panel = _panel()
    result = run_walk_forward(panel, n_blocks=3, horizon=HORIZON)
    all_dates = sorted(panel["date"].unique())
    for block, split in enumerate(result.splits):
        first_test = all_dates.index(min(split.test_dates))
        allowed = set(all_dates[: first_test - HORIZON])
        assert set(split.train_dates) <= allowed
        scored = result.predictions[result.predictions["block"] == block]
        assert set(scored["date"]) <= set(split.test_dates)


# --- baseline ------------------------------------------------------------------------


def test_baseline_truncation_invariance():
    close = pd.Series(100 * np.cumprod(1 + np.random.default_rng(3).normal(0.0005, 0.02, 400)))
    full = historical_mean_forecast(close, HORIZON)
    truncated = historical_mean_forecast(close.iloc[:300], HORIZON)
    pd.testing.assert_series_equal(full.iloc[:300], truncated, check_exact=True)


def test_baseline_needs_full_lookback_and_scales_mean_daily_return():
    close = pd.Series(100 * 1.001 ** np.arange(300))
    forecast = historical_mean_forecast(close, HORIZON)
    assert forecast.iloc[:BASELINE_LOOKBACK].isna().all()
    assert forecast.iloc[BASELINE_LOOKBACK:].to_numpy() == pytest.approx(HORIZON * 0.001, rel=1e-9)


# --- metrics -------------------------------------------------------------------------


def _metric_frame(forecast, realized, per_date=6):
    n = len(realized)
    dates = pd.Series(np.repeat(pd.bdate_range("2024-01-01", periods=n // per_date), per_date))
    return dates, pd.Series(forecast, dtype=float), pd.Series(realized, dtype=float)


def test_perfect_forecast_gives_ic_one_and_hit_rate_one():
    realized = np.random.default_rng(1).normal(0, 0.05, 60)
    dates, f, r = _metric_frame(realized, realized)
    assert mean_ic(dates, f, r) == pytest.approx(1.0)
    assert hit_rate(f, r) == 1.0
    assert mean_absolute_error(f, r) == 0.0


def test_reversed_ranking_gives_ic_minus_one():
    realized = np.random.default_rng(2).normal(0, 0.05, 60)
    dates, f, r = _metric_frame(-realized, realized)
    assert mean_ic(dates, f, r) == pytest.approx(-1.0)
    assert hit_rate(f, r) == 0.0


def test_mae_known_value():
    assert mean_absolute_error(pd.Series([0.1, -0.2, 0.3]), pd.Series([0.0, -0.1, 0.5])) == pytest.approx(
        0.4 / 3
    )


def test_hit_rate_excludes_zero_realized_and_counts_zero_forecast_as_miss():
    forecast = pd.Series([0.1, -0.1, 0.2, 0.0])
    realized = pd.Series([0.05, 0.02, 0.0, 0.01])
    assert hit_rate(forecast, realized) == pytest.approx(1 / 3)


def test_ic_standard_error_known_value():
    daily = pd.Series([0.1, 0.2, 0.3, 0.4])
    # sample std = sqrt(((0.15)^2 + (0.05)^2) * 2 / 3) = 0.129099...; / sqrt(4)
    assert ic_standard_error(daily) == pytest.approx(0.1290994449 / 2, rel=1e-9)
    assert np.isnan(ic_standard_error(pd.Series([0.1])))


def test_per_block_ic_and_standard_errors_cover_every_model_and_block():
    result = run_walk_forward(_panel(signal=1.0), n_blocks=3, horizon=HORIZON)
    blocks = per_block_ic(result)
    standard_errors = ic_standard_errors(result)
    assert set(blocks) == set(standard_errors) == {BASELINE_MODEL, *MODEL_NAMES}
    for model_blocks in blocks.values():
        assert [b.block for b in model_blocks] == [1, 2, 3]
        assert all(b.start <= b.end and b.ic_dates > 0 for b in model_blocks)
    assert all(0 < se < 0.1 for se in standard_errors.values())
    for b, split in zip(blocks[RIDGE], result.splits):
        assert b.start == pd.Timestamp(min(split.test_dates)).date()


def test_ic_skips_dates_with_too_few_tickers():
    dates = pd.Series(["d1"] * MIN_IC_TICKERS + ["d2"] * (MIN_IC_TICKERS - 1))
    values = pd.Series(np.arange(len(dates), dtype=float))
    assert list(daily_ic(dates, values, values).index) == ["d1"]


# --- evaluation ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def signal_evaluation():
    return evaluate_models(_panel(signal=1.0), n_blocks=3, horizon=HORIZON)


def test_evaluation_matches_response_schema(signal_evaluation):
    validated = TypeAdapter(list[ModelEvaluationRead]).validate_python([asdict(e) for e in signal_evaluation])
    assert [e.model for e in validated] == [BASELINE_MODEL, *MODEL_NAMES]
    assert all(e.test_blocks == 3 for e in validated)


def test_evaluation_is_deterministic(signal_evaluation):
    assert evaluate_models(_panel(signal=1.0), n_blocks=3, horizon=HORIZON) == signal_evaluation


def test_models_find_a_real_signal(signal_evaluation):
    ic = {e.model: float(e.mean_ic) for e in signal_evaluation}
    assert ic[RIDGE] > 0.3
    assert ic[HIST_GRADIENT_BOOSTING] > 0.3


def test_models_find_nothing_in_noise():
    evaluation = evaluate_models(_panel(signal=0.0, seed=7), n_blocks=3, horizon=HORIZON)
    for e in evaluation:
        assert abs(float(e.mean_ic)) < 0.1, e


def test_all_models_scored_on_the_same_rows():
    panel = _panel(signal=1.0)
    panel.loc[panel["ticker"] == "ZZTEST_00", BASELINE_COLUMN] = np.nan
    predictions = run_walk_forward(panel, n_blocks=3, horizon=HORIZON).predictions
    assert "ZZTEST_00" not in set(predictions["ticker"])
    assert not predictions[[BASELINE_MODEL, *MODEL_NAMES]].isna().any().any()
