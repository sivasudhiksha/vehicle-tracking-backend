"""Schemas package for request and response models."""

from app.schemas.assignment import (
    AssignmentResponse,
    RouteResponse,
    UserSummaryResponse,
    VehicleResponse,
)
from app.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse
from app.schemas.gps import (
    GPSDataCreate,
    GPSDataResponse,
    GPSHistoryItem,
    GPSHistoryResponse,
)

__all__ = [
    "AssignmentResponse",
    "GPSDataCreate",
    "GPSDataResponse",
    "GPSHistoryItem",
    "GPSHistoryResponse",
    "LoginRequest",
    "RouteResponse",
    "TokenResponse",
    "UserProfileResponse",
    "UserSummaryResponse",
    "VehicleResponse",
]

