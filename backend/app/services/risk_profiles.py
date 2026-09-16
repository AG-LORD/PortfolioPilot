from uuid import UUID

from sqlalchemy.orm import Session

from app.models import RiskProfile
from app.schemas.risk_profile import RiskProfileCreate


def create_risk_profile(db: Session, user_id: UUID, data: RiskProfileCreate) -> RiskProfile:
    risk_profile = RiskProfile(user_id=user_id, **data.model_dump())
    db.add(risk_profile)
    db.commit()
    db.refresh(risk_profile)
    return risk_profile
