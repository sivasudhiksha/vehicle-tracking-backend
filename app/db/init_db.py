from sqlalchemy.engine import Engine

import app.models  # noqa: F401 (Ensures all models are imported and registered)
from app.db.base import Base
from app.db.session import engine


def init_db(target_engine: Engine | None = None) -> None:
    """Initializes database schema and tables for registered SQLAlchemy models.

    Creates tables in PostgreSQL/target engine for User, Route, Vehicle, and GPSData.
    """
    bind_engine = target_engine if target_engine is not None else engine
    Base.metadata.create_all(bind=bind_engine)


if __name__ == "__main__":
    print("Initializing database tables for all models...")
    init_db()
    print("Database tables initialized successfully.")
