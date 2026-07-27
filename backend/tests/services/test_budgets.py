from app.services.budgets import BudgetExceededError
from tests.api.test_projects import (
    create_user_and_client,
    project_payload,
    write_headers,
)


def test_quota_is_visible_and_reserves_active_run_budget() -> None:
    _, client, csrf = create_user_and_client("quota-owner@example.com")
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(name="Quota project"),
            headers=write_headers(csrf),
        ).json()
        started = client.post(
            f"/api/v1/projects/{project['id']}/planning-runs",
            json={"token_budget": 50_000},
            headers={
                **write_headers(csrf),
                "Idempotency-Key": "quota-first-run",
            },
        )
        assert started.status_code == 201
        quota = client.get("/api/v1/usage/quota")
        assert quota.status_code == 200
        assert quota.json()["runs_used"] == 1
        assert quota.json()["tokens_reserved_or_used"] == 50_000
        assert quota.json()["tokens_remaining"] == 150_000


def test_daily_token_budget_rejects_new_reservation_with_retry_guidance() -> None:
    _, client, csrf = create_user_and_client("budget-owner@example.com")
    with client:
        first_project = client.post(
            "/api/v1/projects",
            json=project_payload(name="First budget project"),
            headers=write_headers(csrf),
        ).json()
        second_project = client.post(
            "/api/v1/projects",
            json=project_payload(name="Second budget project"),
            headers=write_headers(csrf),
        ).json()
        first = client.post(
            f"/api/v1/projects/{first_project['id']}/planning-runs",
            json={"token_budget": 50_000},
            headers={
                **write_headers(csrf),
                "Idempotency-Key": "budget-reservation-one",
            },
        )
        assert first.status_code == 201
        rejected = client.post(
            f"/api/v1/projects/{second_project['id']}/planning-runs",
            json={"token_budget": 200_000},
            headers={
                **write_headers(csrf),
                "Idempotency-Key": "budget-reservation-two",
            },
        )
    assert rejected.status_code == 429
    assert rejected.headers["X-Error-Code"] == "daily_token_budget_exceeded"
    assert int(rejected.headers["Retry-After"]) >= 1


def test_budget_error_exposes_only_machine_safe_fields() -> None:
    error = BudgetExceededError("daily_run_limit_exceeded", "limit reached", retry_after=60)
    assert error.code == "daily_run_limit_exceeded"
    assert error.retry_after == 60
    assert str(error) == "limit reached"
