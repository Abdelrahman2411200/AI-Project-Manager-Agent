from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import event, select

from app.db.models.identity import Session
from app.db.session import SessionLocal, engine
from app.services.budgets import BudgetExceededError, _admission_lock_key
from tests.api.test_projects import (
    create_user_and_client,
    project_payload,
    write_headers,
)


def test_quota_rejects_an_expired_session() -> None:
    _, client, _ = create_user_and_client("quota-expired@example.com")
    with SessionLocal() as db:
        session = db.scalar(select(Session))
        assert session is not None
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    with client:
        quota = client.get("/api/v1/usage/quota")

    assert quota.status_code == 401


def test_quota_authentication_and_usage_share_one_database_round_trip() -> None:
    _, client, _ = create_user_and_client("quota-round-trip@example.com")
    select_statements: list[str] = []

    def capture_select(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_select)
    try:
        with client:
            quota = client.get("/api/v1/usage/quota")
    finally:
        event.remove(engine, "before_cursor_execute", capture_select)

    assert quota.status_code == 200
    assert len(select_statements) == 1
    assert "sessions" in select_statements[0]
    assert "agent_runs" in select_statements[0]


def test_quota_aggregate_is_owner_scoped() -> None:
    _, first_client, first_csrf = create_user_and_client("quota-first@example.com")
    _, second_client, _ = create_user_and_client("quota-second@example.com")
    with first_client, second_client:
        project = first_client.post(
            "/api/v1/projects",
            json=project_payload(name="First owner quota project"),
            headers=write_headers(first_csrf),
        ).json()
        started = first_client.post(
            f"/api/v1/projects/{project['id']}/planning-runs",
            json={"token_budget": 50_000},
            headers={
                **write_headers(first_csrf),
                "Idempotency-Key": "quota-owner-isolation",
            },
        )
        assert started.status_code == 201

        second_quota = second_client.get("/api/v1/usage/quota")

    assert second_quota.status_code == 200
    assert second_quota.json()["runs_used"] == 0
    assert second_quota.json()["tokens_reserved_or_used"] == 0


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


def test_admission_lock_key_is_stable_and_scoped_by_owner_and_utc_day() -> None:
    first_owner = UUID("2bbab3f8-2c79-4b88-9894-3742f97bcb50")
    second_owner = UUID("db23942c-2baa-43e6-978a-8a0c1fcbab17")
    first_day = date(2026, 8, 9)

    first_key = _admission_lock_key(first_owner, first_day)

    assert first_key == _admission_lock_key(first_owner, first_day)
    assert first_key != _admission_lock_key(second_owner, first_day)
    assert first_key != _admission_lock_key(first_owner, first_day + timedelta(days=1))
    assert -(2**63) <= first_key < 2**63
