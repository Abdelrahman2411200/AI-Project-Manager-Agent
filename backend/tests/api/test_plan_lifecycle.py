import asyncio
from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai.fake_provider import FakeStructuredModelProvider
from app.core.config import get_settings
from app.db.models.audit import AuditEvent
from app.db.models.plan import PlanApproval, PlanVersion, Task
from app.db.session import SessionLocal
from app.main import app
from app.schemas.run import PlanningRunRequest
from app.services.runs import PlanningRunService
from app.workflows.planning import PlanningWorkflow
from tests.api.test_projects import (
    ORIGIN,
    create_user_and_client,
    project_payload,
    write_headers,
)
from tests.workflows.test_planning import _no_sleep, _outputs


def _fixture(
    email: str = "plan-owner@example.com",
) -> tuple[object, object, str, UUID, UUID]:
    user, client, csrf = create_user_and_client(email)
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(csrf),
        ).json()
    plan_id = _generate_plan(user.id, UUID(project["id"]), "plan-lifecycle-1")
    return user, client, csrf, UUID(project["id"]), plan_id


def _generate_plan(owner_id: UUID, project_id: UUID, key: str) -> UUID:
    with SessionLocal() as session:
        run = PlanningRunService(session, owner_id, f"request-{key}").start(
            project_id,
            key,
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
        return completed.proposed_plan_version_id


def _plan_headers(csrf: str, version: int) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "If-Match": str(version),
    }


def test_plan_graph_and_versions_are_owner_scoped() -> None:
    _, owner_client, _, project_id, plan_id = _fixture()
    _, other_client, _, _, _ = _fixture("other-plan-owner@example.com")
    with owner_client, other_client:
        listing = owner_client.get(f"/api/v1/projects/{project_id}/plan-versions")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [str(plan_id)]

        graph = owner_client.get(f"/api/v1/plan-versions/{plan_id}")
        assert graph.status_code == 200
        assert graph.json()["state"] == "draft"
        assert graph.json()["quality_status"] == "passed"
        assert len(graph.json()["milestones"]) == 1
        assert len(graph.json()["tasks"]) == 2
        assert len(graph.json()["dependencies"]) == 1

        assert other_client.get(f"/api/v1/plan-versions/{plan_id}").status_code == 404
        assert other_client.get(f"/api/v1/projects/{project_id}/plan-versions").status_code == 404


def test_task_lock_protection_user_source_and_optimistic_conflict() -> None:
    _, client, csrf, _, plan_id = _fixture("lock-owner@example.com")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        task = graph["tasks"][0]
        original_hash = graph["content_hash"]

        locked = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"locked": True},
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert locked.status_code == 200
        locked_body = locked.json()
        assert locked_body["item"]["locked"] is True
        assert locked_body["item"]["source"] == "user"
        assert locked_body["item"]["protected"] is True
        assert locked_body["plan"]["quality_status"] == "failed"
        assert locked_body["plan"]["content_hash"] != original_hash

        blocked = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"title": "Change a locked task title"},
            headers=_plan_headers(csrf, locked_body["plan"]["row_version"]),
        )
        assert blocked.status_code == 409
        assert "Unlock" in blocked.json()["detail"]

        stale = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"locked": False},
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert stale.status_code == 409

        unlocked = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"locked": False},
            headers=_plan_headers(csrf, locked_body["plan"]["row_version"]),
        )
        assert unlocked.status_code == 200


def test_review_approval_requires_exact_hash_and_freezes_history() -> None:
    user, client, csrf, project_id, plan_id = _fixture("approval-owner@example.com")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        direct = client.post(
            f"/api/v1/plan-versions/{plan_id}/approve",
            json={"content_hash": graph["content_hash"]},
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert direct.status_code == 409

        reviewed = client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert reviewed.status_code == 200
        review = reviewed.json()
        assert review["state"] == "under_review"
        assert review["quality_status"] == "passed"

        mismatch = client.post(
            f"/api/v1/plan-versions/{plan_id}/approve",
            json={"content_hash": f"sha256:{'0' * 64}"},
            headers=_plan_headers(csrf, review["row_version"]),
        )
        assert mismatch.status_code == 409
        assert "hash" in mismatch.json()["detail"]

        activated = client.post(
            f"/api/v1/plan-versions/{plan_id}/approve",
            json={
                "content_hash": review["content_hash"],
                "reason": "Reviewed against the confirmed project scope.",
            },
            headers=_plan_headers(csrf, review["row_version"]),
        )
        assert activated.status_code == 200
        active = activated.json()
        assert active["state"] == "active"
        assert active["content_hash"] == review["content_hash"]
        assert active["approvals"][-1]["decision"] == "approved"
        assert active["approvals"][-1]["actor_id"] == str(user.id)

        immutable = client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "Attempt to alter active content"},
            headers=_plan_headers(csrf, active["row_version"]),
        )
        assert immutable.status_code == 409

    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count(PlanVersion.id)).where(
                    PlanVersion.project_id == project_id,
                    PlanVersion.state == "active",
                )
            )
            == 1
        )
        approval = session.scalar(select(PlanApproval).where(PlanApproval.version_id == plan_id))
        assert approval is not None
        approval.reason = "Mutation is forbidden"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()


