from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_id
from app.schemas.ml import ModelEvaluationRead

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/evaluation", response_model=list[ModelEvaluationRead])
def read_model_evaluation(user_id=Depends(get_current_user_id)):
    # Contract stub: no models are trained yet.
    return []
