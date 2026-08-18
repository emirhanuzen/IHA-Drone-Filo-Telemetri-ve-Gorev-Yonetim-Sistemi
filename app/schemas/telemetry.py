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


class BulkTelemetryAccepted(BaseModel):
    """Toplu telemetri isteğinin kuyruğa alındığını bildirir.

    Kayıtlar bu yanıt dönerken henüz yazılmamıştır; yazma işini Celery worker
    üstlenir. İşin durumu `task_id` ile sorgulanabilir.
    """

    received: int = Field(..., description="Kuyruğa alınan kayıt sayısı")
    task_id: str = Field(..., description="Celery görev kimliği")
    status: str = Field("kuyruga_alindi", description="İsteğin anlık durumu")


class TaskStatusResponse(BaseModel):
    """Kuyruğa bırakılmış bir telemetri görevinin durumu."""

    task_id: str
    state: str = Field(..., description="PENDING / STARTED / SUCCESS / FAILURE")
    result: dict | None = Field(None, description="Görev tamamlandıysa özeti")
