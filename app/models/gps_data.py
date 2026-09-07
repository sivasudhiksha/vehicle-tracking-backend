from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle


class GPSData(Base):
    """GPS telemetry entity recording geospatial data received from vehicles."""

    __tablename__ = "gps_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    speed: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship(
        "Vehicle",
        back_populates="gps_records",
    )

    # Composite index for vehicle location history filtering & ordering
    __table_args__ = (
        Index("ix_gps_data_vehicle_timestamp", "vehicle_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<GPSData id={self.id} vehicle_id={self.vehicle_id} "
            f"lat={self.latitude} lon={self.longitude} time={self.timestamp}>"
        )
