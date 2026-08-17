from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.telemetry import (
    BulkTelemetryResult,
    TelemetryLogCreate,
    TelemetryLogResponse,
)
from app.services import telemetry as telemetry_service

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post(
    "/bulk", response_model=BulkTelemetryResult, status_code=status.HTTP_201_CREATED
)
def create_telemetry_bulk(
    payload: list[TelemetryLogCreate] = Body(..., min_length=1),
    db: Session = Depends(get_db),
) -> BulkTelemetryResult:
    """Telemetri kayıtlarını toplu olarak (JSON dizisi) alır.

    Şimdilik senkron işlenir; 5. fazda Celery worker'a devredilecek.
    """
    inserted = telemetry_service.create_telemetry_bulk(db, payload)
    return BulkTelemetryResult(received=len(payload), inserted=inserted)


@router.post("", response_model=TelemetryLogResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/{telemetry_id}", response_model=TelemetryLogResponse)
def get_telemetry(
    telemetry_id: int, db: Session = Depends(get_db)
) -> TelemetryLogResponse:
    return telemetry_service.get_telemetry(db, telemetry_id)
