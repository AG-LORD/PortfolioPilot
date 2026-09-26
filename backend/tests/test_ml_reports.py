import json
from datetime import date

import pytest
from fastapi import HTTPException

from app.api import ml as ml_api
from app.ml import evaluation_reports
from app.ml.evaluation_reports import (
    EvaluationReportUnavailableError,
    load_latest_evaluation_report,
)


def _report(generated_at: str):
    return {
        "generated_at": generated_at,
        "evaluation_version": "purged-walk-forward-v1",
        "feature_version": "point-in-time-technical-v1",
        "model_versions": {
            "historical_mean": "historical-mean-lookback-252-v1",
            "ridge": "ridge-alpha-1-fixed-v1",
            "hist_gradient_boosting": "hist-gradient-boosting-fixed-v1",
        },
        "settings": {
            "universe": "NIFTY50",
            "universe_as_of": "2026-09-25",
            "universe_revision": "NIFTY50@2026-09-25:test",
            "start": "2025-01-01",
            "end": "2025-12-31",
            "blocks": 3,
            "horizon": 20,
            "min_feature_history": 252,
            "source": "price cache",
        },
        "data": {
            "requested_tickers": 1,
            "tickers_used": ["TCS"],
            "excluded": [],
            "panel_rows": 300,
            "panel_dates": ["2025-01-01", "2025-12-31"],
            "scored_rows": 120,
            "scored_dates": ["2025-04-01", "2025-12-31"],
        },
        "metrics": [
            {
                "model": "historical_mean",
                "mae": "0.01",
                "hit_rate": "0.5",
                "mean_ic": "0.02",
                "ic_std_error": "0.005",
                "test_blocks": 3,
                "as_of": "2025-12-31",
            }
        ],
        "ic_std_error_note": "Overlapping labels make this uncertainty optimistic.",
        "per_block_ic": {
            "historical_mean": [
                {
                    "block": 1,
                    "start": "2025-04-01",
                    "end": "2025-06-30",
                    "ic_dates": 20,
                    "mean_ic": "0.02",
                }
            ]
        },
    }


def test_report_loader_reads_latest_artifact_without_running_evaluation(tmp_path, monkeypatch):
    older = _report("2025-12-31T00:00:00+00:00")
    latest = _report("2026-09-25T12:00:00+00:00")
    (tmp_path / "evaluation_2025-12-31.json").write_text(json.dumps(older), encoding="utf-8")
    (tmp_path / "evaluation_2026-09-25.json").write_text(json.dumps(latest), encoding="utf-8")
    monkeypatch.setattr(evaluation_reports, "RESULTS_DIR", tmp_path)

    report = load_latest_evaluation_report()

    assert report.generated_at.date() == date(2026, 9, 25)
    assert report.data.scored_rows == 120
    assert report.model_versions["ridge"] == "ridge-alpha-1-fixed-v1"


def test_report_loader_reports_missing_or_invalid_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation_reports, "RESULTS_DIR", tmp_path)
    with pytest.raises(EvaluationReportUnavailableError, match="No completed"):
        load_latest_evaluation_report()

    (tmp_path / "evaluation_2026-09-25.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EvaluationReportUnavailableError, match="is invalid"):
        load_latest_evaluation_report()


def test_evaluation_endpoint_returns_503_when_no_report_is_saved(monkeypatch):
    def missing_report():
        raise EvaluationReportUnavailableError("missing")

    monkeypatch.setattr(ml_api, "load_latest_evaluation_report", missing_report)
    with pytest.raises(HTTPException) as exc_info:
        ml_api.read_model_evaluation(user_id=None)

    assert exc_info.value.status_code == 503