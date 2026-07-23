"""Active-plan execution projections, immutable events, and monitoring snapshots."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")
STATUS_VALUES = "'pending', 'ready', 'in_progress', 'blocked', 'completed', 'cancelled'"


class TaskExecutionProjection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mutable active-plan state kept separate from immutable approved content."""

    __tablename__ = "task_execution_projections"
    __table_args__ = (
        CheckConstraint(f"status IN ({STATUS_VALUES})", name="status_allowed"),
        CheckConstraint(
            "progress_fraction >= 0 AND progress_fraction <= 1",
            name="progress_fraction_range",
        ),
        CheckConstraint("actual_effort_hours >= 0", name="actual_effort_nonnegative"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        UniqueConstraint("task_id", name="task_execution_task"),
        ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="task_execution_same_version",
            ondelete="CASCADE",
        ),
        Index(
            "ix_task_execution_project_version_status",
            "project_id",
            "version_id",
            "status",
        ),
        Index("ix_task_execution_version_changed", "version_id", "status_changed_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    progress_fraction: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal(0), nullable=False
    )
    actual_effort_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal(0), nullable=False
    )
    blocked_reason: Mapped[str | None] = mapped_column(String(1000))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class TaskStatusEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_status_events"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUS_VALUES})",
            name="from_status_allowed",
        ),
        CheckConstraint(f"to_status IN ({STATUS_VALUES})", name="to_status_allowed"),
        CheckConstraint("actor_type IN ('user', 'system')", name="actor_type_allowed"),
        CheckConstraint(
            "progress_fraction >= 0 AND progress_fraction <= 1",
            name="progress_fraction_range",
        ),
        UniqueConstraint("event_key", name="task_status_event_key"),
        ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="task_status_event_same_version",
            ondelete="CASCADE",
        ),
        Index("ix_task_status_events_task_occurred", "task_id", "occurred_at"),
        Index("ix_task_status_events_project_occurred", "project_id", "occurred_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    progress_fraction: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_key: Mapped[str] = mapped_column(String(240), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ProgressUpdate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "progress_updates"
    __table_args__ = (
        CheckConstraint(
            "fraction >= 0 AND fraction <= 1",
            name="fraction_range",
        ),
        CheckConstraint("actual_effort_hours >= 0", name="actual_effort_nonnegative"),
        CheckConstraint("source IN ('user', 'system')", name="source_allowed"),
        UniqueConstraint("event_key", name="progress_update_event_key"),
        ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="progress_update_same_version",
            ondelete="CASCADE",
        ),
        Index("ix_progress_updates_task_occurred", "task_id", "occurred_at"),
        Index("ix_progress_updates_project_occurred", "project_id", "occurred_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    fraction: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    actual_effort_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_key: Mapped[str] = mapped_column(String(240), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class MonitoringSnapshot(UUIDPrimaryKeyMixin, Base):
    """Immutable deterministic output for one exact active-state hash."""

    __tablename__ = "monitoring_snapshots"
    __table_args__ = (
        CheckConstraint(
            "health_label IN ('Completed', 'On track', 'At risk', 'Delayed', 'Insufficient data')",
            name="health_label_allowed",
        ),
        UniqueConstraint("version_id", "state_hash", name="monitoring_version_state_hash"),
        Index("ix_monitoring_project_calculated", "project_id", "calculated_at"),
        Index("ix_monitoring_version_calculated", "version_id", "calculated_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    state_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    schedule_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    health_label: Mapped[str] = mapped_column(String(24), nullable=False)
    health_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    detections_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    calculation_versions: Mapped[dict[str, str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


@event.listens_for(TaskStatusEvent, "before_update")
@event.listens_for(TaskStatusEvent, "before_delete")
@event.listens_for(ProgressUpdate, "before_update")
@event.listens_for(ProgressUpdate, "before_delete")
@event.listens_for(MonitoringSnapshot, "before_update")
@event.listens_for(MonitoringSnapshot, "before_delete")
def _prevent_execution_history_mutation(*_: object) -> None:
    raise ValueError("Execution events and monitoring snapshots are append-only.")
