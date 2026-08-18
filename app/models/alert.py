from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import AlertSeverity, AlertType


class SensorAlert(Base):
    """Telemetri verisinden otomatik üretilen sensör uyarısı."""

    __tablename__ = "sensor_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(
        ForeignKey("drones.id", ondelete="CASCADE"), index=True
    )
    telemetry_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("telemetry_logs.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, values_callable=lambda e: [m.value for m in e]),
        index=True,
        nullable=False,
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, values_callable=lambda e: [m.value for m in e]),
        default=AlertSeverity.ORTA,
        nullable=False,
    )
    message: Mapped[str] = mapped_column(String(256))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    drone: Mapped["Drone"] = relationship(back_populates="alerts")  # noqa: F821
