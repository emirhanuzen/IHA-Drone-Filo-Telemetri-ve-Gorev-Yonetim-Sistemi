"""Telemetri (TelemetryLog) iş mantığı.

Toplu (bulk) yükleme SENKRON işlenmez: API isteği yalnızca kaydı doğrular ve
görevi RabbitMQ kuyruğuna bırakır, veritabanına yazma işini Celery worker
üstlenir. Bu modüldeki fonksiyonlar iki gruba ayrılır:

  * API tarafı  -> kuyruğa görev bırakır (queue_* fonksiyonları)
  * Worker tarafı -> asıl veritabanı yazımını yapar (save_*/import_* fonksiyonları)
"""

from celery.result import AsyncResult
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.models.drone import Drone
from app.models.telemetry import TelemetryLog
from app.schemas.telemetry import TelemetryLogCreate

# Task adları; import döngüsü olmasın diye task'lar adlarıyla çağrılır.
TASK_PROCESS_BATCH = "telemetry.process_batch"
TASK_PROCESS_CSV = "telemetry.process_csv"


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


def _existing_drone_ids(db: Session, drone_ids: set[int]) -> set[int]:
    """Verilen id'lerden veritabanında gerçekten var olanları döner."""
    if not drone_ids:
        return set()
    return set(db.scalars(select(Drone.id).where(Drone.id.in_(drone_ids))).all())


def _validate_drones_exist(db: Session, drone_ids: set[int]) -> None:
    """Verilen tüm drone_id'lerin gerçekten var olduğunu doğrular."""
    missing = drone_ids - _existing_drone_ids(db, drone_ids)
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
    """Tek bir telemetri kaydı oluşturur (senkron)."""
    _validate_drones_exist(db, {data.drone_id})
    log = _to_model(data)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ---------------------------------------------------------------------------
# API tarafı: kuyruğa bırakma
# ---------------------------------------------------------------------------


def queue_telemetry_bulk(db: Session, items: list[TelemetryLogCreate]) -> str:
    """Toplu telemetri paketini worker'a devreder; task id döner.

    Veritabanına yazma işi worker'a ait; burada yalnızca drone'ların varlığı
    doğrulanır ki hatalı istek anında geri bildirilebilsin.
    """
    _validate_drones_exist(db, {item.drone_id for item in items})

    payload = [item.model_dump(mode="json") for item in items]
    result = celery_app.send_task(TASK_PROCESS_BATCH, args=[payload])
    return result.id


def queue_telemetry_csv(file_path: str) -> str:
    """CSV dosyasının işlenmesini worker'a devreder; task id döner."""
    result = celery_app.send_task(TASK_PROCESS_CSV, args=[file_path])
    return result.id


def get_task_state(task_id: str) -> dict:
    """Kuyruğa bırakılan bir telemetri görevinin durumunu döner."""
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
    }


# ---------------------------------------------------------------------------
# Worker tarafı: asıl veritabanı yazımı
# ---------------------------------------------------------------------------


def save_telemetry_batch(db: Session, records: list[dict]) -> dict:
    """Worker tarafından çağrılır: telemetri kayıtlarını veritabanına yazar.

    Worker bir HTTP isteği içinde çalışmadığı için hatalı kayıtlarda istisna
    fırlatmak yerine o kayıtları atlar ve özet döner.
    """
    if not records:
        return {"received": 0, "inserted": 0, "skipped": 0}

    valid: list[TelemetryLogCreate] = []
    skipped = 0
    for record in records:
        try:
            valid.append(TelemetryLogCreate.model_validate(record))
        except ValidationError:
            skipped += 1

    known_ids = _existing_drone_ids(db, {item.drone_id for item in valid})
    logs = []
    for item in valid:
        if item.drone_id not in known_ids:
            skipped += 1
            continue
        logs.append(_to_model(item))

    if logs:
        db.add_all(logs)
        db.commit()

    return {"received": len(records), "inserted": len(logs), "skipped": skipped}