def test_request_changes_returns_review_to_editable_draft() -> None:
    _, client, csrf, _, plan_id = _fixture("changes-owner@example.com")
    with client:
        draft = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        review = client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(csrf, draft["row_version"]),
        ).json()
        returned = client.post(
            f"/api/v1/plan-versions/{plan_id}/request-changes",
            json={"reason": "Acceptance evidence needs more detail."},
            headers=_plan_headers(csrf, review["row_version"]),
        )
        assert returned.status_code == 200
        body = returned.json()
        assert body["state"] == "draft"
        assert body["approvals"][-1]["decision"] == "changes_requested"
        edited = client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={
                "analysis_summary": (
                    "A revised owner-facing planning application with explicit review evidence."
                )
            },
            headers=_plan_headers(csrf, body["row_version"]),
        )
        assert edited.status_code == 200
        assert edited.json()["quality_status"] == "failed"


def test_approval_rechecks_persisted_content_against_reviewed_hash() -> None:
    _, client, csrf, _, plan_id = _fixture("hash-recheck-owner@example.com")
    with client:
        draft = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        review = client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(csrf, draft["row_version"]),
        ).json()
        with SessionLocal() as session:
            task = session.scalar(select(Task).where(Task.version_id == plan_id))
            assert task is not None
            task.title = "Out-of-band concurrent mutation"
            session.commit()

        rejected = client.post(
            f"/api/v1/plan-versions/{plan_id}/approve",
            json={"content_hash": review["content_hash"]},
            headers=_plan_headers(csrf, review["row_version"]),
        )
        assert rejected.status_code == 409
        assert "changed" in rejected.json()["detail"]
        unchanged_state = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        assert unchanged_state["state"] == "under_review"
        assert unchanged_state["approvals"] == []


def test_lifecycle_writes_require_csrf_and_owner_authorization() -> None:
    _, owner_client, owner_csrf, _, plan_id = _fixture("policy-owner@example.com")
    _, other_client, other_csrf, _, _ = _fixture("policy-other@example.com")
    with owner_client, other_client:
        graph = owner_client.get(f"/api/v1/plan-versions/{plan_id}").json()
        unauthenticated = TestClient(app, base_url="http://testserver")
        with unauthenticated:
            assert unauthenticated.get(f"/api/v1/plan-versions/{plan_id}").status_code == 401

        no_csrf = owner_client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "No CSRF write"},
            headers={"Origin": ORIGIN, "If-Match": str(graph["row_version"])},
        )
        assert no_csrf.status_code == 403

        hidden = other_client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "Unauthorized cross-owner write"},
            headers=_plan_headers(other_csrf, graph["row_version"]),
        )
        assert hidden.status_code == 404

        review = owner_client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(owner_csrf, graph["row_version"]),
        ).json()
        frozen_review = owner_client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "Review content cannot be edited"},
            headers=_plan_headers(owner_csrf, review["row_version"]),
        )
        assert frozen_review.status_code == 409


