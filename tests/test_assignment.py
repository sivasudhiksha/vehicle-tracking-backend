"""Phase 6 -- User Assignment & Backend Authorization Tests.

Covers:
  - GET /me/assignment: returns correct assignment for authenticated user.
  - GET /routes/{route_id}: returns route only when it belongs to the user.
  - GET /vehicles/{vehicle_id}: returns vehicle only when it belongs to the user.
  - Cross-user access is blocked (403).
  - Unauthenticated requests are rejected (401).
  - Unassigned user receives appropriate response.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app
from app.models import Route, User, Vehicle


# ---------------------------------------------------------------------------
# Shared fixture: seeded in-memory SQLite database + authenticated clients
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_engine():
    """Module-scoped in-memory SQLite engine with full seed data."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=test_engine)
    return test_engine


@pytest.fixture(scope="module")
def assignment_client(seeded_engine):
    """Module-scoped TestClient with seeded in-memory database."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=seeded_engine)

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


def _login(client: TestClient, username: str, password: str = "password123") -> str:
    """Helper: authenticate and return the Bearer token string."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. GET /me/assignment -- authenticated user returns own assignment
# ---------------------------------------------------------------------------


def test_me_assignment_userA_returns_200(assignment_client: TestClient):
    """1. userA's /me/assignment returns HTTP 200."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    assert resp.status_code == 200


def test_me_assignment_userB_returns_200(assignment_client: TestClient):
    """2. userB's /me/assignment returns HTTP 200."""
    token = _login(assignment_client, "userB")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    assert resp.status_code == 200


def test_me_assignment_userA_contains_route_a(assignment_client: TestClient):
    """3. userA's assignment includes Route A."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["route"] is not None
    assert data["route"]["name"] == "Route A"


def test_me_assignment_userA_contains_bus_001(assignment_client: TestClient):
    """4. userA's assignment includes BUS-001."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["vehicle"] is not None
    assert data["vehicle"]["vehicle_number"] == "BUS-001"


def test_me_assignment_userB_contains_route_b(assignment_client: TestClient):
    """5. userB's assignment includes Route B."""
    token = _login(assignment_client, "userB")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["route"] is not None
    assert data["route"]["name"] == "Route B"


def test_me_assignment_userB_contains_bus_002(assignment_client: TestClient):
    """6. userB's assignment includes BUS-002."""
    token = _login(assignment_client, "userB")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["vehicle"] is not None
    assert data["vehicle"]["vehicle_number"] == "BUS-002"


def test_me_assignment_contains_user_summary(assignment_client: TestClient):
    """7. /me/assignment response includes user id and username."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert "user" in data
    assert data["user"]["username"] == "userA"
    assert "id" in data["user"]


def test_me_assignment_does_not_expose_password(assignment_client: TestClient):
    """8. /me/assignment does not expose password_hash or password fields."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    text = resp.text
    assert "password" not in text
    assert "password_hash" not in text


def test_me_assignment_unauthenticated_returns_401(assignment_client: TestClient):
    """9. /me/assignment without token returns HTTP 401."""
    resp = assignment_client.get("/me/assignment")
    assert resp.status_code == 401


