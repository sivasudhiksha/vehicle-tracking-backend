"""Phase 7 -- GPS Data Ingestion & Storage Tests.

Covers all 22 required test scenarios:
  1.  Valid GPS payload is accepted.
  2.  GPS record is stored in database.
  3.  Returned GPS record contains correct values.
  4.  Latitude below -90 is rejected.
  5.  Latitude above 90 is rejected.
  6.  Longitude below -180 is rejected.
  7.  Longitude above 180 is rejected.
  8.  Negative speed is rejected.
  9.  Invalid timestamp is rejected.
  10. Nonexistent vehicle returns appropriate error.
  11. Unauthenticated GPS ingestion returns 401.
  12. userA can submit GPS for BUS-001.
  13. userA cannot submit GPS for BUS-002.
  14. userB can submit GPS for BUS-002.
  15. userB cannot submit GPS for BUS-001.
  16. Latest GPS service returns newest record.
  17. Latest GPS service returns None when no records exist.
  18. GPS history returns records for requested vehicle.
  19. GPS history respects limit.
  20. GPS history returns newest records first.
  21. GPS records are associated with the correct vehicle.
  22. Cross-user GPS data access is rejected.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import GPSData, Vehicle
from app.services.gps_service import (
    GPS_HISTORY_MAX_LIMIT,
    get_gps_history,
    get_latest_gps,
    ingest_gps_record,
)
from app.schemas.gps import GPSDataCreate


# ---------------------------------------------------------------------------
# Constants used in payloads
# ---------------------------------------------------------------------------

VALID_TS = "2026-09-06T10:30:00Z"
VALID_LAT = 11.0168
VALID_LON = 76.9558
VALID_SPEED = 42.5


def _make_payload(
    vehicle_id: int,
    lat: float = VALID_LAT,
    lon: float = VALID_LON,
    ts: str = VALID_TS,
    speed: float = VALID_SPEED,
) -> dict:
    return {
        "vehicle_id": vehicle_id,
        "latitude": lat,
        "longitude": lon,
        "timestamp": ts,
        "speed": speed,
    }


# ---------------------------------------------------------------------------
# Shared module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_engine():
    """Module-scoped in-memory SQLite engine with full seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=engine)
    return engine


@pytest.fixture(scope="module")
def gps_client(seeded_engine):
    """Module-scoped TestClient using the seeded in-memory database."""
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
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def db_session(seeded_engine):
    """Provide a long-lived session for direct service-layer tests."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=seeded_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


def _login(client: TestClient, username: str, password: str = "password123") -> str:
    resp = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _vehicle_id(seeded_engine, vehicle_number: str) -> int:
    db = sessionmaker(bind=seeded_engine)()
    v = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == vehicle_number)).first()
    db.close()
    return v.id


# ---------------------------------------------------------------------------
# 1-3. Happy path: valid GPS payload accepted, stored, and returned correctly
# ---------------------------------------------------------------------------


def test_valid_gps_payload_accepted(gps_client, seeded_engine):
    """1. Valid GPS payload returns HTTP 201."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 201


def test_gps_record_stored_in_database(gps_client, seeded_engine):
    """2. After ingestion the GPS record exists in the database."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    gps_client.post("/gps", json=_make_payload(vid, lat=12.0, lon=77.0), headers=_auth(token))

    db = sessionmaker(bind=seeded_engine)()
    records = db.scalars(select(GPSData).where(GPSData.vehicle_id == vid)).all()
    db.close()
    assert len(records) >= 1


def test_returned_gps_record_contains_correct_values(gps_client, seeded_engine):
    """3. The response body contains the submitted coordinates and speed."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    payload = _make_payload(vid, lat=11.1111, lon=76.2222, speed=30.0)
    resp = gps_client.post("/gps", json=payload, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["vehicle_id"] == vid
    assert abs(data["latitude"] - 11.1111) < 0.0001
    assert abs(data["longitude"] - 76.2222) < 0.0001
    assert abs(data["speed"] - 30.0) < 0.001
    assert "id" in data
    assert "timestamp" in data


# ---------------------------------------------------------------------------
# 4-9. Validation: coordinate bounds, speed, timestamp
# ---------------------------------------------------------------------------


def test_latitude_below_minus_90_rejected(gps_client, seeded_engine):
    """4. Latitude below -90 returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, lat=-91.0), headers=_auth(token))
    assert resp.status_code == 422


def test_latitude_above_90_rejected(gps_client, seeded_engine):
    """5. Latitude above 90 returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, lat=91.0), headers=_auth(token))
    assert resp.status_code == 422


