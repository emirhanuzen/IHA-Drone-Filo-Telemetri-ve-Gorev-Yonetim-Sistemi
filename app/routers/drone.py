from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.drone import DroneCreate, DroneResponse, DroneUpdate
from app.services import drone as drone_service

router = APIRouter(prefix="/drones", tags=["drones"])


@router.post("", response_model=DroneResponse, status_code=status.HTTP_201_CREATED)
def create_drone(payload: DroneCreate, db: Session = Depends(get_db)) -> DroneResponse:
    return drone_service.create_drone(db, payload)


@router.get("", response_model=list[DroneResponse])
def list_drones(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
) -> list[DroneResponse]:
    return drone_service.list_drones(db, skip=skip, limit=limit)


@router.get("/{drone_id}", response_model=DroneResponse)
def get_drone(drone_id: int, db: Session = Depends(get_db)) -> DroneResponse:
    return drone_service.get_drone(db, drone_id)


@router.patch("/{drone_id}", response_model=DroneResponse)
def update_drone(
    drone_id: int, payload: DroneUpdate, db: Session = Depends(get_db)
) -> DroneResponse:
    return drone_service.update_drone(db, drone_id, payload)


@router.delete("/{drone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drone(drone_id: int, db: Session = Depends(get_db)) -> None:
    drone_service.delete_drone(db, drone_id)
