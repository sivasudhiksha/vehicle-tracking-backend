from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.gps import router as gps_router
from app.api.routes.me import router as me_router
from app.api.routes.routes import router as routes_router
from app.api.routes.vehicles import router as vehicles_router
from app.core.config import settings
from app.db.session import check_database_connection
from app.mqtt.client import start_mqtt_subscriber, stop_mqtt_subscriber


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Application lifespan manager for background services (e.g. MQTT subscriber)."""
    start_mqtt_subscriber()
    yield
    stop_mqtt_subscriber()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API foundation for GPS-based Vehicle Tracking System",
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)


# Configure CORS for mobile/web client integration
raw_origins = settings.CORS_ORIGINS
if raw_origins.strip() == "*":
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router, prefix="/auth")
app.include_router(gps_router)
app.include_router(me_router)
app.include_router(routes_router)
app.include_router(vehicles_router)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint to verify backend service status.

    Fast, lightweight check that confirms the FastAPI application is alive.
    Does not perform database queries per request.
    """
    return {
        "status": "ok",
        "service": "vehicle-tracking-backend",
        "version": settings.PROJECT_VERSION,
    }


@app.get("/health/db", tags=["Health"])
def health_database_check():
    """Dedicated endpoint to verify PostgreSQL database connectivity.

    Separated from the primary health check to avoid query overhead on standard heartbeats.
    """
    is_connected, error_message = check_database_connection()
    if is_connected:
        return {
            "status": "ok",
            "database": "connected",
        }
    return {
        "status": "unavailable",
        "database": "disconnected",
        "detail": error_message,
    }
