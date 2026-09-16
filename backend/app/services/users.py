from uuid import UUID

from sqlalchemy.orm import Session

from app.models import UserProfile


def get_or_create_user_profile(db: Session, user_id: UUID) -> UserProfile:
    profile = db.get(UserProfile, user_id)

    if profile is not None:
        return profile

    profile = UserProfile(id=user_id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