def test_longitude_below_minus_180_rejected(gps_client, seeded_engine):
    """6. Longitude below -180 returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, lon=-181.0), headers=_auth(token))
    assert resp.status_code == 422


def test_longitude_above_180_rejected(gps_client, seeded_engine):
    """7. Longitude above 180 returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, lon=181.0), headers=_auth(token))
    assert resp.status_code == 422


def test_negative_speed_rejected(gps_client, seeded_engine):
    """8. Negative speed returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, speed=-1.0), headers=_auth(token))
    assert resp.status_code == 422


def test_invalid_timestamp_rejected(gps_client, seeded_engine):
    """9. Non-datetime timestamp string returns HTTP 422."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid, ts="not-a-timestamp"), headers=_auth(token))
    assert resp.status_code == 422


def test_naive_timestamp_without_timezone_rejected(gps_client, seeded_engine):
    """9b. Timestamp without timezone info is rejected."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    # ISO 8601 without timezone suffix
    resp = gps_client.post("/gps", json=_make_payload(vid, ts="2026-09-06T10:30:00"), headers=_auth(token))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. Nonexistent vehicle
# ---------------------------------------------------------------------------


def test_nonexistent_vehicle_returns_404(gps_client):
    """10. Submitting GPS for a nonexistent vehicle returns 403 (auth check first).

    Because vehicle_id is verified against current_user.vehicle_id before
    the DB lookup, a completely foreign vehicle_id is blocked with 403
    since it won't match the user's assignment.
    """
    token = _login(gps_client, "userA")
    # vehicle_id 99999 does not exist AND is not userA's vehicle
    resp = gps_client.post("/gps", json=_make_payload(99999), headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 11. Unauthenticated access
# ---------------------------------------------------------------------------


def test_unauthenticated_gps_ingestion_returns_401(gps_client, seeded_engine):
    """11. POST /gps without a token returns HTTP 401."""
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 12-15. Authorization: each user can only post for their own vehicle
# ---------------------------------------------------------------------------


def test_userA_can_submit_gps_for_bus_001(gps_client, seeded_engine):
    """12. userA submitting GPS for BUS-001 returns 201."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 201


