"""Telemetri (TelemetryLog) iş mantığı.

Toplu (bulk) yükleme SENKRON işlenmez: API isteği yalnızca kaydı doğrular ve
görevi RabbitMQ kuyruğuna bırakır, veritabanına yazma işini Celery worker
üstlenir. Bu modüldeki fonksiyonlar iki gruba ayrılır:

  * API tarafı  -> kuyruğa görev bırakır (queue_* fonksiyonları)
  * Worker tarafı -> asıl veritabanı yazımını yapar (save_*/import_* fonksiyonları)
"""

import shutil
import uuid
from pathlib import Path

import pandas as pd
from celery.result import AsyncResult
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.models.drone import Drone
from app.models.telemetry import TelemetryLog
from app.schemas.telemetry import TelemetryLogCreate
from app.services import alert as alert_service

# Task adları; import döngüsü olmasın diye task'lar adlarıyla çağrılır.
TASK_PROCESS_BATCH = "telemetry.process_batch"
TASK_PROCESS_CSV = "telemetry.process_csv"

# CSV dosyasında bulunması zorunlu sütunlar.
CSV_REQUIRED_COLUMNS = {
    "drone_id",
    "latitude",
    "longitude",
    "altitude",
    "fuel_percentage",
    "speed",
}


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
    """Tek bir telemetri kaydı oluşturur (senkron) ve kurallardan geçirir."""
    _validate_drones_exist(db, {data.drone_id})
    log = _to_model(data)
    db.add(log)
    db.flush()

    alerts = alert_service.evaluate_logs(db, [log])
    payloads = [alert_service.build_event_payload(a) for a in alerts]
    db.commit()

    alert_service.publish_alert_created(payloads)
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


def store_upload_file(upload: UploadFile) -> str:
    """Yüklenen CSV'yi paylaşılan dizine kopyalar; dosya yolunu döner.

    Dosya belleğe tamamen alınmaz; worker'ın da erişebildiği ortak dizine
    parça parça yazılır.
    """
    filename = upload.filename or "telemetry.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yalnizca .csv uzantili dosyalar kabul edilir",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{uuid.uuid4().hex}.csv"

    with target.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return str(target)


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


def _persist_records(
    db: Session, records: list[dict], known_ids: set[int] | None = None
) -> dict:
    """Ham kayıtları doğrulayıp veritabanına yazar; özet döner.

    Geçersiz kayıtlar ve var olmayan bir drone'a ait kayıtlar atlanır —
    tek bir bozuk satır yüzünden tüm paket düşmez.
    """
    if not records:
        return {"received": 0, "inserted": 0, "skipped": 0, "alerts": 0}

    valid: list[TelemetryLogCreate] = []
    skipped = 0
    for record in records:
        try:
            valid.append(TelemetryLogCreate.model_validate(record))
        except ValidationError:
            skipped += 1

    if known_ids is None:
        known_ids = _existing_drone_ids(db, {item.drone_id for item in valid})

    logs = []
    for item in valid:
        if item.drone_id not in known_ids:
            skipped += 1
            continue
        logs.append(_to_model(item))

    alert_count = 0
    if logs:
        db.add_all(logs)
        # Uyarı kuralları için kayıtların id ve zaman damgası gerekir.
        db.flush()

        alerts = alert_service.evaluate_logs(db, logs)
        payloads = [alert_service.build_event_payload(a) for a in alerts]
        db.commit()

        # Event'ler ancak kayıtlar kalıcı olduktan sonra yayınlanır.
        alert_service.publish_alert_created(payloads)
        alert_count = len(payloads)

    return {
        "received": len(records),
        "inserted": len(logs),
        "skipped": skipped,
        "alerts": alert_count,
    }


def save_telemetry_batch(db: Session, records: list[dict]) -> dict:
    """Worker tarafından çağrılır: telemetri paketini veritabanına yazar."""
    return _persist_records(db, records)


def _chunk_to_records(chunk: pd.DataFrame) -> list[dict]:
    """Bir pandas parçasını, şemaya verilebilecek sözlük listesine çevirir."""
    missing = CSV_REQUIRED_COLUMNS - set(chunk.columns)
    if missing:
        raise ValueError(f"CSV dosyasinda eksik sutunlar var: {sorted(missing)}")

    # timestamp isteğe bağlı: dosyada varsa alınır, yoksa sunucu zamanı kullanılır.
    columns = sorted(CSV_REQUIRED_COLUMNS)
    if "timestamp" in chunk.columns:
        columns.append("timestamp")

    frame = chunk[columns]
    # Boş hücreler (NaN) None'a çevrilir; şema bunları "verilmemiş" sayar.
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def import_telemetry_csv(db: Session, file_path: str) -> dict:
    """Büyük bir telemetri CSV'sini pandas ile PARÇA PARÇA okuyup yazar.

    Dosya tek seferde belleğe alınmaz; `csv_chunk_size` kadarlık parçalar
    hâlinde okunur ve her parça ayrı bir toplu yazma olarak işlenir.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV dosyasi bulunamadi: {file_path}")

    # Drone kimlikleri dosya boyunca sabit; tek sorguyla okunup yeniden kullanılır.
    known_ids = set(db.scalars(select(Drone.id)).all())

    totals = {"received": 0, "inserted": 0, "skipped": 0, "alerts": 0, "chunks": 0}
    for chunk in pd.read_csv(path, chunksize=settings.csv_chunk_size):
        summary = _persist_records(db, _chunk_to_records(chunk), known_ids)
        for key in ("received", "inserted", "skipped", "alerts"):
            totals[key] += summary[key]
        totals["chunks"] += 1

    return totals
