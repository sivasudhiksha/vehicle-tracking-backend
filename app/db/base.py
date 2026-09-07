from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.x declarative models."""
    pass


# Ensure models are registered in Base.metadata when Base is imported
import app.models  # noqa: E402, F401
