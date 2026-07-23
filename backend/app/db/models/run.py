"""Durable agent runs, node checkpoints, and database-backed jobs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("workflow IN ('planning', 'monitoring')", name="workflow_allowed"),
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_for_user', 'partial', 'failed', "
            "'completed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("token_budget > 0", name="token_budget_positive"),
        CheckConstraint("tokens_used >= 0", name="tokens_used_nonnegative"),
        UniqueConstraint(
            "initiator_id",
            "idempotency_key",
            name="agent_run_initiator_idempotency",
        ),
        Index("ix_agent_runs_project_status_created", "project_id", "status", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    initiator_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    workflow: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str] = mapped_column(String(80), nullable=False)
    state_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    candidate_data: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proposed_plan_version_id: Mapped[UUID | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRunStep(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled', 'skipped')",
            name="status_allowed",
        ),
        CheckConstraint(
            "mode IN ('deterministic', 'llm', 'human', 'transactional')", name="mode_allowed"
        ),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_nonnegative"),
        UniqueConstraint("run_id", "name", "attempt", name="agent_run_step_attempt"),
        Index("ix_agent_run_steps_input", "run_id", "name", "input_hash", "status"),
        Index("ix_agent_run_steps_run_started", "run_id", "started_at"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    input_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    output_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    validation: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    usage: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class AgentJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_jobs"
    __table_args__ = (
        CheckConstraint("job_type IN ('planning', 'monitoring')", name="job_type_allowed"),
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        UniqueConstraint("idempotency_key", name="agent_job_idempotency"),
        Index("ix_agent_jobs_claim", "status", "available_at", "lease_expires_at"),
        Index("ix_agent_jobs_run_created", "run_id", "created_at"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_ref: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claim_token: Mapped[UUID | None] = mapped_column()
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
