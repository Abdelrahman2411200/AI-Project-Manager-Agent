from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.db.models.project import Project

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'system', 'agent', 'worker')", name="actor_type_allowed"
        ),
        Index("ix_audit_events_owner_occurred", "owner_id", "occurred_at"),
        Index("ix_audit_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    before_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    after_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    project: Mapped["Project | None"] = relationship(back_populates="audit_events")


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _prevent_audit_mutation(*_: object) -> None:
    raise ValueError("Audit events are append-only.")
