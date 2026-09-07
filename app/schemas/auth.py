from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """Schema for user authentication request."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    """Safe schema for returning basic user details without exposing sensitive data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    route_id: int | None = None
    vehicle_id: int | None = None
