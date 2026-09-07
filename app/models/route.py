from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vehicle import Vehicle


class Route(Base):
    """Route entity representing a predefined path assigned to vehicles and users."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_location: Mapped[str] = mapped_column(String(255), nullable=False)
    end_location: Mapped[str] = mapped_column(String(255), nullable=False)
    route_coordinates: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    vehicles: Mapped[list["Vehicle"]] = relationship(
        "Vehicle",
        back_populates="route",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="route",
    )

    def __repr__(self) -> str:
        return f"<Route id={self.id} name={self.name!r}>"
