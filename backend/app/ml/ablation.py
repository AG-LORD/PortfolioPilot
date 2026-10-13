"""Feature-group ablation on one panel: identical rows, splits and models.

Every configuration is a subset of the panel's feature columns, so all of
them are trained on the same walk-forward splits and scored on exactly the
same (date, ticker) rows (checked, not assumed). Hyperparameters are the
fixed constants in app.ml.models; nothing is tuned here.

Screening (agreed before running): a configuration/model passes if its mean
IC exceeds the live baseline's (configuration A, hist_gradient_boosting) by
more than SCREEN_SE_MULTIPLE naive standard errors of the baseline's daily
IC AND its IC is positive in at least SCREEN_MIN_POSITIVE_BLOCKS of the test
blocks. The naive standard error ignores the autocorrelation from
overlapping labels and 7 configurations are compared, so passing is a
screening signal only, never evidence of generalization.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.ml.evaluation import (
    BASELINE_MODEL,
    EvaluationError,
    ic_standard_errors,
    per_block_ic,
    run_walk_forward,
    summarize_walk_forward,
)
from app.ml.feature_groups.registry import TECHNICAL, feature_columns
from app.ml.models import HIST_GRADIENT_BOOSTING, MODEL_NAMES
from app.ml.splits import N_TEST_BLOCKS
from app.services.features import DEFAULT_HORIZON, LABEL_COLUMN

RESEARCH_GROUPS = ("dow", "patterns", "accdist", "geometry")
CONFIGURATIONS: dict[str, tuple[str, ...]] = {
    "A": (TECHNICAL,),
    "B": ("dow",),
    "C": ("patterns",),
    "D": ("accdist",),
    "E": ("geometry",),
    "F": RESEARCH_GROUPS,
    "G": (TECHNICAL, *RESEARCH_GROUPS),
}
BASELINE_CONFIG = "A"
LIVE_MODEL = HIST_GRADIENT_BOOSTING
SCREEN_SE_MULTIPLE = 2.0
SCREEN_MIN_POSITIVE_BLOCKS = 4


@dataclass
class ModelResult:
    mae: float
    hit_rate: float
    mean_ic: float
    ic_std_error: float
    block_ics: list[float]
    positive_blocks: int
    block_ic_std: float


@dataclass
class ConfigResult:
    name: str
    groups: tuple[str, ...]
    n_features: int
    models: dict[str, ModelResult]
    screen: dict[str, dict] = field(default_factory=dict)


@dataclass
class AblationResult:
    configs: list[ConfigResult]
    baseline_forecast: ModelResult  # historical mean: identical in every configuration
    scored_rows: int
    scored_dates: tuple[str, str]
    blocks: list[tuple[str, str]]


def _model_result(evaluation, standard_error: float, blocks) -> ModelResult:
    ics = [b.mean_ic for b in blocks]
    finite = [v for v in ics if np.isfinite(v)]
    return ModelResult(
        mae=float(evaluation.mae),
        hit_rate=float(evaluation.hit_rate),
        mean_ic=float(evaluation.mean_ic),
        ic_std_error=float(standard_error),
        block_ics=ics,
        positive_blocks=sum(v > 0 for v in finite),
        block_ic_std=float(np.std(finite, ddof=1)) if len(finite) > 1 else float("nan"),
    )


def run_ablation(
    panel: pd.DataFrame,
    configurations: dict[str, tuple[str, ...]] = CONFIGURATIONS,
    n_blocks: int = N_TEST_BLOCKS,
    horizon: int = DEFAULT_HORIZON,
) -> AblationResult:
    configs: list[ConfigResult] = []
    reference_rows = None
    baseline_forecast = None
    for name, groups in configurations.items():
        columns = feature_columns(groups)
        result = run_walk_forward(panel, n_blocks=n_blocks, horizon=horizon, feature_columns=columns)
        rows = result.predictions[["date", "ticker", "block"]].reset_index(drop=True)
        if reference_rows is None:
            reference_rows = rows
        elif not rows.equals(reference_rows):
            raise EvaluationError(f"Configuration {name} was scored on different rows.")

        evaluations = {e.model: e for e in summarize_walk_forward(result)}
        errors = ic_standard_errors(result)
        blocks = per_block_ic(result)
        if baseline_forecast is None:
            baseline_forecast = _model_result(evaluations[BASELINE_MODEL], errors[BASELINE_MODEL], blocks[BASELINE_MODEL])
            block_dates = [(b.start.isoformat(), b.end.isoformat()) for b in blocks[BASELINE_MODEL]]
            dates = result.predictions["date"]
            scored_dates = (str(dates.min())[:10], str(dates.max())[:10])
        configs.append(
            ConfigResult(
                name=name,
                groups=tuple(groups),
                n_features=len(columns),
                models={m: _model_result(evaluations[m], errors[m], blocks[m]) for m in MODEL_NAMES},
            )
        )

    _screen(configs)
    return AblationResult(
        configs=configs,
        baseline_forecast=baseline_forecast,
        scored_rows=len(reference_rows),
        scored_dates=scored_dates,
        blocks=block_dates,
    )


def _screen(configs: list[ConfigResult]) -> None:
    baseline = next((c for c in configs if c.name == BASELINE_CONFIG), None)
    if baseline is None:
        return
    live = baseline.models[LIVE_MODEL]
    threshold = live.mean_ic + SCREEN_SE_MULTIPLE * live.ic_std_error
    for config in configs:
        for model, result in config.models.items():
            config.screen[model] = {
                "ic_vs_live": result.mean_ic - live.mean_ic,
                "beats_by_2se": result.mean_ic > threshold,
                "positive_blocks_ok": result.positive_blocks >= SCREEN_MIN_POSITIVE_BLOCKS,
                "passes": config.name != BASELINE_CONFIG
                and result.mean_ic > threshold
                and result.positive_blocks >= SCREEN_MIN_POSITIVE_BLOCKS,
            }


def coverage(panel: pd.DataFrame) -> dict[str, float]:
    """Share of labelled rows on which event-like features are present (diagnostic)."""
    labeled = panel[panel[LABEL_COLUMN].notna()]
    present = {
        "dow_k5_has_structure": labeled.get("dow_k5_has_structure", pd.Series(dtype=float)) == 1,
        "dow_k5_trend_nonzero": labeled.get("dow_k5_trend", pd.Series(dtype=float)) != 0,
        "geo_has_swings": labeled.get("geo_has_swings", pd.Series(dtype=float)) == 1,
        "failed_breakout_flag_nonzero": labeled.get("failed_breakout_flag", pd.Series(dtype=float)) != 0,
        "any_pattern_active": labeled.get("pat_active_count", pd.Series(dtype=float)) > 0,
        "pattern_breakout_confirmed": labeled.get("pat_breakout_dir", pd.Series(dtype=float)) != 0,
    }
    stats = {name: float(mask.mean()) for name, mask in present.items() if len(mask)}
    for column in labeled.columns:
        if column.startswith("pat_") and column.endswith("_state"):
            stats[f"{column[4:-6]}_active"] = float((labeled[column] > 0).mean())
            stats[f"{column[4:-6]}_confirmed"] = float((labeled[column] == 2).mean())
    return stats
