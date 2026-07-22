import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_root_exposes_service_metadata(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.json()["service"] == "AI Project Manager API"
    assert response.headers["X-Request-ID"] == "test-request-id"


def test_liveness_reports_process_status(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Project Manager API",
        "version": "0.2.0",
        "environment": "test",
        "checks": {"process": "ok"},
    }


def test_readiness_reports_configuration_status(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {"configuration": "ok", "database": "ok"}


def test_unknown_route_uses_problem_detail_envelope(client: TestClient) -> None:
    response = client.get("/missing", headers={"X-Request-ID": "missing-route"})

    assert response.status_code == 404
    assert response.json() == {
        "type": "about:blank",
        "title": "Request failed",
        "status": 404,
        "code": "http_error",
        "detail": "Not Found",
        "errors": [],
        "request_id": "missing-route",
    }