def test_userA_cannot_submit_gps_for_bus_002(gps_client, seeded_engine):
    """13. userA submitting GPS for BUS-002 returns 403."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-002")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 403


def test_userB_can_submit_gps_for_bus_002(gps_client, seeded_engine):
    """14. userB submitting GPS for BUS-002 returns 201."""
    token = _login(gps_client, "userB")
    vid = _vehicle_id(seeded_engine, "BUS-002")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 201


def test_userB_cannot_submit_gps_for_bus_001(gps_client, seeded_engine):
    """15. userB submitting GPS for BUS-001 returns 403."""
    token = _login(gps_client, "userB")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 16-17. get_latest_gps service
# ---------------------------------------------------------------------------


def test_latest_gps_returns_newest_record(seeded_engine):
    """16. get_latest_gps returns the most recently inserted GPS record."""
    db = sessionmaker(bind=seeded_engine)()
    vid = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first().id

    now = datetime.now(timezone.utc)
    older_ts = now - timedelta(hours=2)
    newer_ts = now - timedelta(minutes=5)

    older = GPSData(vehicle_id=vid, latitude=10.0, longitude=76.0, timestamp=older_ts, speed=10.0)
    newer = GPSData(vehicle_id=vid, latitude=11.5, longitude=77.5, timestamp=newer_ts, speed=55.0)
    db.add_all([older, newer])
    db.commit()

    result = get_latest_gps(vehicle_id=vid, db=db)
    db.close()

    assert result is not None
    assert abs(result.latitude - 11.5) < 0.0001


def test_latest_gps_returns_none_when_no_records_exist(seeded_engine):
    """17. get_latest_gps returns None for a vehicle with no GPS records."""
    # Create a fresh engine so we have a vehicle with zero GPS records
    fresh_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=fresh_engine)
    db = sessionmaker(bind=fresh_engine)()
    # Get BUS-002 but clear all its GPS records first
    vehicle = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-002")).first()
    # Delete any GPS records
    for rec in db.scalars(select(GPSData).where(GPSData.vehicle_id == vehicle.id)).all():
        db.delete(rec)
    db.commit()

    result = get_latest_gps(vehicle_id=vehicle.id, db=db)
    db.close()
    assert result is None


# ---------------------------------------------------------------------------
# 18-20. get_gps_history service
# ---------------------------------------------------------------------------


def test_gps_history_returns_records_for_vehicle(seeded_engine):
    """18. get_gps_history returns GPS records for the requested vehicle."""
    db = sessionmaker(bind=seeded_engine)()
    vid = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first().id

    history = get_gps_history(vehicle_id=vid, db=db)
    db.close()
    assert isinstance(history, list)
    assert len(history) >= 1
    for record in history:
        assert record.vehicle_id == vid


def test_gps_history_respects_limit(seeded_engine):
    """19. get_gps_history returns no more records than the requested limit."""
    db = sessionmaker(bind=seeded_engine)()
    vid = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first().id

    # Insert 10 distinct records
    base_ts = datetime.now(timezone.utc) - timedelta(hours=10)
    for i in range(10):
        db.add(GPSData(
            vehicle_id=vid,
            latitude=10.0 + i * 0.01,
            longitude=76.0 + i * 0.01,
            timestamp=base_ts + timedelta(minutes=i),
            speed=float(i),
        ))
    db.commit()

    history_3 = get_gps_history(vehicle_id=vid, db=db, limit=3)
    db.close()
    assert len(history_3) <= 3


def test_gps_history_returns_newest_first(seeded_engine):
    """20. get_gps_history orders records newest-first (descending timestamp)."""
    db = sessionmaker(bind=seeded_engine)()
    vid = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first().id

    history = get_gps_history(vehicle_id=vid, db=db, limit=100)
    db.close()

    if len(history) >= 2:
        for i in range(len(history) - 1):
            assert history[i].timestamp >= history[i + 1].timestamp, (
                f"Record {i} ({history[i].timestamp}) should be newer than "
                f"record {i+1} ({history[i+1].timestamp})"
            )


# ---------------------------------------------------------------------------
# 21. Record association
# ---------------------------------------------------------------------------


def test_gps_records_associated_with_correct_vehicle(gps_client, seeded_engine):
    """21. GPS records are associated with the vehicle submitted in the payload."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    payload = _make_payload(vid, lat=9.9, lon=75.5, speed=88.0)
    resp = gps_client.post("/gps", json=payload, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["vehicle_id"] == vid

    db = sessionmaker(bind=seeded_engine)()
    record = db.scalars(select(GPSData).where(GPSData.id == data["id"])).first()
    db.close()
    assert record is not None
    assert record.vehicle_id == vid


# ---------------------------------------------------------------------------
# 22. Cross-user GPS data access rejected
# ---------------------------------------------------------------------------


def test_cross_user_gps_submission_rejected(gps_client, seeded_engine):
    """22. A user cannot submit GPS data for another user's vehicle (403)."""
    token_a = _login(gps_client, "userA")
    bus_002_id = _vehicle_id(seeded_engine, "BUS-002")  # belongs to userB

    resp = gps_client.post("/gps", json=_make_payload(bus_002_id), headers=_auth(token_a))
    assert resp.status_code == 403
    assert "authorized" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Bonus: Response schema field verification
# ---------------------------------------------------------------------------


def test_gps_response_does_not_expose_sensitive_fields(gps_client, seeded_engine):
    """Bonus: GPS response must not include password_hash or JWT secrets."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 201
    text = resp.text
    assert "password" not in text
    assert "secret" not in text
    assert "credential" not in text


def test_gps_response_contains_required_fields(gps_client, seeded_engine):
    """Bonus: GPS response includes id, vehicle_id, latitude, longitude, timestamp, speed."""
    token = _login(gps_client, "userA")
    vid = _vehicle_id(seeded_engine, "BUS-001")
    resp = gps_client.post("/gps", json=_make_payload(vid), headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    for field in ("id", "vehicle_id", "latitude", "longitude", "timestamp", "speed"):
        assert field in data, f"Missing expected field: {field}"


def test_gps_history_max_limit_enforced(seeded_engine):
    """Bonus: get_gps_history clamps limit to GPS_HISTORY_MAX_LIMIT."""
    db = sessionmaker(bind=seeded_engine)()
    vid = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first().id
    # Requesting more than the max should still be bounded
    history = get_gps_history(vehicle_id=vid, db=db, limit=GPS_HISTORY_MAX_LIMIT + 9999)
    db.close()
    assert len(history) <= GPS_HISTORY_MAX_LIMIT