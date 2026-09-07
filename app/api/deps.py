from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.route import Route
from app.models.user import User
from app.models.vehicle import Vehicle

# HTTPBearer security scheme extracts the Bearer token from the Authorization header
security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """FastAPI dependency to authenticate requests and return the current User ORM instance.

    Validates signature, expiration, user identifier, and loads the active user from the database.
    Raises HTTP 401 Unauthorized with WWW-Authenticate header for any failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise credentials_exception

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        raise credentials_exception

    user = db.scalars(select(User).where(User.id == user_id)).first()
    if user is None:
        raise credentials_exception

    return user


# Reusable alias for semantic clarity
require_current_user = get_current_user


def validate_user_assignment(user: User, db: Session) -> tuple[Route, Vehicle]:
    """Validates that a user's assigned route and vehicle exist and are internally consistent.

    Ensures:
    1. User has both route_id and vehicle_id populated.
    2. Route and Vehicle records exist in the database.
    3. Vehicle.route_id matches User.route_id (no cross-route inconsistencies).

    Returns:
        tuple[Route, Vehicle]: The loaded Route and Vehicle instances.

    Raises:
        HTTPException(403): If the assignment is missing, non-existent, or inconsistent.
    """
    if user.route_id is None or user.vehicle_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no assigned route or vehicle",
        )

    route = db.scalars(select(Route).where(Route.id == user.route_id)).first()
    vehicle = db.scalars(select(Vehicle).where(Vehicle.id == user.vehicle_id)).first()

    if route is None or vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assigned route or vehicle does not exist",
        )

    if vehicle.route_id != user.route_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inconsistent assignment: vehicle route does not match user route",
        )

    return route, vehicle


def require_assigned_route(
    route_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Route:
    """Verifies that the requested route_id matches the authenticated user's assigned route.

    Raises HTTP 403 Forbidden if user is not authorized for the requested route.
    """
    if current_user.route_id is None or route_id != current_user.route_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this route",
        )

    route, _ = validate_user_assignment(current_user, db)
    return route


def require_assigned_vehicle(
    vehicle_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Vehicle:
    """Verifies that the requested vehicle_id matches the authenticated user's assigned vehicle.

    Raises HTTP 403 Forbidden if user is not authorized for the requested vehicle.
    """
    if current_user.vehicle_id is None or vehicle_id != current_user.vehicle_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this vehicle",
        )

    _, vehicle = validate_user_assignment(current_user, db)
    return vehicle
