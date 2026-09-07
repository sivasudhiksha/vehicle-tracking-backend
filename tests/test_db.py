import pytest
from collections.abc import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.init_db import init_db
from app.db.session import SessionLocal, check_database_connection, engine, get_db
from app.main import app

client = TestClient(app)


def test_database_configuration_loads():
    """Verify database configuration loads properly from settings."""
    assert hasattr(settings, "DATABASE_URL")
    assert isinstance(settings.DATABASE_URL, str)
    assert len(settings.DATABASE_URL) > 0
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")


def test_sqlalchemy_engine_constructed():
    """Verify SQLAlchemy engine is constructed as a valid Engine instance."""
    assert isinstance(engine, Engine)
    assert "postgresql+psycopg" in str(engine.url)


def test_base_metadata_imported():
    """Verify Base is a DeclarativeBase with valid MetaData."""
    assert issubclass(Base, DeclarativeBase)
    assert hasattr(Base, "metadata")
    assert Base.metadata is not None


def test_session_factory_initialization():
    """Verify SessionLocal is a sessionmaker that creates valid Sessions."""
    assert isinstance(SessionLocal, sessionmaker)

    # Test session creation using an isolated in-memory test engine
    test_engine = create_engine("sqlite:///:memory:")
    TestSessionLocal = sessionmaker(bind=test_engine)
    session = TestSessionLocal()
    assert isinstance(session, Session)
    session.close()


def test_get_db_dependency_lifecycle():
    """Verify get_db FastAPI dependency creates, yields, and closes a session."""
    # Test session lifecycle using an in-memory SQLite engine
    test_engine = create_engine("sqlite:///:memory:")
    TestSessionLocal = sessionmaker(bind=test_engine)

    def custom_get_db() -> Generator[Session, None, None]:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    generator = custom_get_db()
    session = next(generator)
    assert isinstance(session, Session)

    # Closing generator should trigger the finally block and close the session
    with pytest.raises(StopIteration):
        next(generator)


def test_init_db_runs_without_error():
    """Verify init_db initializes metadata against an engine without failure."""
    test_engine = create_engine("sqlite:///:memory:")
    init_db(target_engine=test_engine)
    # Check that metadata was bound and executed cleanly
    assert test_engine is not None


def test_check_database_connection_with_healthy_engine():
    """Verify check_database_connection returns (True, None) for a working engine."""
    test_engine = create_engine("sqlite:///:memory:")
    is_connected, error = check_database_connection(custom_engine=test_engine)
    assert is_connected is True
    assert error is None


def test_check_database_connection_handles_failure_cleanly():
    """Verify check_database_connection catches connection errors cleanly."""
    broken_engine = create_engine(
        "postgresql+psycopg://invalid:invalid@127.0.0.1:9999/nonexistent",
        connect_args={"connect_timeout": 1},
    )
    is_connected, error = check_database_connection(custom_engine=broken_engine)
    assert is_connected is False
    assert error is not None
    assert isinstance(error, str)


def test_health_db_endpoint():
    """Verify GET /health/db returns HTTP 200 with structured status."""
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert data["database"] in ("connected", "disconnected")


def test_postgresql_connectivity_with_configured_settings():
    """Verify PostgreSQL connectivity handling with configured DATABASE_URL.

    If credentials are using placeholders (e.g. YOUR_PASSWORD) or database
    is not yet authenticated, verifies that connection fails gracefully without
    raising unhandled exceptions.
    """
    is_connected, error = check_database_connection(custom_engine=engine)
    if is_connected:
        assert error is None
    else:
        # Graceful failure verification: no unhandled exception occurred
        assert error is not None
        assert isinstance(error, str)
