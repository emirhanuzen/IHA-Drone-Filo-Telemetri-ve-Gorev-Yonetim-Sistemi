from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MissionStatus


class MissionBase(BaseModel):
    start_location: str = Field(..., max_length=256, examples=["41.01,28.97"])
    end_location: str = Field(..., max_length=256, examples=["39.92,32.85"])


class MissionCreate(MissionBase):
    drone_id: int


class MissionUpdate(BaseModel):
    """Kısmi güncelleme; genellikle durum geçişi için kullanılır."""

    start_location: str | None = Field(None, max_length=256)
    end_location: str | None = Field(None, max_length=256)
    status: MissionStatus | None = None


class MissionResponse(MissionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    drone_id: int
    status: MissionStatus
    created_at: datetime
    updated_at: datetime
