import uuid
from decimal import Decimal

import pytest

from app.api.users import create_own_risk_profile
from app.models import RiskProfile, UserProfile
from app.schemas.risk_profile import RiskProfileCreate

PAYLOAD = {
    "score": 50,
    "category": "moderate",
    "max_position_weight": 0.1,
    "max_sector_weight": 0.25,
    "drift_threshold": 0.05,
    "target_volatility": 0.15,
}


@pytest.fixture
def new_user_id(db_session):
    user_id = uuid.uuid4()
    yield user_id
    db_session.rollback()
    db_session.query(RiskProfile).filter(RiskProfile.user_id == user_id).delete()
    db_session.query(UserProfile).filter(UserProfile.id == user_id).delete()
    db_session.commit()


@pytest.mark.db
def test_new_user_can_create_risk_profile_without_existing_user_profile(db_session, new_user_id):
    assert db_session.get(UserProfile, new_user_id) is None

    created = create_own_risk_profile(
        data=RiskProfileCreate(**PAYLOAD), user_id=new_user_id, db=db_session
    )

    assert created.user_id == new_user_id
    assert created.category == "moderate"
    assert created.max_position_weight == Decimal("0.1")
    db_session.expire_all()
    assert db_session.get(UserProfile, new_user_id) is not None


@pytest.mark.db
def test_repeat_risk_profiles_reuse_the_single_user_profile(db_session, new_user_id):
    for _ in range(2):
        create_own_risk_profile(data=RiskProfileCreate(**PAYLOAD), user_id=new_user_id, db=db_session)

    assert db_session.query(UserProfile).filter(UserProfile.id == new_user_id).count() == 1
    assert db_session.query(RiskProfile).filter(RiskProfile.user_id == new_user_id).count() == 2


@pytest.mark.db
def test_existing_user_profile_is_left_unchanged(db_session, new_user_id):
    db_session.add(UserProfile(id=new_user_id, full_name="Existing Name"))
    db_session.commit()

    create_own_risk_profile(data=RiskProfileCreate(**PAYLOAD), user_id=new_user_id, db=db_session)

    db_session.expire_all()
    assert db_session.get(UserProfile, new_user_id).full_name == "Existing Name"


@pytest.mark.db
def test_client_supplied_user_id_is_ignored(db_session, new_user_id):
    other_user = uuid.uuid4()
    data = RiskProfileCreate.model_validate({**PAYLOAD, "user_id": str(other_user)})

    created = create_own_risk_profile(data=data, user_id=new_user_id, db=db_session)

    assert created.user_id == new_user_id
    assert db_session.get(UserProfile, other_user) is None
