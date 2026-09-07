from typing import Annotated
from fastapi import APIRouter, Depends

from app.api.deps import require_assigned_vehicle
from app.models.vehicle import Vehicle
from app.schemas.assignment import VehicleResponse

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Get assigned vehicle details",
)
def get_vehicle(
    vehicle: Annotated[Vehicle, Depends(require_assigned_vehicle)],
) -> VehicleResponse:
    """Retrieves vehicle details if and only if the vehicle is assigned to the authenticated user.

    Returns HTTP 403 Forbidden if user requests an unassigned vehicle.
    """
    return VehicleResponse.model_validate(vehicle)
