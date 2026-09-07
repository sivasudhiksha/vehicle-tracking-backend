import json
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator


class UserSummaryResponse(BaseModel):
    """Minimal public user information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class RouteResponse(BaseModel):
    """Route details response schema with parsed coordinates."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    start_location: str
    end_location: str
    route_coordinates: Any = None

    @field_validator("route_coordinates", mode="before")
    @classmethod
    def parse_coordinates(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value


class VehicleResponse(BaseModel):
    """Vehicle details response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_number: str
    status: str
    route_id: int | None = None


class AssignmentResponse(BaseModel):
    """Consolidated user route and vehicle assignment schema."""

    user: UserSummaryResponse
    route: RouteResponse | None = None
    vehicle: VehicleResponse | None = None
