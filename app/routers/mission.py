from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.mission import MissionCreate, MissionResponse, MissionUpdate
from app.services import mission as mission_service

router = APIRouter(prefix="/missions", tags=["missions"])


@router.post("", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
def create_mission(
    payload: MissionCreate, db: Session = Depends(get_db)
) -> MissionResponse:
    return mission_service.create_mission(db, payload)


@router.get("", response_model=list[MissionResponse])
def list_missions(
    drone_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[MissionResponse]:
    return mission_service.list_missions(db, drone_id=drone_id, skip=skip, limit=limit)


@router.get("/{mission_id}", response_model=MissionResponse)
def get_mission(mission_id: int, db: Session = Depends(get_db)) -> MissionResponse:
    return mission_service.get_mission(db, mission_id)


@router.patch("/{mission_id}", response_model=MissionResponse)
def update_mission(
    mission_id: int, payload: MissionUpdate, db: Session = Depends(get_db)
) -> MissionResponse:
    return mission_service.update_mission(db, mission_id, payload)


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission(mission_id: int, db: Session = Depends(get_db)) -> None:
    mission_service.delete_mission(db, mission_id)
