"""GPS service layer - business logic for GPS data ingestion and retrieval.

Separates database operations from route handlers following the
single-responsibility principle. All GPS-related queries go through
this module so route handlers remain thin and readable.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gps_data import GPSData
from app.models.vehicle import Vehicle
from app.schemas.gps import GPSDataCreate

# Maximum number of history records returnable in a single query.
# Prevents runaway queries on large datasets.
GPS_HISTORY_MAX_LIMIT: int = 500


def ingest_gps_record(payload: GPSDataCreate, db: Session) -> GPSData:
    """Persist an incoming GPS telemetry record.

    Validates that the target vehicle exists before creating the record.
    Payload values have already been validated by the Pydantic schema.

    Args:
        payload: Validated GPS data from the API request body.
        db: Active SQLAlchemy database session.

    Returns:
        GPSData: The newly created and committed GPS record ORM instance.

    Raises:
        ValueError: If the requested vehicle_id does not exist in the database.
    """
    vehicle = db.scalars(
        select(Vehicle).where(Vehicle.id == payload.vehicle_id)
    ).first()

    if vehicle is None:
        raise ValueError(f"Vehicle with id={payload.vehicle_id} does not exist.")

    gps_record = GPSData(
        vehicle_id=payload.vehicle_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        timestamp=payload.timestamp,
        speed=payload.speed,
    )
    db.add(gps_record)
    db.commit()
    db.refresh(gps_record)
    return gps_record


def get_latest_gps(vehicle_id: int, db: Session) -> GPSData | None:
    """Retrieve the most recent GPS record for a given vehicle.

    Uses the composite index (vehicle_id, timestamp) for efficient lookup.

    Args:
        vehicle_id: The vehicle whose latest GPS fix is requested.
        db: Active SQLAlchemy database session.

    Returns:
        GPSData | None: The newest GPS record, or None if no data exists.
    """
    return db.scalars(
        select(GPSData)
        .where(GPSData.vehicle_id == vehicle_id)
        .order_by(GPSData.timestamp.desc())
        .limit(1)
    ).first()


def get_gps_history(
    vehicle_id: int,
    db: Session,
    limit: int = 50,
) -> list[GPSData]:
    """Retrieve a time-ordered list of GPS records for a given vehicle.

    Uses the composite index (vehicle_id, timestamp) for efficient range scans.
    Records are returned newest-first.

    Args:
        vehicle_id: The vehicle whose GPS history is requested.
        db: Active SQLAlchemy database session.
        limit: Maximum number of records to return. Clamped to GPS_HISTORY_MAX_LIMIT.

    Returns:
        list[GPSData]: GPS records ordered by timestamp descending.
                       Returns an empty list when no records exist.
    """
    effective_limit = min(limit, GPS_HISTORY_MAX_LIMIT)
    rows = db.scalars(
        select(GPSData)
        .where(GPSData.vehicle_id == vehicle_id)
        .order_by(GPSData.timestamp.desc())
        .limit(effective_limit)
    ).all()
    return list(rows)