from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user_id
from app.ml.evaluation_reports import (
    EvaluationReportUnavailableError,
    load_latest_evaluation_report,
)
from app.schemas.ml import EvaluationReportRead

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/evaluation", response_model=EvaluationReportRead)
def read_model_evaluation(user_id=Depends(get_current_user_id)):
    try:
        return load_latest_evaluation_report()
    except EvaluationReportUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No valid offline model evaluation report is available. Run scripts.run_evaluation to create one.",
        ) from exc
