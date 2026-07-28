from app.core.config import get_settings
from tests.api.test_projects import create_user_and_client


def test_capabilities_report_provider_readiness_without_exposing_credentials() -> None:
    _, client, _ = create_user_and_client("capabilities-owner@example.com")

    with client:
        response = client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "planning_ai_configured": True,
        "planning_model": get_settings().openai_model,
    }
    assert "test-provider-key" not in response.text


def test_capabilities_report_unconfigured_provider(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    _, client, _ = create_user_and_client("capabilities-no-provider@example.com")

    with client:
        response = client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    assert response.json()["planning_ai_configured"] is False
