import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.ml import EvaluationReportRead

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


class EvaluationReportUnavailableError(Exception):
    pass


def load_latest_evaluation_report() -> EvaluationReportRead:
    report_paths = sorted(RESULTS_DIR.glob("evaluation_*.json"), reverse=True)
    if not report_paths:
        raise EvaluationReportUnavailableError("No completed walk-forward evaluation report is available")

    report_path = report_paths[0]
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return EvaluationReportRead.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise EvaluationReportUnavailableError(
            f"The latest evaluation report ({report_path.name}) is invalid"
        ) from exc