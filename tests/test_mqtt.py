"""Phase 8 -- MQTT GPS Ingestion & GPS Simulator Tests.

Tests cover all required Phase 8 scenarios:
 1. Valid MQTT payload is accepted and stored.
 2. Invalid latitude (< -90 or > 90) rejected.
 3. Invalid longitude (< -180 or > 180) rejected.
 4. Negative speed rejected.
 5. Invalid vehicle ID rejected.
 6. Invalid timestamp (naive or malformed) rejected.
 7. Nonexistent vehicle handled correctly (returns None, no crash).
 8. Valid message creates GPSData record with correct attributes.
 9. Matching topic vehicle ID and payload vehicle ID accepted.
10. Mismatched topic vehicle ID and payload vehicle ID rejected.
11. Malformed JSON payload handled safely.
12. Missing required fields handled safely.
13. MQTT handler does not crash on bad or unexpected input.
14. Existing GPS service is called during MQTT message processing.
15. MQTT client startup/shutdown lifecycle does not block or break FastAPI when broker is unreachable.
16. Existing REST /gps endpoint continues working normally.
17. Existing authentication dependencies and token verification pass.
18. Existing assignment authorization controls pass.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import GPSData, Vehicle
from app.mqtt.client import create_mqtt_client, start_mqtt_subscriber, stop_mqtt_subscriber
from app.mqtt.handlers import extract_vehicle_id_from_topic, handle_mqtt_message
from app.schemas.auth import TokenResponse

VALID_TS = "2026-09-06T10:30:00Z"
VALID_LAT = 11.0168
VALID_LON = 76.9558
VALID_SPEED = 42.5


@pytest.fixture(scope="module")
def seeded_engine():
    """Module-scoped in-memory SQLite engine initialized with seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=engine)
    return engine


@pytest.fixture(scope="module")
def db_session_factory(seeded_engine):
    """Factory creating database sessions bound to the seeded engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=seeded_engine)


@pytest.fixture(scope="module")
def client(seeded_engine):
    """FastAPI TestClient with database dependency overridden."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=seeded_engine
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper function to generate test payloads
# ---------------------------------------------------------------------------


def _make_mqtt_payload(
    vehicle_id: int = 1,
    latitude: float = VALID_LAT,
    longitude: float = VALID_LON,
    speed: float = VALID_SPEED,
    timestamp: str = VALID_TS,
) -> bytes:
    data = {
        "vehicle_id": vehicle_id,
        "latitude": latitude,
        "longitude": longitude,
        "speed": speed,
        "timestamp": timestamp,
    }
    return json.dumps(data).encode("utf-8")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_extract_vehicle_id_from_topic():
    assert extract_vehicle_id_from_topic("vehicles/1/gps") == 1
    assert extract_vehicle_id_from_topic("vehicles/42/gps") == 42
    assert extract_vehicle_id_from_topic("vehicles/invalid/gps") is None
    assert extract_vehicle_id_from_topic("other/topic") is None


def test_valid_mqtt_payload_accepted(db_session_factory):
    """1 & 8: Valid MQTT payload is accepted and creates a GPSData record."""
    payload = _make_mqtt_payload(vehicle_id=1, speed=55.0)
    record = handle_mqtt_message(
        topic="vehicles/1/gps",
        payload_bytes=payload,
        db_factory=db_session_factory,
    )
    assert record is not None
    assert record.vehicle_id == 1
    assert record.latitude == VALID_LAT
    assert record.longitude == VALID_LON
    assert record.speed == 55.0


def test_invalid_latitude_rejected(db_session_factory):
    """2: Latitude below -90 or above 90 is rejected."""
    payload_low = _make_mqtt_payload(vehicle_id=1, latitude=-95.0)
    record_low = handle_mqtt_message("vehicles/1/gps", payload_low, db_session_factory)
    assert record_low is None

    payload_high = _make_mqtt_payload(vehicle_id=1, latitude=95.0)
    record_high = handle_mqtt_message("vehicles/1/gps", payload_high, db_session_factory)
    assert record_high is None


def test_invalid_longitude_rejected(db_session_factory):
    """3: Longitude below -180 or above 180 is rejected."""
    payload_low = _make_mqtt_payload(vehicle_id=1, longitude=-185.0)
    assert handle_mqtt_message("vehicles/1/gps", payload_low, db_session_factory) is None

    payload_high = _make_mqtt_payload(vehicle_id=1, longitude=185.0)
    assert handle_mqtt_message("vehicles/1/gps", payload_high, db_session_factory) is None


def test_negative_speed_rejected(db_session_factory):
    """4: Negative speed is rejected."""
    payload = _make_mqtt_payload(vehicle_id=1, speed=-10.0)
    assert handle_mqtt_message("vehicles/1/gps", payload, db_session_factory) is None


def test_invalid_vehicle_id_rejected(db_session_factory):
    """5: Vehicle ID <= 0 is rejected."""
    payload_zero = _make_mqtt_payload(vehicle_id=0)
    assert handle_mqtt_message("vehicles/0/gps", payload_zero, db_session_factory) is None

    payload_neg = _make_mqtt_payload(vehicle_id=-5)
    assert handle_mqtt_message("vehicles/-5/gps", payload_neg, db_session_factory) is None


