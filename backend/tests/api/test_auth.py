from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import hash_password
from app.db.models.audit import AuditEvent
from app.db.models.identity import Session, User
from app.db.session import SessionLocal
from app.main import app

ORIGIN = {"Origin": "http://testserver"}


def create_user(email: str = "owner@example.com", password: str = "correct-horse-battery") -> User:
    with SessionLocal() as db:
        user = User(email=email, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_login_uses_opaque_cookie_hashes_and_appends_audit() -> None:
    user = create_user()
    with TestClient(app, base_url="http://testserver") as client:
        response = client.post(
            "/api/v1/auth/session",
            json={"email": user.email, "password": "correct-horse-battery"},
            headers=ORIGIN,
        )

        assert response.status_code == 200
        assert response.json()["user"]["id"] == str(user.id)
        assert response.json()["csrf_token"]
        session_cookie = client.cookies.get("apm_session")
        csrf_cookie = client.cookies.get("apm_csrf")
        assert session_cookie and csrf_cookie

        current = client.get("/api/v1/auth/session")
        assert current.status_code == 200
        assert current.json()["user"]["email"] == user.email

    with SessionLocal() as db:
        session = db.scalar(select(Session))
        assert session is not None
        assert session.token_hash != session_cookie
        assert session.csrf_hash != csrf_cookie
        assert len(session.token_hash) == 64
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "SessionCreated"))


def test_login_failure_is_generic_and_rate_limited() -> None:
    create_user()
    with TestClient(app, base_url="http://testserver") as client:
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/session",
                json={"email": "owner@example.com", "password": "wrong-password"},
                headers=ORIGIN,
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid email or password."

        limited = client.post(
            "/api/v1/auth/session",
            json={"email": "owner@example.com", "password": "wrong-password"},
            headers=ORIGIN,
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1


def test_login_rate_limit_applies_across_emails_from_one_address() -> None:
    with TestClient(app, base_url="http://testserver") as client:
        for attempt in range(5):
            response = client.post(
                "/api/v1/auth/session",
                json={"email": f"unknown-{attempt}@example.com", "password": "wrong-password"},
                headers=ORIGIN,
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/v1/auth/session",
            json={"email": "another@example.com", "password": "wrong-password"},
            headers=ORIGIN,
        )
        assert limited.status_code == 429


def test_logout_requires_csrf_and_revokes_session() -> None:
    create_user()
    with TestClient(app, base_url="http://testserver") as client:
        login = client.post(
            "/api/v1/auth/session",
            json={"email": "owner@example.com", "password": "correct-horse-battery"},
            headers=ORIGIN,
        )
        csrf = login.json()["csrf_token"]

        denied = client.delete("/api/v1/auth/session", headers=ORIGIN)
        assert denied.status_code == 403

        logout = client.delete("/api/v1/auth/session", headers={**ORIGIN, "X-CSRF-Token": csrf})
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401

    with SessionLocal() as db:
        session = db.scalar(select(Session))
        assert session is not None and session.revoked_at is not None
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "SessionRevoked"))
