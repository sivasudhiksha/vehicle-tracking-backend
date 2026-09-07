from typing import Annotated
from fastapi import APIRouter, Depends

from app.api.deps import require_assigned_route
from app.models.route import Route
from app.schemas.assignment import RouteResponse

router = APIRouter(prefix="/routes", tags=["Routes"])


@router.get(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Get assigned route details",
)
def get_route(
    route: Annotated[Route, Depends(require_assigned_route)],
) -> RouteResponse:
    """Retrieves route details if and only if the route is assigned to the authenticated user.

    Returns HTTP 403 Forbidden if user requests an unassigned route.
    """
    return RouteResponse.model_validate(route)