def test_cycle_cross_version_and_failed_quality_block_review() -> None:
    user, client, csrf, project_id, plan_id = _fixture("graph-owner@example.com")
    other_plan_id = _generate_plan(user.id, project_id, "plan-lifecycle-2")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        first, second = graph["tasks"]
        cycle = client.post(
            f"/api/v1/plan-versions/{plan_id}/dependencies",
            json={
                "predecessor_id": second["id"],
                "successor_id": first["id"],
                "reason": "This reverse edge would create a dependency cycle.",
                "evidence_refs": [second["stable_key"], first["stable_key"]],
                "confidence_label": "high",
            },
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert cycle.status_code == 409

        other_graph = client.get(f"/api/v1/plan-versions/{other_plan_id}").json()
        cross_version = client.post(
            f"/api/v1/plan-versions/{plan_id}/dependencies",
            json={
                "predecessor_id": first["id"],
                "successor_id": other_graph["tasks"][0]["id"],
                "reason": "Cross-version dependencies must never be accepted.",
                "evidence_refs": [first["stable_key"], other_graph["tasks"][0]["stable_key"]],
                "confidence_label": "high",
            },
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert cross_version.status_code == 404

        current = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        first_parent = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{first['id']}",
            json={"parent_id": second["id"]},
            headers=_plan_headers(csrf, current["row_version"]),
        )
        assert first_parent.status_code == 200
        parent_cycle = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{second['id']}",
            json={"parent_id": first["id"]},
            headers=_plan_headers(csrf, first_parent.json()["plan"]["row_version"]),
        )
        assert parent_cycle.status_code == 409
        restored = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{first['id']}",
            json={"parent_id": None},
            headers=_plan_headers(csrf, first_parent.json()["plan"]["row_version"]),
        )
        assert restored.status_code == 200
        current = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        for task in deepcopy(current["tasks"]):
            deleted = client.delete(
                f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
                headers=_plan_headers(csrf, current["row_version"]),
            )
            assert deleted.status_code == 200
            current["row_version"] = deleted.json()["row_version"]
        validation = client.post(
            f"/api/v1/plan-versions/{plan_id}/validate",
            headers=_plan_headers(csrf, current["row_version"]),
        )
        assert validation.status_code == 200
        assert validation.json()["passed"] is False
        assert {item["code"] for item in validation.json()["issues"]} >= {"MISSING_TASKS"}
        blocked_review = client.post(
            f"/api/v1/plan-versions/{plan_id}/submit-review",
            headers=_plan_headers(csrf, validation.json()["row_version"]),
        )
        assert blocked_review.status_code == 409


def test_second_activation_supersedes_prior_without_mutating_history() -> None:
    user, client, csrf, project_id, first_id = _fixture("versions-owner@example.com")
    second_id = _generate_plan(user.id, project_id, "plan-lifecycle-2")
    with client:
        first = client.get(f"/api/v1/plan-versions/{first_id}").json()
        first_task_snapshot = deepcopy(first["tasks"])
        first_review = client.post(
            f"/api/v1/plan-versions/{first_id}/submit-review",
            headers=_plan_headers(csrf, first["row_version"]),
        ).json()
        first_active = client.post(
            f"/api/v1/plan-versions/{first_id}/approve",
            json={"content_hash": first_review["content_hash"]},
            headers=_plan_headers(csrf, first_review["row_version"]),
        )
        assert first_active.status_code == 200

        second = client.get(f"/api/v1/plan-versions/{second_id}").json()
        second_review = client.post(
            f"/api/v1/plan-versions/{second_id}/submit-review",
            headers=_plan_headers(csrf, second["row_version"]),
        ).json()
        second_active = client.post(
            f"/api/v1/plan-versions/{second_id}/approve",
            json={"content_hash": second_review["content_hash"]},
            headers=_plan_headers(csrf, second_review["row_version"]),
        )
        assert second_active.status_code == 200
        assert second_active.json()["state"] == "active"

        historical = client.get(f"/api/v1/plan-versions/{first_id}").json()
        assert historical["state"] == "superseded"
        assert historical["tasks"] == first_task_snapshot

    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count(PlanVersion.id)).where(
                    PlanVersion.project_id == project_id,
                    PlanVersion.state == "active",
                )
            )
            == 1
        )
        actions = set(
            session.scalars(select(AuditEvent.action).where(AuditEvent.project_id == project_id))
        )
        assert {"PlanApproved", "PlanActivated", "PlanSuperseded"} <= actions


