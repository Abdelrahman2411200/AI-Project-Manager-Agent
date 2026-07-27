from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_api_responses_include_browser_hardening_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_oversized_request_is_rejected_before_schema_or_auth_processing() -> None:
    settings = get_settings()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/session",
            content=b"x" * (settings.request_max_body_bytes + 1),
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": "oversized-request",
            },
        )
    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
    assert response.json()["request_id"] == "oversized-request"


def test_ai_start_rate_limit_is_keyed_by_route_address_and_session() -> None:
    settings = get_settings()
    path = "/api/v1/projects/00000000-0000-0000-0000-000000000001/planning-runs"
    headers = {"Idempotency-Key": "rate-limit-test"}
    with TestClient(app) as client:
        for _ in range(settings.ai_rate_limit_requests):
            response = client.post(path, json={"token_budget": 1_000}, headers=headers)
            assert response.status_code == 401
        limited = client.post(path, json={"token_budget": 1_000}, headers=headers)
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limit_exceeded"
    assert int(limited.headers["Retry-After"]) >= 1