def test_me_assignment_invalid_token_returns_401(assignment_client: TestClient):
    """10. /me/assignment with invalid token returns HTTP 401."""
    resp = assignment_client.get("/me/assignment", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. GET /routes/{route_id} -- user can only access their own route
# ---------------------------------------------------------------------------


def test_routes_userA_can_access_own_route(assignment_client: TestClient, seeded_engine):
    """11. userA can GET their own assigned route."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    route_a = db.scalars(select(Route).where(Route.name == "Route A")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_a.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "Route A"


def test_routes_userB_can_access_own_route(assignment_client: TestClient, seeded_engine):
    """12. userB can GET their own assigned route."""
    token = _login(assignment_client, "userB")
    db = sessionmaker(bind=seeded_engine)()
    route_b = db.scalars(select(Route).where(Route.name == "Route B")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_b.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "Route B"


def test_routes_userA_cannot_access_route_b(assignment_client: TestClient, seeded_engine):
    """13. userA gets HTTP 403 trying to access Route B."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    route_b = db.scalars(select(Route).where(Route.name == "Route B")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_b.id}", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_routes_userB_cannot_access_route_a(assignment_client: TestClient, seeded_engine):
    """14. userB gets HTTP 403 trying to access Route A."""
    token = _login(assignment_client, "userB")
    db = sessionmaker(bind=seeded_engine)()
    route_a = db.scalars(select(Route).where(Route.name == "Route A")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_a.id}", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_routes_unauthenticated_returns_401(assignment_client: TestClient, seeded_engine):
    """15. /routes/{id} without token returns HTTP 401."""
    db = sessionmaker(bind=seeded_engine)()
    route_a = db.scalars(select(Route).where(Route.name == "Route A")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_a.id}")
    assert resp.status_code == 401


def test_routes_response_contains_route_coordinates(assignment_client: TestClient, seeded_engine):
    """16. Route response includes route_coordinates as parsed list."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    route_a = db.scalars(select(Route).where(Route.name == "Route A")).first()
    db.close()
    resp = assignment_client.get(f"/routes/{route_a.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "route_coordinates" in data
    assert isinstance(data["route_coordinates"], list)


# ---------------------------------------------------------------------------
# 3. GET /vehicles/{vehicle_id} -- user can only access their own vehicle
# ---------------------------------------------------------------------------


def test_vehicles_userA_can_access_own_vehicle(assignment_client: TestClient, seeded_engine):
    """17. userA can GET their own assigned vehicle (BUS-001)."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    bus_001 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_001.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["vehicle_number"] == "BUS-001"


def test_vehicles_userB_can_access_own_vehicle(assignment_client: TestClient, seeded_engine):
    """18. userB can GET their own assigned vehicle (BUS-002)."""
    token = _login(assignment_client, "userB")
    db = sessionmaker(bind=seeded_engine)()
    bus_002 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-002")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_002.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["vehicle_number"] == "BUS-002"


def test_vehicles_userA_cannot_access_bus_002(assignment_client: TestClient, seeded_engine):
    """19. userA gets HTTP 403 trying to access BUS-002."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    bus_002 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-002")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_002.id}", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_vehicles_userB_cannot_access_bus_001(assignment_client: TestClient, seeded_engine):
    """20. userB gets HTTP 403 trying to access BUS-001."""
    token = _login(assignment_client, "userB")
    db = sessionmaker(bind=seeded_engine)()
    bus_001 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_001.id}", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_vehicles_unauthenticated_returns_401(assignment_client: TestClient, seeded_engine):
    """21. /vehicles/{id} without token returns HTTP 401."""
    db = sessionmaker(bind=seeded_engine)()
    bus_001 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_001.id}")
    assert resp.status_code == 401


def test_vehicles_response_contains_status(assignment_client: TestClient, seeded_engine):
    """22. Vehicle response includes status field with value active."""
    token = _login(assignment_client, "userA")
    db = sessionmaker(bind=seeded_engine)()
    bus_001 = db.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()
    db.close()
    resp = assignment_client.get(f"/vehicles/{bus_001.id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] == "active"


# ---------------------------------------------------------------------------
# 4. Consistency checks
# ---------------------------------------------------------------------------


def test_assignment_consistency_userA(assignment_client: TestClient):
    """23. userA: assignment route_id matches vehicle route_id."""
    token = _login(assignment_client, "userA")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["route"]["id"] == data["vehicle"]["route_id"]


def test_assignment_consistency_userB(assignment_client: TestClient):
    """24. userB: assignment route_id matches vehicle route_id."""
    token = _login(assignment_client, "userB")
    resp = assignment_client.get("/me/assignment", headers=_auth_headers(token))
    data = resp.json()
    assert data["route"]["id"] == data["vehicle"]["route_id"]


def test_unassigned_user_me_assignment_returns_empty(seeded_engine):
    """25. A user with no route/vehicle returns 200 with null route and vehicle."""
    from app.core.security import get_password_hash
    from app.db.init_db import init_db
    from app.models import User

    init_db(target_engine=seeded_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=seeded_engine)

    with TestingSessionLocal() as db:
        existing = db.scalars(select(User).where(User.username == "unassigned_user")).first()
        if not existing:
            unassigned = User(
                username="unassigned_user",
                email="unassigned@example.com",
                password_hash=get_password_hash("testpass123"),
                route_id=None,
                vehicle_id=None,
            )
            db.add(unassigned)
            db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        login_resp = client.post("/auth/login", json={"username": "unassigned_user", "password": "testpass123"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        resp = client.get("/me/assignment", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] is None
        assert data["vehicle"] is None
        assert data["user"]["username"] == "unassigned_user"

    app.dependency_overrides.clear()