def test_database_single_active_constraint_rejects_duplicate() -> None:
    _, _, _, project_id, first_id = _fixture("db-active-owner@example.com")
    with SessionLocal() as session:
        first = session.get(PlanVersion, first_id)
        assert first is not None
        first.state = "active"
        session.commit()
        duplicate = PlanVersion(
            project_id=project_id,
            number=2,
            state="active",
            based_on_id=first.id,
            reason="Invalid duplicate active version",
            content_hash=f"sha256:{'1' * 64}",
            quality_status="passed",
            quality_report={"passed": True},
            source_run_id=UUID("00000000-0000-0000-0000-000000000002"),
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()


def test_milestone_task_dependency_crud_diff_and_archive() -> None:
    user, client, csrf, project_id, plan_id = _fixture("crud-owner@example.com")
    comparison_id = _generate_plan(user.id, project_id, "plan-lifecycle-compare")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        milestone_created = client.post(
            f"/api/v1/plan-versions/{plan_id}/milestones",
            json={
                "module_refs": ["MOD-001"],
                "name": "Owner review complete",
                "description": (
                    "A dedicated milestone for reviewing the complete planning evidence."
                ),
                "objective": "Let the owner inspect and accept all validated plan evidence.",
                "deliverable": "Owner-reviewed planning evidence",
                "sequence": 2,
                "planned_effort_hours": 4,
                "acceptance_criteria": ["The owner can trace every task to its requirement"],
            },
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert milestone_created.status_code == 201
        milestone_result = milestone_created.json()
        milestone = milestone_result["item"]
        assert milestone["stable_key"] == "MS-002"
        assert milestone["source"] == "user"
        assert milestone["protected"] is True

        task_created = client.post(
            f"/api/v1/plan-versions/{plan_id}/tasks",
            json={
                "milestone_id": milestone["id"],
                "title": "Trace the plan evidence",
                "description": (
                    "Inspect every task reference and confirm its persisted project evidence."
                ),
                "deliverable": "Reviewed evidence trace",
                "acceptance_criteria": ["Every in-scope requirement has a visible task reference"],
                "definition_of_done": ["The evidence review record is complete"],
                "effort_min_hours": 3,
                "effort_likely_hours": 4,
                "effort_max_hours": 6,
                "complexity": "low",
                "workstreams": ["Quality"],
                "skill_tags": ["Planning"],
                "requirement_refs": ["REQ-001"],
                "assumption_refs": [],
                "priority_factors": {
                    "mvp_necessity": 80,
                    "deadline_urgency": 40,
                    "user_value": 70,
                    "risk_reduction": 60,
                    "user_preference": 50,
                },
            },
            headers=_plan_headers(csrf, milestone_result["plan"]["row_version"]),
        )
        assert task_created.status_code == 201
        task_result = task_created.json()
        task = task_result["item"]
        assert task["stable_key"] == "TASK-003"
        assert task["source"] == "user"

        dependency_created = client.post(
            f"/api/v1/plan-versions/{plan_id}/dependencies",
            json={
                "predecessor_id": graph["tasks"][1]["id"],
                "successor_id": task["id"],
                "reason": "The base planning draft must exist before its evidence is traced.",
                "evidence_refs": [graph["tasks"][1]["stable_key"], task["stable_key"]],
                "confidence_label": "high",
            },
            headers=_plan_headers(csrf, task_result["plan"]["row_version"]),
        )
        assert dependency_created.status_code == 201
        dependency_result = dependency_created.json()
        assert dependency_result["item"]["source"] == "user"

        dependency_deleted = client.delete(
            (f"/api/v1/plan-versions/{plan_id}/dependencies/{dependency_result['item']['id']}"),
            headers=_plan_headers(csrf, dependency_result["plan"]["row_version"]),
        )
        assert dependency_deleted.status_code == 200
        current_version = dependency_deleted.json()["row_version"]

        task_deleted = client.delete(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            headers=_plan_headers(csrf, current_version),
        )
        assert task_deleted.status_code == 200
        milestone_deleted = client.delete(
            f"/api/v1/plan-versions/{plan_id}/milestones/{milestone['id']}",
            headers=_plan_headers(csrf, task_deleted.json()["row_version"]),
        )
        assert milestone_deleted.status_code == 200

        edited = client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "Owner-curated planning draft"},
            headers=_plan_headers(csrf, milestone_deleted.json()["row_version"]),
        )
        assert edited.status_code == 200
        diff = client.get(f"/api/v1/plan-versions/{comparison_id}/compare/{plan_id}")
        assert diff.status_code == 200
        assert any(item["category"] == "content_changed" for item in diff.json()["changes"])

        archived = client.post(
            f"/api/v1/plan-versions/{plan_id}/archive",
            headers=_plan_headers(csrf, edited.json()["row_version"]),
        )
        assert archived.status_code == 200
        assert archived.json()["state"] == "archived"
        blocked = client.patch(
            f"/api/v1/plan-versions/{plan_id}",
            json={"reason": "Archived plans are immutable"},
            headers=_plan_headers(csrf, archived.json()["row_version"]),
        )
        assert blocked.status_code == 409
