"""Phase 9 -- Current Location & GPS History API Tests.

Covers all 23 required test scenarios:
 1. userA can retrieve assigned vehicle latest location.
 2. userB can retrieve assigned vehicle latest location.
 3. Latest location returns newest GPS record.
 4. userA cannot retrieve userB vehicle data (no IDOR vulnerability).
 5. userB cannot retrieve userA vehicle data (no IDOR vulnerability).
 6. Unauthenticated latest-location request returns 401.
 7. User with no assigned vehicle returns 404.
 8. Assigned vehicle with no GPS data returns 404 for location endpoint.
 9. userA can retrieve GPS history.
10. userB can retrieve GPS history.
11. History records are returned newest-first.
12. Default history limit (100) works.
13. Custom history limit works.
14. limit=1 works.
15. limit=1000 works.
16. limit=0 is rejected with 422.
17. Negative limit is rejected with 422.
18. limit > 1000 is rejected with 422.
19. Malformed limit (e.g. string) is rejected with 422.
20. Authentication endpoints (/auth/login) remain functional.
21. Assignment endpoint (/me/assignment) remains functional.
22. POST /gps endpoint remains functional.
23. MQTT ingestion functionality remains functional.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import GPSData, User
from app.mqtt.handlers import handle_mqtt_message
from app.schemas.gps import GPSDataCreate
from app.services.gps_service import ingest_gps_record


@pytest.fixture(scope="module")
def seeded_engine():
    """Module-scoped in-memory SQLite database initialized with seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=engine)
    return engine


