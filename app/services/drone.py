"""Drone iş mantığı ve veritabanı işlemleri.

Router katmanı asla doğrudan veritabanına erişmez; tüm işlemler bu servis
fonksiyonları üzerinden yürür.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.drone import Drone
from app.schemas.drone import DroneCreate, DroneUpdate


def get_drone(db: Session, drone_id: int) -> Drone:
    """Tek bir drone'u getirir; bulunamazsa 404 döner."""
    drone = db.get(Drone, drone_id)
    if drone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Drone bulunamadi"
        )
    return drone


def list_drones(db: Session, skip: int = 0, limit: int = 100) -> list[Drone]:
    """Drone'ları sayfalı olarak listeler."""
    stmt = select(Drone).offset(skip).limit(limit).order_by(Drone.id)
    return list(db.scalars(stmt).all())


def create_drone(db: Session, data: DroneCreate) -> Drone:
    """Yeni bir drone oluşturur; seri no tekilse hata döner."""
    existing = db.scalar(
        select(Drone).where(Drone.serial_number == data.serial_number)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu seri numarasina sahip bir drone zaten var",
        )
    drone = Drone(
        serial_number=data.serial_number,
        model=data.model,
        status=data.status,
        fuel_percentage=data.fuel_percentage,
    )
    db.add(drone)
    db.commit()
    db.refresh(drone)
    return drone


def update_drone(db: Session, drone_id: int, data: DroneUpdate) -> Drone:
    """Var olan bir drone'u kısmi olarak günceller."""
    drone = get_drone(db, drone_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(drone, field, value)
    db.commit()
    db.refresh(drone)
    return drone


def delete_drone(db: Session, drone_id: int) -> None:
    """Bir drone'u siler."""
    drone = get_drone(db, drone_id)
    db.delete(drone)
    db.commit()
