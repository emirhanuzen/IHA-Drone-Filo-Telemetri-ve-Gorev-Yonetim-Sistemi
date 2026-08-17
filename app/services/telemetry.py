"""Telemetri (TelemetryLog) iş mantığı.

NOT: Toplu (bulk) yükleme şimdilik SENKRON işleniyor. 5. fazda bu işlem
Celery worker'a devredilecek (asenkron); bu servis o zaman görevi kuyruğa
bırakacak şekilde güncellenecek.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.drone import Drone
from app.models.telemetry import TelemetryLog
from app.schemas.telemetry import TelemetryLogCreate


def get_telemetry(db: Session, telemetry_id: int) -> TelemetryLog:
    """Tek bir telemetri kaydını getirir; bulunamazsa 404 döner."""
    log = db.get(TelemetryLog, telemetry_id)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Telemetri kaydi bulunamadi"
        )
    return log


def list_telemetry(
    db: Session, drone_id: int | None = None, skip: int = 0, limit: int = 100
) -> list[TelemetryLog]:
    """Telemetri kayıtlarını listeler; drone_id verilirse filtreler."""
    stmt = select(TelemetryLog)
    if drone_id is not None:
        stmt = stmt.where(TelemetryLog.drone_id == drone_id)
    stmt = stmt.offset(skip).limit(limit).order_by(TelemetryLog.timestamp.desc())
    return list(db.scalars(stmt).all())


def _validate_drones_exist(db: Session, drone_ids: set[int]) -> None:
    """Verilen tüm drone_id'lerin gerçekten var olduğunu doğrular."""
    found = set(
        db.scalars(select(Drone.id).where(Drone.id.in_(drone_ids))).all()
    )
    missing = drone_ids - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Su drone id'leri bulunamadi: {sorted(missing)}",
        )


def _to_model(data: TelemetryLogCreate) -> TelemetryLog:
    """Şemayı ORM nesnesine dönüştürür (timestamp verilmemişse atlanır)."""
    fields = data.model_dump(exclude_none=True)
    return TelemetryLog(**fields)


def create_telemetry(db: Session, data: TelemetryLogCreate) -> TelemetryLog:
    """Tek bir telemetri kaydı oluşturur."""
    _validate_drones_exist(db, {data.drone_id})
    log = _to_model(data)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def create_telemetry_bulk(db: Session, items: list[TelemetryLogCreate]) -> int:
    """Telemetri kayıtlarını toplu (senkron) olarak yazar; yazılan sayıyı döner.

    5. fazda bu fonksiyonun gövdesi Celery task'ına devredilecek.
    """
    if not items:
        return 0

    drone_ids = {item.drone_id for item in items}
    _validate_drones_exist(db, drone_ids)

    logs = [_to_model(item) for item in items]
    db.add_all(logs)
    db.commit()
    return len(logs)