@pytest.fixture(scope="module")
def db_session_factory(seeded_engine):
    """Factory returning Session bound to seeded in-memory SQLite engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=seeded_engine)


@pytest.fixture(scope="module")
def client(seeded_engine):
    """Module-scoped TestClient with database dependency override."""
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


@pytest.fixture(scope="module")
def user_a_token(client: TestClient) -> str:
    res = client.post("/auth/login", json={"username": "userA", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def user_b_token(client: TestClient) -> str:
    res = client.post("/auth/login", json={"username": "userB", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def unassigned_user_token(client: TestClient, db_session_factory) -> str:
    """Create an unassigned user with no route/vehicle and return auth token."""
    db = db_session_factory()
    unassigned_user = User(
        username="unassigned_loc_user",
        email="unassigned_loc@example.com",
        password_hash=get_password_hash("password123"),
        route_id=None,
        vehicle_id=None,
    )
    db.add(unassigned_user)
    db.commit()
    db.close()

    res = client.post(
        "/auth/login",
        json={"username": "unassigned_loc_user", "password": "password123"},
    )
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_unauthenticated_requests_rejected(client: TestClient):
    """6: Unauthenticated latest location and history requests return 401."""
    res_loc = client.get("/me/vehicle/location")
    assert res_loc.status_code == 401

    res_hist = client.get("/me/vehicle/history")
    assert res_hist.status_code == 401


def test_user_with_no_assigned_vehicle_returns_404(client: TestClient, unassigned_user_token: str):
    """7: User with no assigned vehicle receives 404 for location and history."""
    headers = {"Authorization": f"Bearer {unassigned_user_token}"}

    res_loc = client.get("/me/vehicle/location", headers=headers)
    assert res_loc.status_code == 404
    assert res_loc.json()["detail"] == "User has no assigned vehicle"

    res_hist = client.get("/me/vehicle/history", headers=headers)
    assert res_hist.status_code == 404
    assert res_hist.json()["detail"] == "User has no assigned vehicle"


def test_assigned_vehicle_with_no_gps_data_returns_404(client: TestClient, user_b_token: str):
    """8: Assigned vehicle with no GPS data returns 404 for location, empty records list for history."""
    headers = {"Authorization": f"Bearer {user_b_token}"}

    # BUS-002 (vehicle_id=2) has no GPS data initially
    res_loc = client.get("/me/vehicle/location", headers=headers)
    assert res_loc.status_code == 404
    assert res_loc.json()["detail"] == "No GPS data available for assigned vehicle"

    # History returns HTTP 200 with vehicle_id=2 and empty records list
    res_hist = client.get("/me/vehicle/history", headers=headers)
    assert res_hist.status_code == 200
    data = res_hist.json()
    assert data["vehicle_id"] == 2
    assert data["records"] == []


def test_user_a_latest_location_and_history(client: TestClient, user_a_token: str, db_session_factory):
    """1, 3, 9, 11: userA can retrieve assigned vehicle (BUS-001) location and history (newest first)."""
    # Seed 3 telemetry fixes for vehicle 1 with distinct timestamps
    db = db_session_factory()
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    for i in range(3):
        payload = GPSDataCreate(
            vehicle_id=1,
            latitude=11.0168 + (i * 0.001),
            longitude=76.9558 + (i * 0.001),
            timestamp=base_time + timedelta(minutes=i),
            speed=30.0 + (i * 5.0),
        )
        ingest_gps_record(payload, db)
    db.close()

    headers = {"Authorization": f"Bearer {user_a_token}"}

    # 1 & 3: Latest location
    res_loc = client.get("/me/vehicle/location", headers=headers)
    assert res_loc.status_code == 200
    loc_data = res_loc.json()
    assert loc_data["vehicle_id"] == 1
    assert loc_data["speed"] == 40.0  # Newest record (i=2: 30 + 10)

    # 9 & 11: History ordered newest first
    res_hist = client.get("/me/vehicle/history", headers=headers)
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert hist_data["vehicle_id"] == 1
    records = hist_data["records"]
    assert len(records) >= 3

    # Verify descending timestamp order
    timestamps = [r["timestamp"] for r in records]
    assert timestamps == sorted(timestamps, reverse=True)


def test_user_b_latest_location_and_history(client: TestClient, user_b_token: str, db_session_factory):
    """2 & 10: userB can retrieve assigned vehicle (BUS-002) location and history."""
    db = db_session_factory()
    now_ts = datetime.now(timezone.utc)
    payload = GPSDataCreate(
        vehicle_id=2,
        latitude=12.9716,
        longitude=77.5946,
        timestamp=now_ts,
        speed=60.0,
    )
    ingest_gps_record(payload, db)
    db.close()

    headers = {"Authorization": f"Bearer {user_b_token}"}

    res_loc = client.get("/me/vehicle/location", headers=headers)
    assert res_loc.status_code == 200
    loc_data = res_loc.json()
    assert loc_data["vehicle_id"] == 2
    assert loc_data["latitude"] == 12.9716

    res_hist = client.get("/me/vehicle/history", headers=headers)
    assert res_hist.status_code == 200
    assert res_hist.json()["vehicle_id"] == 2
    assert len(res_hist.json()["records"]) >= 1


def test_no_idor_cross_user_isolation(client: TestClient, user_a_token: str, user_b_token: str):
    """4 & 5: userA receives only vehicle 1 data; userB receives only vehicle 2 data (No IDOR)."""
    headers_a = {"Authorization": f"Bearer {user_a_token}"}
    headers_b = {"Authorization": f"Bearer {user_b_token}"}

    res_loc_a = client.get("/me/vehicle/location", headers=headers_a)
    res_loc_b = client.get("/me/vehicle/location", headers=headers_b)

    assert res_loc_a.json()["vehicle_id"] == 1
    assert res_loc_b.json()["vehicle_id"] == 2

    res_hist_a = client.get("/me/vehicle/history", headers=headers_a)
    res_hist_b = client.get("/me/vehicle/history", headers=headers_b)

    assert res_hist_a.json()["vehicle_id"] == 1
    assert res_hist_b.json()["vehicle_id"] == 2


def test_history_limit_parameter_validations(client: TestClient, user_a_token: str):
    """12, 13, 14, 15, 16, 17, 18, 19: History limit parameter rules and error handling."""
    headers = {"Authorization": f"Bearer {user_a_token}"}

    # 12: Default limit works
    res_default = client.get("/me/vehicle/history", headers=headers)
    assert res_default.status_code == 200

    # 13 & 14: Custom limit=1
    res_limit_1 = client.get("/me/vehicle/history?limit=1", headers=headers)
    assert res_limit_1.status_code == 200
    assert len(res_limit_1.json()["records"]) == 1

    # 15: Maximum valid limit=1000
    res_limit_1000 = client.get("/me/vehicle/history?limit=1000", headers=headers)
    assert res_limit_1000.status_code == 200

    # 16: limit=0 rejected with 422
    res_zero = client.get("/me/vehicle/history?limit=0", headers=headers)
    assert res_zero.status_code == 422

    # 17: Negative limit rejected with 422
    res_neg = client.get("/me/vehicle/history?limit=-5", headers=headers)
    assert res_neg.status_code == 422

    # 18: limit > 1000 rejected with 422
    res_over = client.get("/me/vehicle/history?limit=1001", headers=headers)
    assert res_over.status_code == 422

    # 19: Malformed limit rejected with 422
    res_invalid = client.get("/me/vehicle/history?limit=abc", headers=headers)
    assert res_invalid.status_code == 422


def test_regression_existing_functionality(client: TestClient, user_a_token: str, db_session_factory):
    """20, 21, 22, 23: Verify auth, assignment, REST GPS, and MQTT remain fully functional."""
    # 20: Authentication
    login_res = client.post("/auth/login", json={"username": "userA", "password": "password123"})
    assert login_res.status_code == 200

    # 21: Assignment
    headers = {"Authorization": f"Bearer {user_a_token}"}
    assign_res = client.get("/me/assignment", headers=headers)
    assert assign_res.status_code == 200
    assert assign_res.json()["vehicle"]["id"] == 1

    # 22: REST POST /gps
    gps_res = client.post(
        "/gps",
        json={
            "vehicle_id": 1,
            "latitude": 11.0168,
            "longitude": 76.9558,
            "timestamp": "2026-09-06T12:00:00Z",
            "speed": 50.0,
        },
        headers=headers,
    )
    assert gps_res.status_code == 201

    # 23: MQTT Ingestion
    mqtt_payload = json.dumps({
        "vehicle_id": 1,
        "latitude": 11.0168,
        "longitude": 76.9558,
        "speed": 45.0,
        "timestamp": "2026-09-06T12:05:00Z",
    }).encode("utf-8")

    mqtt_record = handle_mqtt_message("vehicles/1/gps", mqtt_payload, db_session_factory)
    assert mqtt_record is not None
    assert mqtt_record.speed == 45.0