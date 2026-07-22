from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.security import hash_password
from app.db.models.audit import AuditEvent
from app.db.models.identity import User
from app.db.models.project import Project
from app.db.session import SessionLocal
from app.main import app

ORIGIN = "http://testserver"


def create_user_and_client(email: str) -> tuple[User, TestClient, str]:
    with SessionLocal() as db:
        user = User(email=email, password_hash=hash_password("correct-horse-battery"))
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    client = TestClient(app, base_url="http://testserver")
    login = client.post(
        "/api/v1/auth/session",
        json={"email": email, "password": "correct-horse-battery"},
        headers={"Origin": ORIGIN},
    )
    assert login.status_code == 200
    return user, client, str(login.json()["csrf_token"])


def project_payload(name: str = "University planner") -> dict[str, Any]:
    return {
        "name": name,
        "goal": "Deliver a validated planning assistant.",
        "desired_outcome": "A reliable university demonstration.",
        "start_date": "2026-07-23",
        "deadline": "2026-12-01",
        "timezone": "Africa/Cairo",
        "capacity_hours_per_week": 30,
        "team_size": 2,
        "requirements": [
            {"kind": "stated", "text": "Owner-scoped project data", "status": "confirmed"}
        ],
        "constraints": [
            {
                "constraint_type": "technology",
                "value_json": {"backend": "FastAPI"},
                "confirmed": True,
            }
        ],
        "work_calendar": {
            "weekday_hours": {"sunday": 6, "monday": 6, "tuesday": 6},
            "parallel_limit": 2,
        },
    }


def write_headers(csrf: str, version: int | None = None) -> dict[str, str]:
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    if version is not None:
        headers["If-Match"] = str(version)
    return headers


def test_project_intake_persists_children_and_audit() -> None:
    user, client, csrf = create_user_and_client("owner@example.com")
    with client:
        response = client.post(
            "/api/v1/projects", json=project_payload(), headers=write_headers(csrf)
        )
        assert response.status_code == 201
        project = response.json()
        assert project["row_version"] == 1
        assert project["timezone"] == "Africa/Cairo"
        assert len(project["requirements"]) == 1
        assert len(project["constraints"]) == 1
        assert project["calendars"][0]["parallel_limit"] == 2

        listing = client.get("/api/v1/projects")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()["items"]] == [project["id"]]

    with SessionLocal() as db:
        stored = db.scalar(select(Project).where(Project.owner_id == user.id))
        assert stored is not None
        assert (
            db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.project_id == stored.id))
            == 1
        )


def test_two_owners_cannot_observe_each_others_resources() -> None:
    _, owner_client, owner_csrf = create_user_and_client("owner@example.com")
    _, other_client, _ = create_user_and_client("other@example.com")
    with owner_client, other_client:
        created = owner_client.post(
            "/api/v1/projects", json=project_payload(), headers=write_headers(owner_csrf)
        ).json()

        assert other_client.get(f"/api/v1/projects/{created['id']}").status_code == 404
        assert other_client.get("/api/v1/projects").json()["items"] == []


def test_project_writes_require_csrf_and_optimistic_version() -> None:
    _, client, csrf = create_user_and_client("owner@example.com")
    with client:
        denied = client.post("/api/v1/projects", json=project_payload(), headers={"Origin": ORIGIN})
        assert denied.status_code == 403

        project = client.post(
            "/api/v1/projects", json=project_payload(), headers=write_headers(csrf)
        ).json()
        changed = client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "Updated planner"},
            headers=write_headers(csrf, project["row_version"]),
        )
        assert changed.status_code == 200
        assert changed.json()["row_version"] == 2

        stale = client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "Stale edit"},
            headers=write_headers(csrf, project["row_version"]),
        )
        assert stale.status_code == 409
        assert "current 2" in stale.json()["detail"]


def test_replace_intake_and_archive_append_audit_events() -> None:
    _, client, csrf = create_user_and_client("owner@example.com")
    with client:
        project = client.post(
            "/api/v1/projects", json=project_payload(), headers=write_headers(csrf)
        ).json()
        changed = client.put(
            f"/api/v1/projects/{project['id']}/requirements",
            json=[{"kind": "excluded", "text": "Portfolio management"}],
            headers=write_headers(csrf, project["row_version"]),
        ).json()
        archived = client.delete(
            f"/api/v1/projects/{project['id']}",
            headers=write_headers(csrf, changed["row_version"]),
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"

    with SessionLocal() as db:
        actions = list(
            db.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.project_id == UUID(project["id"]))
                .order_by(AuditEvent.occurred_at)
            )
        )
        assert actions == ["ProjectCreated", "RequirementsChanged", "ProjectArchived"]
