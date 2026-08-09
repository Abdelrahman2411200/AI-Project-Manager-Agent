from app.core.config import get_settings
from tests.api.test_projects import create_user_and_client


def test_capabilities_report_provider_readiness_without_exposing_credentials() -> None:
    _, client, _ = create_user_and_client("capabilities-owner@example.com")

    with client:
        response = client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "planning_ai_configured": True,
        "planning_provider": "openai",
        "planning_model": get_settings().openai_model,
        "planning_run_default_token_budget": 50_000,
    }
    assert "test-provider-key" not in response.text


def test_capabilities_report_unconfigured_provider(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "none")
    _, client, _ = create_user_and_client("capabilities-no-provider@example.com")

    with client:
        response = client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    assert response.json()["planning_ai_configured"] is False
    assert response.json()["planning_provider"] == "none"
    assert response.json()["planning_model"] is None
