from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.enums import AlertType
from app.schemas.alert import SensorAlertCreate, SensorAlertResponse
from app.services import alert as alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=SensorAlertResponse, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: SensorAlertCreate, db: Session = Depends(get_db)
) -> SensorAlertResponse:
    """Elle uyarı kaydı açar (ör. sinyal kaybı bildirimi)."""
    return alert_service.create_alert(db, payload)


@router.get("", response_model=list[SensorAlertResponse])
def list_alerts(
    drone_id: int | None = None,
    alert_type: AlertType | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[SensorAlertResponse]:
    return alert_service.list_alerts(
        db, drone_id=drone_id, alert_type=alert_type, skip=skip, limit=limit
    )


@router.get("/{alert_id}", response_model=SensorAlertResponse)
def get_alert(alert_id: int, db: Session = Depends(get_db)) -> SensorAlertResponse:
    return alert_service.get_alert(db, alert_id)
