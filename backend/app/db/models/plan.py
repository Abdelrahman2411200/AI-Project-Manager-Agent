"""Version-local planning entities produced by the persistent workflow."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class PlanVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plan_versions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('idea', 'clarification_required', 'generating', 'draft', "
            "'under_review', 'approved', 'active', 'archived', 'superseded')",
            name="state_allowed",
        ),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        CheckConstraint(
            "quality_status IN ('passed', 'failed')",
            name="quality_status_allowed",
        ),
        UniqueConstraint("project_id", "number", name="plan_version_project_number"),
        UniqueConstraint("source_run_id", name="plan_version_source_run"),
        Index("ix_plan_versions_project_state_created", "project_id", "state", "created_at"),
        Index(
            "uq_plan_versions_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
            sqlite_where=text("state = 'active'"),
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    based_on_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    source_run_id: Mapped[UUID] = mapped_column(nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class PlanApproval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "plan_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'changes_requested', 'rejected')",
            name="decision_allowed",
        ),
        Index("ix_plan_approvals_version_created", "version_id", "created_at"),
        Index("ix_plan_approvals_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ProjectAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_analyses"
    __table_args__ = (UniqueConstraint("version_id", name="project_analysis_version"),)

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    project_type: Mapped[str] = mapped_column(String(80), nullable=False)
    intended_users: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    objectives: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    success_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    modules: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    workstreams: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    assumptions: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    complexity: Mapped[str] = mapped_column(String(20), nullable=False)
    mvp_boundary: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    excluded_scope: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)


class ClarificationQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clarification_questions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'answered', 'assumed', 'dismissed')",
            name="status_allowed",
        ),
        CheckConstraint(
            "answer_type IN ('text', 'single_choice', 'multi_choice', 'boolean', 'date', 'number')",
            name="answer_type_allowed",
        ),
        UniqueConstraint("project_id", "stable_key", name="clarification_project_key"),
        UniqueConstraint("run_id", "source_temp_id", name="clarification_run_source"),
        Index("ix_clarifications_project_status", "project_id", "status"),
        Index("ix_clarifications_run_created", "run_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(20), nullable=False)
    source_temp_id: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    affects: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(24), nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    default_assumption: Mapped[str | None] = mapped_column(String(500))
    source_fact_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    answer_json: Mapped[Any | None] = mapped_column(JSON_DOCUMENT)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    answered_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanningDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "planning_decisions"
    __table_args__ = (
        CheckConstraint("decision_type IN ('answer', 'assumption')", name="type_allowed"),
        UniqueConstraint("project_id", "stable_key", name="planning_decision_project_key"),
        Index("ix_planning_decisions_run_created", "run_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(24), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clarification_questions.id", ondelete="RESTRICT")
    )
    source_fact_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)


class Milestone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint("planned_effort_hours > 0", name="effort_positive"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("source IN ('ai', 'user')", name="source_allowed"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        UniqueConstraint("version_id", "stable_key", name="milestone_version_key"),
        UniqueConstraint("version_id", "sequence", name="milestone_version_sequence"),
        UniqueConstraint("id", "version_id", name="milestone_id_version"),
        Index("ix_milestones_version_sequence", "version_id", "sequence"),
    )

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(20), nullable=False)
    module_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    deliverable: Mapped[str] = mapped_column(String(500), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    planned_effort_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ready', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("source IN ('ai', 'user')", name="source_allowed"),
        CheckConstraint(
            "complexity IN ('trivial', 'low', 'medium', 'high')",
            name="complexity_allowed",
        ),
        CheckConstraint(
            "effort_min_hours > 0 AND effort_likely_hours >= effort_min_hours "
            "AND effort_max_hours >= effort_likely_hours",
            name="effort_ordered",
        ),
        CheckConstraint("priority_score >= 0 AND priority_score <= 100", name="priority_range"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        UniqueConstraint("version_id", "stable_key", name="task_version_key"),
        UniqueConstraint("id", "version_id", name="task_id_version"),
        ForeignKeyConstraint(
            ["milestone_id", "version_id"],
            ["milestones.id", "milestones.version_id"],
            name="task_milestone_same_version",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["parent_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="task_parent_same_version",
            ondelete="CASCADE",
        ),
        Index("ix_tasks_version_milestone", "version_id", "milestone_id"),
        Index("ix_tasks_version_status_priority", "version_id", "status", "priority_score"),
    )

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    milestone_id: Mapped[UUID] = mapped_column(nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column()
    stable_key: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    deliverable: Mapped[str] = mapped_column(String(500), nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    definition_of_done: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    effort_min_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    effort_likely_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    effort_max_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    complexity: Mapped[str] = mapped_column(String(20), nullable=False)
    workstreams: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    skill_tags: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    requirement_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    assumption_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    priority_label: Mapped[str] = mapped_column(String(16), nullable=False)
    priority_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class TaskDependency(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("dependency_type = 'finish_to_start'", name="type_finish_to_start"),
        CheckConstraint("source IN ('ai', 'user')", name="source_allowed"),
        CheckConstraint("predecessor_id <> successor_id", name="endpoints_distinct"),
        UniqueConstraint(
            "version_id",
            "predecessor_id",
            "successor_id",
            name="task_dependency_edge",
        ),
        ForeignKeyConstraint(
            ["predecessor_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="dependency_predecessor_same_version",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["successor_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name="dependency_successor_same_version",
            ondelete="CASCADE",
        ),
        Index("ix_task_dependencies_version_successor", "version_id", "successor_id"),
    )

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id: Mapped[UUID] = mapped_column(nullable=False)
    successor_id: Mapped[UUID] = mapped_column(nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Risk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint(
            "category IN ('technical', 'schedule', 'scope', 'dependency', 'security', "
            "'quality', 'external')",
            name="category_allowed",
        ),
        CheckConstraint(
            "probability IN ('unlikely', 'possible', 'likely')",
            name="probability_allowed",
        ),
        CheckConstraint(
            "impact IN ('low', 'medium', 'high', 'critical')",
            name="impact_allowed",
        ),
        CheckConstraint("status IN ('open', 'mitigated', 'closed')", name="status_allowed"),
        UniqueConstraint("version_id", "stable_key", name="risk_version_key"),
        Index("ix_risks_version_status", "version_id", "status"),
    )

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(24), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[str] = mapped_column(String(16), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(500), nullable=False)
    mitigation: Mapped[str] = mapped_column(String(1000), nullable=False)
    contingency: Mapped[str] = mapped_column(String(1000), nullable=False)
    related_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    source_fact_refs: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


@event.listens_for(PlanApproval, "before_update")
@event.listens_for(PlanApproval, "before_delete")
def _prevent_approval_mutation(*_: object) -> None:
    raise ValueError("Plan approvals are append-only.")
