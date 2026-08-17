from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import MissionStatus


class Mission(Base):
    """Bir drone'a atanan uçuş görevini temsil eder."""

    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(
        ForeignKey("drones.id", ondelete="CASCADE"), index=True
    )
    start_location: Mapped[str] = mapped_column(String(256))
    end_location: Mapped[str] = mapped_column(String(256))
    status: Mapped[MissionStatus] = mapped_column(
        Enum(MissionStatus, values_callable=lambda e: [m.value for m in e]),
        default=MissionStatus.PLANLANDI,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    drone: Mapped["Drone"] = relationship(back_populates="missions")  # noqa: F821
