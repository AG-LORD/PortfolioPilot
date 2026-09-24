"""Walk-forward evaluation of the ML models against the historical-mean
baseline, all forecasting the same forward return (the panel's label).

All models are scored on the same rows: test-block rows that have a label
and a baseline forecast, so no model is scored on dates another one skips.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd
from sklearn.pipeline import Pipeline

from app.ml.baseline import BASELINE_COLUMN
from app.ml.metrics import daily_ic, hit_rate, ic_standard_error, mean_absolute_error, mean_ic
from app.ml.models import MODEL_NAMES, make_model
from app.ml.splits import N_TEST_BLOCKS, WalkForwardSplit, walk_forward_splits
from app.services.features import DEFAULT_HORIZON, FEATURE_COLUMNS, LABEL_COLUMN

BASELINE_MODEL = "historical_mean"
METRIC_DECIMALS = 6


class EvaluationError(Exception):
    pass


@dataclass
class ModelEvaluation:
    """Same fields as the /ml/evaluation response (ModelEvaluationRead)."""

    model: str
    mae: Decimal
    hit_rate: Decimal
    mean_ic: Decimal
    test_blocks: int
    as_of: date


@dataclass
class WalkForwardResult:
    splits: list[WalkForwardSplit]
    # One row per scored (date, ticker): label, block, one forecast column per model.
    predictions: pd.DataFrame
    fitted_models: list[dict[str, Pipeline]]


def fit_models(train: pd.DataFrame) -> dict[str, Pipeline]:
    return {
        name: make_model(name).fit(train[FEATURE_COLUMNS], train[LABEL_COLUMN])
        for name in MODEL_NAMES
    }


def run_walk_forward(
    panel: pd.DataFrame, n_blocks: int = N_TEST_BLOCKS, horizon: int = DEFAULT_HORIZON
) -> WalkForwardResult:
    labeled = panel[panel[LABEL_COLUMN].notna()].sort_values(["date", "ticker"], ignore_index=True)
    splits = walk_forward_splits(labeled["date"], n_blocks=n_blocks, horizon=horizon)

    blocks = []
    fitted_models = []
    for block, split in enumerate(splits):
        train = labeled[labeled["date"].isin(split.train_dates)]
        test = labeled[labeled["date"].isin(split.test_dates) & labeled[BASELINE_COLUMN].notna()]
        models = fit_models(train)
        fitted_models.append(models)
        if test.empty:
            continue

        scored = test[["date", "ticker", LABEL_COLUMN]].copy()
        scored["block"] = block
        scored[BASELINE_MODEL] = test[BASELINE_COLUMN]
        for name, model in models.items():
            scored[name] = model.predict(test[FEATURE_COLUMNS])
        blocks.append(scored)

    if not blocks:
        raise EvaluationError("No test rows with both a label and a baseline forecast.")
    return WalkForwardResult(
        splits=splits,
        predictions=pd.concat(blocks, ignore_index=True),
        fitted_models=fitted_models,
    )


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(round(value, METRIC_DECIMALS)))


def evaluate_models(
    panel: pd.DataFrame, n_blocks: int = N_TEST_BLOCKS, horizon: int = DEFAULT_HORIZON
) -> list[ModelEvaluation]:
    return summarize_walk_forward(run_walk_forward(panel, n_blocks=n_blocks, horizon=horizon))


def summarize_walk_forward(result: WalkForwardResult) -> list[ModelEvaluation]:
    predictions = result.predictions
    realized = predictions[LABEL_COLUMN]
    test_blocks = int(predictions["block"].nunique())
    as_of = pd.Timestamp(predictions["date"].max()).date()

    evaluations = []
    for model in (BASELINE_MODEL, *MODEL_NAMES):
        forecast = predictions[model]
        metrics = {
            "mae": mean_absolute_error(forecast, realized),
            "hit_rate": hit_rate(forecast, realized),
            "mean_ic": mean_ic(predictions["date"], forecast, realized),
        }
        undefined = [name for name, value in metrics.items() if pd.isna(value)]
        if undefined:
            raise EvaluationError(f"{model}: {', '.join(undefined)} undefined on the test rows.")
        evaluations.append(
            ModelEvaluation(
                model=model,
                test_blocks=test_blocks,
                as_of=as_of,
                **{name: _to_decimal(value) for name, value in metrics.items()},
            )
        )
    return evaluations


@dataclass
class BlockIC:
    block: int  # 1-based
    start: date
    end: date
    ic_dates: int
    mean_ic: float  # NaN when no date in the block has a usable IC


def _daily_ic(predictions: pd.DataFrame, model: str) -> pd.Series:
    return daily_ic(predictions["date"], predictions[model], predictions[LABEL_COLUMN])


def per_block_ic(result: WalkForwardResult) -> dict[str, list[BlockIC]]:
    blocks: dict[str, list[BlockIC]] = {}
    for model in (BASELINE_MODEL, *MODEL_NAMES):
        blocks[model] = []
        for block, rows in result.predictions.groupby("block", sort=True):
            daily = _daily_ic(rows, model)
            blocks[model].append(
                BlockIC(
                    block=int(block) + 1,
                    start=pd.Timestamp(rows["date"].min()).date(),
                    end=pd.Timestamp(rows["date"].max()).date(),
                    ic_dates=len(daily),
                    mean_ic=float(daily.mean()) if len(daily) else float("nan"),
                )
            )
    return blocks


def ic_standard_errors(result: WalkForwardResult) -> dict[str, float]:
    return {
        model: ic_standard_error(_daily_ic(result.predictions, model))
        for model in (BASELINE_MODEL, *MODEL_NAMES)
    }
