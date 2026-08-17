"""Görev (Mission) iş mantığı.

İş kuralları burada uygulanır:
  * Bir drone aynı anda yalnızca BİR aktif göreve atanabilir.
  * Yakıtı %20'nin altındaki drone'a yeni görev atanamaz.
  * Görev tamamlandığında (veya iptal edildiğinde) drone yeniden 'aktif' olur.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.drone import Drone
from app.models.enums import DroneStatus, MissionStatus
from app.models.mission import Mission
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services import drone as drone_service

# Bir drone'u "meşgul" sayan görev durumları.
ACTIVE_MISSION_STATUSES = (MissionStatus.PLANLANDI, MissionStatus.DEVAM_EDIYOR)

# Yeni görev atamak için gereken asgari yakıt yüzdesi.
MIN_FUEL_FOR_ASSIGNMENT = 20.0


def get_mission(db: Session, mission_id: int) -> Mission:
    """Tek bir görevi getirir; bulunamazsa 404 döner."""
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gorev bulunamadi"
        )
    return mission


def list_missions(
    db: Session, drone_id: int | None = None, skip: int = 0, limit: int = 100
) -> list[Mission]:
    """Görevleri listeler; drone_id verilirse ona göre filtreler."""
    stmt = select(Mission)
    if drone_id is not None:
        stmt = stmt.where(Mission.drone_id == drone_id)
    stmt = stmt.offset(skip).limit(limit).order_by(Mission.id)
    return list(db.scalars(stmt).all())


def _has_active_mission(db: Session, drone_id: int) -> bool:
    """Drone'un halihazırda aktif (planlandı/devam ediyor) görevi var mı?"""
    stmt = select(Mission.id).where(
        Mission.drone_id == drone_id,
        Mission.status.in_(ACTIVE_MISSION_STATUSES),
    )
    return db.scalar(stmt) is not None


def create_mission(db: Session, data: MissionCreate) -> Mission:
    """İş kurallarını uygulayarak yeni bir görev oluşturur."""
    drone = drone_service.get_drone(db, data.drone_id)

    # Kural: yakıt %20'nin altındaysa atama yapılamaz.
    if drone.fuel_percentage < MIN_FUEL_FOR_ASSIGNMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Yakit seviyesi %20'nin altinda oldugu icin drone'a yeni gorev "
                "atanamaz"
            ),
        )

    # Kural: aynı anda yalnızca bir aktif görev.
    if _has_active_mission(db, drone.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Drone'un zaten aktif bir gorevi var, cifte atama engellendi",
        )

    mission = Mission(
        drone_id=drone.id,
        start_location=data.start_location,
        end_location=data.end_location,
        status=MissionStatus.PLANLANDI,
    )
    # Görev atanan drone artık "görevde".
    drone.status = DroneStatus.GOREVDE

    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def _apply_status_side_effects(drone: Drone, new_status: MissionStatus) -> None:
    """Görev durum değişiminin drone durumuna yansımasını uygular."""
    if new_status in (MissionStatus.TAMAMLANDI, MissionStatus.IPTAL):
        # Görev bittiğinde/iptal edildiğinde drone yeniden aktif olur.
        drone.status = DroneStatus.AKTIF
    elif new_status == MissionStatus.DEVAM_EDIYOR:
        drone.status = DroneStatus.GOREVDE


def update_mission(db: Session, mission_id: int, data: MissionUpdate) -> Mission:
    """Görevi günceller; durum değişiminde drone durumunu da ayarlar."""
    mission = get_mission(db, mission_id)
    fields = data.model_dump(exclude_unset=True)

    new_status = fields.get("status")
    if new_status is not None and new_status != mission.status:
        _apply_status_side_effects(mission.drone, new_status)

    for field, value in fields.items():
        setattr(mission, field, value)

    db.commit()
    db.refresh(mission)
    return mission


def delete_mission(db: Session, mission_id: int) -> None:
    """Bir görevi siler."""
    mission = get_mission(db, mission_id)
    db.delete(mission)
    db.commit()
