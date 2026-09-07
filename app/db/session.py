from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Configure connection arguments (e.g., connect_timeout for PostgreSQL)
connect_args = {}
if settings.DATABASE_URL.startswith("postgresql"):
    connect_args["connect_timeout"] = 3

# SQLAlchemy engine creation with connection health checking (pool_pre_ping).
# Note: create_engine does not establish an immediate socket connection, preventing
# startup crashes if the database server is temporarily offline or initializing.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

# Session factory for generating independent database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI database dependency.

    Yields a scoped database session and guarantees closure upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(custom_engine: Engine | None = None) -> tuple[bool, str | None]:
    """Safely tests database connectivity using a lightweight 'SELECT 1' query.

    Returns:
        tuple[bool, str | None]: (True, None) if connection succeeds, or (False, error_message)
        if connection fails. Does not raise unhandled exceptions.
    """
    target_engine = custom_engine if custom_engine is not None else engine
    try:
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)
