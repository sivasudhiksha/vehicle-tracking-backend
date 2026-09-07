from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_200():
    """Verify /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_payload():
    """Verify /health returns the expected JSON response."""
    response = client.get("/health")
    data = response.json()
    assert data == {
        "status": "ok",
        "service": "vehicle-tracking-backend",
        "version": "0.1.0",
    }


def test_docs_endpoint():
    """Verify /docs Swagger UI endpoint is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_cors_preflight_headers():
    """Verify CORS preflight headers are properly returned for client origins."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
