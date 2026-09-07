"""API routes package."""

from app.api.routes.auth import router as auth_router
from app.api.routes.me import router as me_router
from app.api.routes.routes import router as routes_router
from app.api.routes.vehicles import router as vehicles_router

__all__ = ["auth_router", "me_router", "routes_router", "vehicles_router"]
