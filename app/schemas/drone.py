from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DroneStatus


class DroneBase(BaseModel):
    serial_number: str = Field(..., max_length=64, examples=["IHA-001"])
    model: str = Field(..., max_length=128, examples=["Bayraktar TB2"])
    fuel_percentage: float = Field(100.0, ge=0, le=100)


class DroneCreate(DroneBase):
    status: DroneStatus = DroneStatus.AKTIF


class DroneUpdate(BaseModel):
    """Kısmi güncelleme; yalnızca verilen alanlar değiştirilir."""

    model: str | None = Field(None, max_length=128)
    status: DroneStatus | None = None
    fuel_percentage: float | None = Field(None, ge=0, le=100)


class DroneResponse(DroneBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: DroneStatus
    created_at: datetime
    updated_at: datetime
