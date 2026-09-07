from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.gps_data import GPSData
    from app.models.route import Route
    from app.models.user import User


class Vehicle(Base):
    """Vehicle entity representing a tracked transport unit."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        server_default="active",
        nullable=False,
    )
    route_id: Mapped[int | None] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    route: Mapped["Route | None"] = relationship(
        "Route",
        back_populates="vehicles",
    )
    gps_records: Mapped[list["GPSData"]] = relationship(
        "GPSData",
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="vehicle",
    )

    def __repr__(self) -> str:
        return f"<Vehicle id={self.id} vehicle_number={self.vehicle_number!r} status={self.status!r}>"
