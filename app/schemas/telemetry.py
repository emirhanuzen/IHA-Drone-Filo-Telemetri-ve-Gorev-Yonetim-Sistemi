from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelemetryLogBase(BaseModel):
    drone_id: int
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(..., description="Metre cinsinden irtifa")
    fuel_percentage: float = Field(..., ge=0, le=100)
    speed: float = Field(..., ge=0, description="km/s cinsinden hiz")
    timestamp: datetime | None = Field(
        None, description="Ölçüm zamanı; verilmezse sunucu zamanı kullanılır"
    )


class TelemetryLogCreate(TelemetryLogBase):
    pass


class TelemetryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    drone_id: int
    timestamp: datetime
    latitude: float
    longitude: float
    altitude: float
    fuel_percentage: float
    speed: float
    created_at: datetime


class BulkTelemetryResult(BaseModel):
    """Toplu telemetri yüklemesinin özeti."""

    received: int = Field(..., description="Gelen kayıt sayısı")
    inserted: int = Field(..., description="Veritabanına yazılan kayıt sayısı")
