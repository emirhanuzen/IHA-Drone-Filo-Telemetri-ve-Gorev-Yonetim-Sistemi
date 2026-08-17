from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import DroneStatus


class Drone(Base):
    """Filodaki bir İHA'yı temsil eder."""

    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[DroneStatus] = mapped_column(
        Enum(DroneStatus, values_callable=lambda e: [m.value for m in e]),
        default=DroneStatus.AKTIF,
        nullable=False,
    )
    fuel_percentage: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    missions: Mapped[list["Mission"]] = relationship(  # noqa: F821
        back_populates="drone", cascade="all, delete-orphan"
    )
    telemetry_logs: Mapped[list["TelemetryLog"]] = relationship(  # noqa: F821
        back_populates="drone", cascade="all, delete-orphan"
    )
