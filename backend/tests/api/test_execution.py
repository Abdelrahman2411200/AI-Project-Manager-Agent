import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.ai.fake_provider import FakeStructuredModelProvider
from app.core.config import get_settings
from app.db.models.audit import AuditEvent
from app.db.models.execution import (
    MonitoringSnapshot,
    ProgressUpdate,
    TaskStatusEvent,
)
from app.db.models.plan import Task
from app.db.models.run import AgentRun
from app.db.session import SessionLocal
from app.schemas.run import PlanningRunRequest
from app.services.monitoring import MonitoringService
from app.services.runs import PlanningRunService
from app.workflows.monitoring import MonitoringWorkflow
from app.workflows.planning import PlanningWorkflow
from tests.api.test_projects import (
    ORIGIN,
    create_user_and_client,
    project_payload,
    write_headers,
)
from tests.workflows.test_planning import _no_sleep, _outputs


def _active_fixture(email: str = "execution-owner@example.com"):
    user, client, csrf = create_user_and_client(email)
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(csrf),
        ).json()
    project_id = UUID(project["id"])
    with SessionLocal() as session:
        run = PlanningRunService(session, user.id, f"execution-{uuid4()}").start(
            project_id,
            f"execution-{uuid4()}",
            PlanningRunRequest(),
        )
        completed = asyncio.run(
            PlanningWorkflow(
                session,
                FakeStructuredModelProvider(_outputs()),
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run.id)
        )
        assert completed.proposed_plan_version_id is not None
        plan_id = completed.proposed_plan_version_id
    with client:
        draft = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        reviewed = client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(csrf, draft["row_version"]),
        ).json()
        active = client.post(
            f"/api/v1/plan-versions/{plan_id}/approve",
            json={"content_hash": reviewed["content_hash"]},
            headers=_plan_headers(csrf, reviewed["row_version"]),
        )
        assert active.status_code == 200
    return user, client, csrf, project_id, plan_id


def _plan_headers(csrf: str, version: int) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "If-Match": str(version),
    }


def _execution_headers(csrf: str, version: int, key: str) -> dict[str, str]:
    return {
        **_plan_headers(csrf, version),
        "Idempotency-Key": key,
    }


def test_active_execution_lifecycle_persists_events_progress_readiness_and_health() -> None:
    user, client, csrf, project_id, plan_id = _active_fixture()
    with client:
        board = client.get(f"/api/v1/projects/{project_id}/execution")
        assert board.status_code == 200
        initial = board.json()
        assert initial["version_id"] == str(plan_id)
        first = next(item for item in initial["tasks"] if item["status"] == "ready")
        successor = next(item for item in initial["tasks"] if item["status"] == "pending")
        assert successor["incomplete_predecessor_refs"] == [first["stable_key"]]
        assert len(initial["recent_events"]) == 2

        started = client.post(
            f"/api/v1/tasks/{first['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(csrf, first["row_version"], "start-root-task"),
        )
        assert started.status_code == 200
        started_body = started.json()
        assert started_body["task"]["status"] == "in_progress"
        assert started_body["event"]["from_status"] == "ready"

        progressed = client.post(
            f"/api/v1/tasks/{first['task_id']}/progress",
            json={
                "fraction": "0.5000",
                "actual_effort_hours": "3.50",
                "note": "Implementation and unit tests are halfway complete.",
            },
            headers=_execution_headers(
                csrf,
                started_body["task"]["row_version"],
                "progress-root-half",
            ),
        )
        assert progressed.status_code == 200
        progress_body = progressed.json()
        assert progress_body["task"]["progress_fraction"] == "0.5000"
        assert progress_body["task"]["actual_effort_hours"] == "3.50"
        assert float(progress_body["progress"]["project"]["fraction"]) > 0

        completed = client.post(
            f"/api/v1/tasks/{first['task_id']}/status",
            json={"to_status": "completed"},
            headers=_execution_headers(
                csrf,
                progress_body["task"]["row_version"],
                "complete-root-task",
            ),
        )
        assert completed.status_code == 200
        complete_body = completed.json()
        assert float(complete_body["task"]["progress_fraction"]) == 1
        assert any(
            item["task_id"] == successor["task_id"]
            and item["from_status"] == "pending"
            and item["to_status"] == "ready"
            for item in complete_body["readiness_changes"]
        )

        reloaded = client.get(f"/api/v1/projects/{project_id}/execution").json()
        successor = next(
            item for item in reloaded["tasks"] if item["task_id"] == successor["task_id"]
        )
        assert successor["status"] == "ready"
        successor_started = client.post(
            f"/api/v1/tasks/{successor['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(
                csrf,
                successor["row_version"],
                "start-successor-task",
            ),
        ).json()
        blocked = client.post(
            f"/api/v1/tasks/{successor['task_id']}/status",
            json={
                "to_status": "blocked",
                "reason": "The external approval contract is unavailable.",
            },
            headers=_execution_headers(
                csrf,
                successor_started["task"]["row_version"],
                "block-successor-task",
            ),
        )
        assert blocked.status_code == 200
        blocked_body = blocked.json()
        assert blocked_body["task"]["blocked_reason"] == (
            "The external approval contract is unavailable."
        )
        assert blocked_body["health"]["label"] == "At risk"
        assert "BLOCKED_CRITICAL_TASK" in blocked_body["health"]["rule_codes"]
        assert successor["stable_key"] in blocked_body["health"]["blocking_path"]
        assert any(
            item["code"] == "BLOCKED_TASKS" and successor["stable_key"] in item["references"]
            for item in blocked_body["health"]["detections"]
        )

        history = client.get(f"/api/v1/tasks/{successor['task_id']}/events")
        assert history.status_code == 200
        assert [item["to_status"] for item in history.json()] == [
            "pending",
            "ready",
            "in_progress",
            "blocked",
        ]
        progress = client.get(f"/api/v1/projects/{project_id}/progress")
        health = client.get(f"/api/v1/projects/{project_id}/health")
        assert progress.status_code == health.status_code == 200
        assert progress.json()["state_hash"] == health.json()["state_hash"]

    with SessionLocal() as session:
        active_content = list(session.scalars(select(Task).where(Task.version_id == plan_id)))
        assert {item.status for item in active_content} == {"pending"}
        assert (
            session.scalar(
                select(func.count(TaskStatusEvent.id)).where(
                    TaskStatusEvent.project_id == project_id
                )
            )
            >= 7
        )
        assert (
            session.scalar(
                select(func.count(ProgressUpdate.id)).where(ProgressUpdate.project_id == project_id)
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(MonitoringSnapshot.id)).where(
                    MonitoringSnapshot.project_id == project_id
                )
            )
            >= 5
        )
        actions = set(
            session.scalars(select(AuditEvent.action).where(AuditEvent.project_id == project_id))
        )
        assert {
            "ExecutionInitialized",
            "TaskStatusChanged",
            "TaskProgressUpdated",
            "TaskReadinessChanged",
        } <= actions
        runs = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.project_id == project_id,
                    AgentRun.workflow == "monitoring",
                )
            )
        )
        assert runs and all(item.status == "completed" for item in runs)
        assert all(item.tokens_used == 0 for item in runs)
        assert user.id == runs[-1].initiator_id


