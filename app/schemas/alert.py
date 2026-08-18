from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AlertSeverity, AlertType


class SensorAlertBase(BaseModel):
    drone_id: int
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.ORTA
    message: str = Field(..., max_length=256)


class SensorAlertCreate(SensorAlertBase):
    """Uyarılar normalde worker tarafından otomatik üretilir.

    Bu şema, elle uyarı girilmesi gereken durumlar (ör. sinyal kaybı bildirimi)
    için kullanılır.
    """

    telemetry_log_id: int | None = None
    timestamp: datetime | None = None


class SensorAlertResponse(SensorAlertBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telemetry_log_id: int | None
    timestamp: datetime
    created_at: datetime