def test_invalid_timestamp_rejected(db_session_factory):
    """6: Naive timestamp or malformed timestamp string is rejected."""
    payload_naive = _make_mqtt_payload(vehicle_id=1, timestamp="2026-09-06T10:30:00")
    assert handle_mqtt_message("vehicles/1/gps", payload_naive, db_session_factory) is None

    payload_garbage = _make_mqtt_payload(vehicle_id=1, timestamp="not-a-date")
    assert handle_mqtt_message("vehicles/1/gps", payload_garbage, db_session_factory) is None


def test_nonexistent_vehicle_handled(db_session_factory):
    """7: Nonexistent vehicle returns None cleanly without crashing."""
    payload = _make_mqtt_payload(vehicle_id=99999)
    assert handle_mqtt_message("vehicles/99999/gps", payload, db_session_factory) is None


def test_topic_vehicle_id_matches_payload(db_session_factory):
    """9: Matching topic vehicle ID and payload vehicle ID is accepted."""
    payload = _make_mqtt_payload(vehicle_id=1)
    record = handle_mqtt_message("vehicles/1/gps", payload, db_session_factory)
    assert record is not None
    assert record.vehicle_id == 1


def test_topic_payload_vehicle_id_mismatch_rejected(db_session_factory):
    """10: Mismatch between topic vehicle ID (1) and payload vehicle ID (2) is rejected."""
    payload = _make_mqtt_payload(vehicle_id=2)
    record = handle_mqtt_message("vehicles/1/gps", payload, db_session_factory)
    assert record is None


def test_malformed_json_handled_safely(db_session_factory):
    """11: Malformed JSON payload is handled safely without raising an exception."""
    malformed_bytes = b'{"vehicle_id": 1, "latitude": 11.0, "longitude":'
    assert handle_mqtt_message("vehicles/1/gps", malformed_bytes, db_session_factory) is None


def test_missing_fields_handled_safely(db_session_factory):
    """12: Missing required payload fields are handled safely."""
    incomplete_json = json.dumps({"vehicle_id": 1, "latitude": 11.0}).encode("utf-8")
    assert handle_mqtt_message("vehicles/1/gps", incomplete_json, db_session_factory) is None


def test_mqtt_handler_does_not_crash_on_bad_input(db_session_factory):
    """13: Test various corrupted or unexpected inputs."""
    assert handle_mqtt_message("vehicles/1/gps", b"\xff\xfe\xfd", db_session_factory) is None
    assert handle_mqtt_message("vehicles/1/gps", json.dumps([1, 2, 3]), db_session_factory) is None
    assert handle_mqtt_message("vehicles/1/gps", "", db_session_factory) is None


def test_existing_gps_service_called_correctly(db_session_factory):
    """14: Verify existing ingest_gps_record service is invoked by MQTT handler."""
    with patch("app.mqtt.handlers.ingest_gps_record") as mock_ingest:
        mock_record = GPSData(id=100, vehicle_id=1, latitude=VALID_LAT, longitude=VALID_LON, speed=10.0)
        mock_ingest.return_value = mock_record

        payload = _make_mqtt_payload(vehicle_id=1)
        res = handle_mqtt_message("vehicles/1/gps", payload, db_session_factory)
        assert res == mock_record
        assert mock_ingest.called


def test_mqtt_startup_shutdown_does_not_break_fastapi():
    """15: MQTT subscriber startup/shutdown handles unreachable broker gracefully."""
    # Attempting to connect to non-existent broker port 18833 should log warning and return None
    with patch("app.mqtt.client.settings.MQTT_BROKER_PORT", 18833):
        client_inst = start_mqtt_subscriber()
        assert client_inst is None
        # stop should execute safely even when client is None
        stop_mqtt_subscriber()


def test_create_mqtt_client_callbacks():
    """Verify MQTT client configuration and callbacks."""
    mqtt_client = create_mqtt_client()
    assert mqtt_client is not None
    assert callable(mqtt_client.on_connect)
    assert callable(mqtt_client.on_message)
    assert callable(mqtt_client.on_disconnect)


def test_existing_rest_gps_endpoint_continues_working(client):
    """16: REST POST /gps endpoint continues working alongside MQTT."""
    login_res = client.post("/auth/login", json={"username": "userA", "password": "password123"})
    token = login_res.json()["access_token"]

    gps_res = client.post(
        "/gps",
        json={
            "vehicle_id": 1,
            "latitude": 11.0168,
            "longitude": 76.9558,
            "timestamp": "2026-09-06T10:30:00Z",
            "speed": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gps_res.status_code == 201
    assert gps_res.json()["vehicle_id"] == 1



def test_existing_authentication_tests_continue_passing(client):
    """17: Verify JWT authentication pipeline works properly."""
    res = client.post("/auth/login", json={"username": "userA", "password": "password123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data


def test_existing_assignment_authorization_tests_continue_passing(client):
    """18: Verify user assignment authorization rules (userA forbidden on BUS-002)."""
    login_res = client.post("/auth/login", json={"username": "userA", "password": "password123"})
    token = login_res.json()["access_token"]

    gps_res = client.post(
        "/gps",
        json={
            "vehicle_id": 2,
            "latitude": 11.0168,
            "longitude": 76.9558,
            "timestamp": "2026-09-06T10:30:00Z",
            "speed": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gps_res.status_code == 403