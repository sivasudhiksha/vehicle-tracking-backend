from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, decode_access_token
from app.db.seed import seed_database
from app.db.session import get_db
from app.main import app


@pytest.fixture
def auth_client():
    """Provides a TestClient with an isolated seeded database in memory using StaticPool."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    seed_database(target_engine=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

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


def test_login_user_a_succeeds(auth_client: TestClient):
    """1. Verify login with userA succeeds."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_login_user_b_succeeds(auth_client: TestClient):
    """2. Verify login with userB succeeds."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userB", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_login_returns_access_token(auth_client: TestClient):
    """3. Verify login returns non-empty access_token."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    token = data.get("access_token")
    assert isinstance(token, str)
    assert len(token) > 20


def test_token_type_is_bearer(auth_client: TestClient):
    """4. Verify token_type is bearer."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("token_type") == "bearer"


def test_returned_token_can_be_decoded(auth_client: TestClient):
    """5. Verify returned token can be decoded by JWT utility."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert isinstance(payload, dict)


def test_token_contains_user_identity(auth_client: TestClient):
    """6. Verify token contains user identity in sub and username."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert "sub" in payload
    assert payload.get("username") == "userA"


def test_token_expiration_is_present(auth_client: TestClient):
    """7. Verify token expiration timestamp is present and in the future."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]


def test_wrong_password_returns_401(auth_client: TestClient):
    """8. Verify wrong password returns HTTP 401."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_unknown_username_returns_401(auth_client: TestClient):
    """9. Verify unknown username returns HTTP 401."""
    response = auth_client.post(
        "/auth/login",
        json={"username": "nonexistent_user", "password": "password123"},
    )
    assert response.status_code == 401


def test_missing_credentials_rejected(auth_client: TestClient):
    """10. Verify empty or missing credentials are rejected."""
    # Empty string credentials
    r1 = auth_client.post(
        "/auth/login",
        json={"username": "", "password": ""},
    )
    assert r1.status_code in (401, 422)

    # Missing fields
    r2 = auth_client.post(
        "/auth/login",
        json={"username": "userA"},
    )
    assert r2.status_code == 422


def test_malformed_token_returns_401(auth_client: TestClient):
    """11. Verify malformed token returns HTTP 401."""
    headers = {"Authorization": "Bearer this-is-not-a-valid-jwt"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_expired_token_returns_401(auth_client: TestClient):
    """12. Verify expired token returns HTTP 401."""
    expired_token = create_access_token(
        subject="1",
        expires_delta=timedelta(seconds=-10),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 401


def test_token_referencing_nonexistent_user_returns_401(auth_client: TestClient):
    """13. Verify token referencing a nonexistent user returns HTTP 401."""
    ghost_token = create_access_token(subject="99999")
    headers = {"Authorization": f"Bearer {ghost_token}"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(auth_client: TestClient):
    """14. Verify protected endpoint rejects request with missing token."""
    response = auth_client.get("/auth/me")
    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_token(auth_client: TestClient):
    """15. Verify protected endpoint accepts valid token and returns current user details."""
    login_resp = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    token = login_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["username"] == "userA"
    assert user_data["email"] == "userA@example.com"
    assert "password" not in user_data
    assert "password_hash" not in user_data


def test_invalid_token_cannot_access_protected_endpoint(auth_client: TestClient):
    """16. Verify modified/corrupted token cannot access protected endpoint."""
    login_resp = auth_client.post(
        "/auth/login",
        json={"username": "userA", "password": "password123"},
    )
    valid_token = login_resp.json()["access_token"]
    corrupted_token = valid_token[:-4] + "xxxx"

    headers = {"Authorization": f"Bearer {corrupted_token}"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 401
