"""GPS data Pydantic schemas for request validation and response serialization."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GPSDataCreate(BaseModel):
    """Schema for incoming GPS data ingestion request.

    All coordinate and speed fields are validated against physical bounds.
    Timestamps are normalized to UTC.
    """

    vehicle_id: Annotated[int, Field(gt=0, description="Positive vehicle identifier")]
    latitude: Annotated[
        float,
        Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees (-90 to 90)"),
    ]
    longitude: Annotated[
        float,
        Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees (-180 to 180)"),
    ]
    timestamp: Annotated[
        datetime,
        Field(description="GPS fix timestamp (timezone-aware ISO 8601)"),
    ]
    speed: Annotated[
        float,
        Field(ge=0.0, description="Vehicle speed in km/h (must not be negative)"),
    ] = 0.0

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_and_require_timezone(cls, value: object) -> datetime:
        """Ensure timestamp is a valid timezone-aware datetime.

        Accepts:
          - datetime objects (with or without tzinfo)
          - ISO 8601 strings (with or without UTC offset)

        Naive datetimes and strings without timezone info raise ValueError.
        """
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid datetime string: {value!r}")
        else:
            raise ValueError(f"Unsupported timestamp type: {type(value)}")

        if dt.tzinfo is None:
            raise ValueError(
                "Timestamp must be timezone-aware. "
                "Append 'Z' or a UTC offset (e.g. '+00:00') to the datetime string."
            )
        # Normalize to UTC
        return dt.astimezone(timezone.utc)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vehicle_id": 1,
                "latitude": 11.0168,
                "longitude": 76.9558,
                "timestamp": "2026-09-06T10:30:00Z",
                "speed": 42.5,
            }
        }
    )


class GPSDataResponse(BaseModel):
    """Schema for GPS data record returned from the API.

    Does not expose internal database fields, credentials, or user data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    latitude: float
    longitude: float
    timestamp: datetime
    speed: float | None = None


class GPSHistoryItem(BaseModel):
    """Schema for individual GPS history record item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    timestamp: datetime
    speed: float | None = None


class GPSHistoryResponse(BaseModel):
    """Schema for GPS history response payload for a vehicle."""

    vehicle_id: int
    records: list[GPSHistoryItem]