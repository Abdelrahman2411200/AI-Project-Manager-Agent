from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.security import hash_password
from app.db.models.audit import AuditEvent
from app.db.models.identity import Session, User
from app.db.models.project import Project
from app.db.session import SessionLocal


def test_normalized_email_is_unique() -> None:
    with SessionLocal() as db:
        db.add(User(email="same@example.com", password_hash=hash_password("first-password")))
        db.commit()
        db.add(User(email="same@example.com", password_hash=hash_password("second-password")))
        with pytest.raises(IntegrityError):
            db.commit()


def test_project_checks_reject_invalid_capacity() -> None:
    with SessionLocal() as db:
        user = User(email="owner@example.com", password_hash=hash_password("valid-password"))
        db.add(user)
        db.flush()
        db.add(Project(owner_id=user.id, name="Invalid", goal="Invalid", capacity_hours_per_week=0))
        with pytest.raises(IntegrityError):
            db.commit()


def test_session_tokens_are_unique() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = User(email="owner@example.com", password_hash=hash_password("valid-password"))
        db.add(user)
        db.flush()
        for csrf in ("a" * 64, "b" * 64):
            db.add(
                Session(
                    user_id=user.id,
                    token_hash="x" * 64,
                    csrf_hash=csrf,
                    expires_at=now + timedelta(hours=1),
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()


def test_audit_events_are_append_only() -> None:
    with SessionLocal() as db:
        user = User(email="owner@example.com", password_hash=hash_password("valid-password"))
        db.add(user)
        db.flush()
        event = AuditEvent(
            owner_id=user.id,
            actor_id=user.id,
            actor_type="user",
            action="Created",
            entity_type="User",
            entity_id=user.id,
            request_id="test-request",
        )
        db.add(event)
        db.commit()
        event.action = "Changed"
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
