from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class TelemetryLog(Base):
    """Bir drone'dan gelen tekil telemetri ölçümü."""

    __tablename__ = "telemetry_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(
        ForeignKey("drones.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[float] = mapped_column(Float, nullable=False)
    fuel_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    drone: Mapped["Drone"] = relationship(  # noqa: F821
        back_populates="telemetry_logs"
    )
