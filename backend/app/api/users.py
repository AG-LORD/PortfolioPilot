from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user_id, get_db
from app.services.users import get_or_create_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_own_profile(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    profile = get_or_create_user_profile(db, user_id)
    return {
        "id": str(profile.id),
        "full_name": profile.full_name,
        "created_at": profile.created_at,
    }

from app.schemas.risk_profile import RiskProfileCreate, RiskProfileRead
from app.services.risk_profiles import create_risk_profile


@router.post("/me/risk-profile", response_model=RiskProfileRead)
def create_own_risk_profile(
    data: RiskProfileCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return create_risk_profile(db, user_id, data)
