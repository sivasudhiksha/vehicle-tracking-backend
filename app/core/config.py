import os
from pathlib import Path
from dotenv import load_dotenv

# Path to backend directory and .env file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load local .env if it exists
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    """Application settings loaded from environment variables."""

    PROJECT_NAME: str = "Vehicle Tracking Backend"
    PROJECT_VERSION: str = "0.1.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # PostgreSQL Database URL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/vehicle_tracking",
    )

    # JWT Authentication Settings
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "development-secret-key-replace-in-production-with-random-32-byte-hex",
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # MQTT Broker Configuration
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_USERNAME: str | None = os.getenv("MQTT_USERNAME") or None
    MQTT_PASSWORD: str | None = os.getenv("MQTT_PASSWORD") or None
    MQTT_TOPIC: str = os.getenv("MQTT_TOPIC", "vehicles/+/gps")


settings = Settings()

