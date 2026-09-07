from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, validate_user_assignment
from app.db.session import get_db
from app.models.user import User
from app.schemas.assignment import (
    AssignmentResponse,
    RouteResponse,
    UserSummaryResponse,
    VehicleResponse,
)
from app.schemas.gps import GPSDataResponse, GPSHistoryItem, GPSHistoryResponse
from app.services.gps_service import get_gps_history, get_latest_gps

router = APIRouter(prefix="/me", tags=["Assignment & Location"])


@router.get(
    "/assignment",
    response_model=AssignmentResponse,
    summary="Get authenticated user's assigned route and vehicle",
)
def get_user_assignment(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AssignmentResponse:
    """Returns the authenticated user's single assigned route and vehicle.

    Derives user identity strictly from the verified JWT.
    Validates internal consistency between user and vehicle route assignments.
    """
    user_summary = UserSummaryResponse.model_validate(current_user)

    # Safe response if user has no assigned resources
    if current_user.route_id is None and current_user.vehicle_id is None:
        return AssignmentResponse(user=user_summary, route=None, vehicle=None)

    # Validates consistency (User.route_id == Vehicle.route_id)
    route, vehicle = validate_user_assignment(current_user, db)

    return AssignmentResponse(
        user=user_summary,
        route=RouteResponse.model_validate(route),
        vehicle=VehicleResponse.model_validate(vehicle),
    )


@router.get(
    "/vehicle/location",
    response_model=GPSDataResponse,
    summary="Get latest GPS location for authenticated user's assigned vehicle",
)
def get_my_vehicle_location(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GPSDataResponse:
    """Retrieve the newest GPS telemetry fix for the user's assigned vehicle.

    Authorization is strictly derived from the authenticated JWT user identity.
    Returns HTTP 404 if the user has no assigned vehicle or if no GPS telemetry exists.
    """
    if current_user.vehicle_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User has no assigned vehicle",
        )

    latest_gps = get_latest_gps(vehicle_id=current_user.vehicle_id, db=db)
    if latest_gps is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GPS data available for assigned vehicle",
        )

    return GPSDataResponse.model_validate(latest_gps)


@router.get(
    "/vehicle/history",
    response_model=GPSHistoryResponse,
    summary="Get GPS history for authenticated user's assigned vehicle",
)
def get_my_vehicle_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=1000,
            description="Maximum number of historical records to return (1 to 1000, default 100)",
        ),
    ] = 100,
) -> GPSHistoryResponse:

    """Retrieve historical GPS telemetry records for the user's assigned vehicle.

    Authorization is strictly derived from the authenticated JWT user identity.
    Records are returned newest-first.
    Returns HTTP 404 if the user has no assigned vehicle.
    Returns an empty list of records if no GPS telemetry exists for the assigned vehicle.
    """
    if current_user.vehicle_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User has no assigned vehicle",
        )

    history = get_gps_history(vehicle_id=current_user.vehicle_id, db=db, limit=limit)
    items = [GPSHistoryItem.model_validate(record) for record in history]

    return GPSHistoryResponse(
        vehicle_id=current_user.vehicle_id,
        records=items,
    )

