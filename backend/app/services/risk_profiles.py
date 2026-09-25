from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import RiskProfile, UserProfile
from app.schemas.risk_profile import RiskProfileCreate


def create_risk_profile(db: Session, user_id: UUID, data: RiskProfileCreate) -> RiskProfile:
    """user_id is the authenticated JWT subject. A first-time user may not
    have a user_profiles row yet, so create it in the same transaction
    (ON CONFLICT DO NOTHING keeps concurrent first requests safe)."""
    db.execute(insert(UserProfile).values(id=user_id).on_conflict_do_nothing(index_elements=["id"]))
    risk_profile = RiskProfile(user_id=user_id, **data.model_dump())
    db.add(risk_profile)
    db.commit()
    db.refresh(risk_profile)
    return risk_profile
