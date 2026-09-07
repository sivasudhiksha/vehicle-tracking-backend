"""GPS data ingestion API router.

Exposes:
  POST /gps  -- Authenticated endpoint to ingest a GPS telemetry record.

Authorization enforces that the authenticated user may only submit GPS
data for their own assigned vehicle. The vehicle_id in the request body
is compared against current_user.vehicle_id derived from the JWT.

Trust model:
  - vehicle ownership is NEVER trusted from the client.
  - The JWT sub claim is used to load the authenticated user.
  - user.vehicle_id is the source of truth for ownership.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.gps import GPSDataCreate, GPSDataResponse
from app.services.gps_service import ingest_gps_record

router = APIRouter(prefix="/gps", tags=["GPS"])


@router.post(
    "",
    response_model=GPSDataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a GPS telemetry record for an assigned vehicle",
    responses={
        201: {"description": "GPS record created successfully"},
        401: {"description": "Missing or invalid authentication token"},
        403: {"description": "Authenticated user is not authorized for the requested vehicle"},
        404: {"description": "Requested vehicle does not exist"},
        422: {"description": "Invalid GPS payload (coordinate bounds, negative speed, bad timestamp)"},
    },
)
def ingest_gps(
    payload: GPSDataCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GPSDataResponse:
    """Accept and store a GPS telemetry record for the authenticated user's vehicle.

    The authenticated user must have an assigned vehicle and may only submit
    GPS data for that vehicle. Requests targeting another vehicle are rejected
    with HTTP 403 Forbidden.

    - **vehicle_id**: must match the authenticated user's assigned vehicle.
    - **latitude**: must be in [-90, 90].
    - **longitude**: must be in [-180, 180].
    - **timestamp**: must be a valid timezone-aware datetime.
    - **speed**: must be >= 0.
    """
    # --- Authorization: confirm the user is assigned to the requested vehicle ---
    if current_user.vehicle_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have no assigned vehicle. GPS data cannot be submitted.",
        )

    if payload.vehicle_id != current_user.vehicle_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to submit GPS data for this vehicle.",
        )

    # --- Service layer: validate vehicle existence and persist record ---
    try:
        gps_record = ingest_gps_record(payload=payload, db=db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return GPSDataResponse.model_validate(gps_record)