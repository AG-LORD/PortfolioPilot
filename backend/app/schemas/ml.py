from datetime import date
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ModelEvaluationRead(BaseModel):
    model: str
    mae: Decimal
    hit_rate: Decimal
    mean_ic: Decimal
    test_blocks: int
    as_of: date


class EvaluationSettingsRead(BaseModel):
    universe: str
    universe_as_of: date | None
    universe_revision: str
    start: date
    end: date
    blocks: int
    horizon: int
    min_feature_history: int
    source: str


class EvaluationDataRead(BaseModel):
    requested_tickers: int
    tickers_used: list[str]
    excluded: list[dict[str, str]]
    panel_rows: int
    panel_dates: list[str] | None
    scored_rows: int
    scored_dates: list[str] | None


class EvaluationMetricRead(BaseModel):
    model: str
    mae: Decimal
    hit_rate: Decimal
    mean_ic: Decimal
    ic_std_error: Decimal | None
    test_blocks: int
    as_of: date


class EvaluationBlockICRead(BaseModel):
    block: int
    start: date
    end: date
    ic_dates: int
    mean_ic: Decimal | None


class EvaluationReportRead(BaseModel):
    generated_at: datetime
    evaluation_version: str
    feature_version: str
    model_versions: dict[str, str]
    settings: EvaluationSettingsRead
    data: EvaluationDataRead
    metrics: list[EvaluationMetricRead]
    ic_std_error_note: str
    per_block_ic: dict[str, list[EvaluationBlockICRead]]
