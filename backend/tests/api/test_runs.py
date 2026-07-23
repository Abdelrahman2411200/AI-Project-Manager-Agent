from uuid import UUID

from sqlalchemy import func, select

from app.db.models.run import AgentJob, AgentRun
from app.db.session import SessionLocal
from tests.api.test_projects import (
    ORIGIN,
    create_user_and_client,
    project_payload,
    write_headers,
)


def test_planning_start_is_csrf_protected_and_idempotent() -> None:
    _, client, csrf = create_user_and_client("run-owner@example.com")
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(csrf),
        ).json()
        path = f"/api/v1/projects/{project['id']}/planning-runs"
        denied = client.post(
            path,
            json={"token_budget": 50000},
            headers={"Origin": ORIGIN, "Idempotency-Key": "phase5-denied"},
        )
        assert denied.status_code == 403

        headers = {
            **write_headers(csrf),
            "Idempotency-Key": "phase5-idempotent-run",
        }
        first = client.post(path, json={"token_budget": 50000}, headers=headers)
        second = client.post(path, json={"token_budget": 50000}, headers=headers)
        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]

        conflict = client.post(path, json={"token_budget": 60000}, headers=headers)
        assert conflict.status_code == 409

    with SessionLocal() as session:
        run_id = UUID(first.json()["id"])
        assert session.scalar(select(func.count(AgentRun.id))) == 1
        assert session.scalar(select(func.count(AgentJob.id)).where(AgentJob.run_id == run_id)) == 1


def test_run_trace_is_owner_scoped_and_queued_run_can_be_cancelled() -> None:
    _, owner_client, owner_csrf = create_user_and_client("trace-owner@example.com")
    _, other_client, _ = create_user_and_client("trace-other@example.com")
    with owner_client, other_client:
        project = owner_client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(owner_csrf),
        ).json()
        started = owner_client.post(
            f"/api/v1/projects/{project['id']}/planning-runs",
            json={"token_budget": 50000},
            headers={
                **write_headers(owner_csrf),
                "Idempotency-Key": "phase5-owner-run",
            },
        ).json()
        run_path = f"/api/v1/agent-runs/{started['id']}"
        assert other_client.get(run_path).status_code == 404
        assert other_client.get(f"{run_path}/steps").status_code == 404

        cancelled = owner_client.post(
            f"{run_path}/cancel",
            headers=write_headers(owner_csrf),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancel_requested"] is True

    with SessionLocal() as session:
        job = session.scalar(select(AgentJob).where(AgentJob.run_id == UUID(started["id"])))
        assert job is not None
        assert job.status == "cancelled"
