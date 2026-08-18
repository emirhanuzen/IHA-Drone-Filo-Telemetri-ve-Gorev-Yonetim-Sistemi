from fastapi import APIRouter, Body, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_telemetry_sender
from app.schemas.telemetry import (
    BulkTelemetryAccepted,
    CsvUploadAccepted,
    TaskStatusResponse,
    TelemetryLogCreate,
    TelemetryLogResponse,
)
from app.services import telemetry as telemetry_service

# Telemetri gönderimi operator'ün (ve admin'in) yetkisindedir; okuma tüm
# rollere açıktır.
router = APIRouter(
    prefix="/telemetry", tags=["telemetry"], dependencies=[Depends(get_current_user)]
)


@router.post(
    "/bulk",
    response_model=BulkTelemetryAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_telemetry_sender)],
)
def create_telemetry_bulk(
    payload: list[TelemetryLogCreate] = Body(..., min_length=1),
    db: Session = Depends(get_db),
) -> BulkTelemetryAccepted:
    """Telemetri kayıtlarını toplu olarak (JSON dizisi) alır.

    Kayıtlar senkron yazılmaz; istek doğrulanıp Celery worker'a devredilir ve
    202 Accepted ile birlikte takip için bir task id döner.
    """
    task_id = telemetry_service.queue_telemetry_bulk(db, payload)
    return BulkTelemetryAccepted(received=len(payload), task_id=task_id)


@router.post(
    "/upload-csv",
    response_model=CsvUploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_telemetry_sender)],
)
def upload_telemetry_csv(file: UploadFile = File(...)) -> CsvUploadAccepted:
    """Büyük bir telemetri CSV dosyasını yükler.

    Dosya ortak dizine alınır ve worker'a devredilir; worker dosyayı pandas
    ile parça parça okuyup yazar.
    """
    file_path = telemetry_service.store_upload_file(file)
    task_id = telemetry_service.queue_telemetry_csv(file_path)
    return CsvUploadAccepted(filename=file.filename or "telemetry.csv", task_id=task_id)


@router.post(
    "",
    response_model=TelemetryLogResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_telemetry_sender)],
)
def create_telemetry(
    payload: TelemetryLogCreate, db: Session = Depends(get_db)
) -> TelemetryLogResponse:
    return telemetry_service.create_telemetry(db, payload)


@router.get("", response_model=list[TelemetryLogResponse])
def list_telemetry(
    drone_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[TelemetryLogResponse]:
    return telemetry_service.list_telemetry(db, drone_id=drone_id, skip=skip, limit=limit)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    """Kuyruğa bırakılan toplu yükleme görevinin durumunu sorgular."""
    return TaskStatusResponse(**telemetry_service.get_task_state(task_id))


@router.get("/{telemetry_id}", response_model=TelemetryLogResponse)
def get_telemetry(
    telemetry_id: int, db: Session = Depends(get_db)
) -> TelemetryLogResponse:
    return telemetry_service.get_telemetry(db, telemetry_id)
