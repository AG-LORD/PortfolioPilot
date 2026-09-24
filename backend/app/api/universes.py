from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_id
from app.schemas.universe import UniverseRead
from app.services.universe import list_universes

router = APIRouter(prefix="/universes", tags=["universes"])


@router.get("", response_model=list[UniverseRead])
def read_universes(user_id=Depends(get_current_user_id)):
    return [UniverseRead(**listing._asdict()) for listing in list_universes()]