def test_status_transition_is_concurrent_idempotent_owner_scoped_and_validated() -> None:
    _, client, csrf, project_id, _ = _active_fixture("execution-policy@example.com")
    _, other, other_csrf, _, _ = _active_fixture("execution-other@example.com")
    with client, other:
        board = client.get(f"/api/v1/projects/{project_id}/execution").json()
        task = next(item for item in board["tasks"] if item["status"] == "ready")
        no_reason = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "blocked"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "blocked-without-reason",
            ),
        )
        assert no_reason.status_code == 422
        illegal = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "completed"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "illegal-ready-complete",
            ),
        )
        assert illegal.status_code == 409
        hidden = other.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(
                other_csrf,
                task["row_version"],
                "other-owner-hidden",
            ),
        )
        assert hidden.status_code == 404
        no_csrf = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "in_progress"},
            headers={
                "Origin": ORIGIN,
                "If-Match": str(task["row_version"]),
                "Idempotency-Key": "missing-csrf-header",
            },
        )
        assert no_csrf.status_code == 403

        first = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "idempotent-start",
            ),
        )
        assert first.status_code == 200
        duplicate = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "idempotent-start",
            ),
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["event"]["id"] == first.json()["event"]["id"]
        mismatch = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={
                "to_status": "blocked",
                "reason": "A different request reused the same key.",
            },
            headers=_execution_headers(
                csrf,
                first.json()["task"]["row_version"],
                "idempotent-start",
            ),
        )
        assert mismatch.status_code == 409
        stale = client.post(
            f"/api/v1/tasks/{task['task_id']}/progress",
            json={"fraction": "0.25", "actual_effort_hours": "1"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "stale-progress",
            ),
        )
        assert stale.status_code == 409


def test_stale_monitoring_run_cannot_overwrite_newer_execution_state() -> None:
    user, client, csrf, project_id, plan_id = _active_fixture("stale-monitor@example.com")
    with client:
        board = client.get(f"/api/v1/projects/{project_id}/execution").json()
        task = next(item for item in board["tasks"] if item["status"] == "ready")
    with SessionLocal() as session:
        project, plan = MonitoringService(session, user.id).active_plan(project_id)
        stale_hash = MonitoringService(session, user.id).current_state_hash(project, plan)
        stale_run = AgentRun(
            project_id=project_id,
            initiator_id=user.id,
            workflow="monitoring",
            status="queued",
            idempotency_key=f"stale-monitor-{uuid4()}",
            input_hash=stale_hash,
            token_budget=1,
            tokens_used=0,
            current_step="monitor.recalculate",
            state_snapshot={},
            candidate_data={
                "active_plan_version_id": str(plan_id),
                "state_hash": stale_hash,
            },
        )
        session.add(stale_run)
        session.commit()
        stale_run_id = stale_run.id

    with client:
        changed = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "in_progress"},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "change-after-stale-run",
            ),
        )
        assert changed.status_code == 200

    with SessionLocal() as session:
        run = asyncio.run(MonitoringWorkflow(session).execute(stale_run_id))
        assert run.status == "partial"
        assert run.outcome is not None and run.outcome["stale"] is True
        assert run.outcome["expected_state_hash"] == stale_hash
        current = MonitoringService(session, user.id).ensure_current(project_id)
        assert current.state_hash != stale_hash


def test_execution_events_are_append_only() -> None:
    _, client, _, project_id, _ = _active_fixture("append-only-execution@example.com")
    with client:
        board = client.get(f"/api/v1/projects/{project_id}/execution")
        assert board.status_code == 200
    with SessionLocal() as session:
        event = session.scalar(
            select(TaskStatusEvent).where(TaskStatusEvent.project_id == project_id)
        )
        snapshot = session.scalar(
            select(MonitoringSnapshot).where(MonitoringSnapshot.project_id == project_id)
        )
        assert event is not None and snapshot is not None
        event.reason = "Mutation is forbidden."
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
        snapshot = session.get(MonitoringSnapshot, snapshot.id)
        assert snapshot is not None
        snapshot.health_label = "Delayed"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
