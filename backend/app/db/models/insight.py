"""Grounded recommendations, factual reports, and safe product telemetry."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
OPEN_RECOMMENDATION = text("state IN ('open', 'deferred')")


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation_type IN ('dependency_warning', 'schedule_warning', "
            "'scope_warning', 'risk_mitigation', 'priority_adjustment', 'next_action')",
            name="type_allowed",
        ),
        CheckConstraint(
            "state IN ('open', 'accepted', 'dismissed', 'deferred')",
            name="state_allowed",
        ),
        CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'immediate')",
            name="urgency_allowed",
        ),
        CheckConstraint(
            "explanation_source IN ('deterministic', 'ai')",
            name="explanation_source_allowed",
        ),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        Index(
            "uq_recommendations_open_input",
            "project_id",
            "recommendation_type",
            "input_hash",
            unique=True,
            sqlite_where=OPEN_RECOMMENDATION,
            postgresql_where=OPEN_RECOMMENDATION,
        ),
        Index(
            "ix_recommendations_project_state_urgency",
            "project_id",
            "state",
            "urgency",
        ),
        Index("ix_recommendations_version_created", "version_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("monitoring_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    detection_code: Mapped[str] = mapped_column(String(80), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(String(1000), nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(1000), nullable=False)
    expected_impact: Mapped[str] = mapped_column(String(1000), nullable=False)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    risk: Mapped[str] = mapped_column(String(500), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_step: Mapped[str] = mapped_column(String(1000), nullable=False)
    alternatives: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    explanation_source: Mapped[str] = mapped_column(String(16), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class RecommendationEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recommendation_evidence"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('task', 'milestone', 'dependency', 'metric', 'forecast', "
            "'detection', 'event', 'project')",
            name="entity_type_allowed",
        ),
        UniqueConstraint(
            "recommendation_id",
            "entity_type",
            "entity_ref",
            "fact_key",
            name="recommendation_evidence_fact",
        ),
        Index("ix_recommendation_evidence_recommendation", "recommendation_id"),
    )

    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(80), nullable=False)
    fact_value: Mapped[Any] = mapped_column(JSON_DOCUMENT, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RecommendationDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recommendation_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('accept', 'dismiss', 'defer')",
            name="decision_allowed",
        ),
        CheckConstraint(
            "(decision = 'defer' AND defer_until IS NOT NULL) OR "
            "(decision <> 'defer' AND defer_until IS NULL)",
            name="defer_date_required",
        ),
        UniqueConstraint("event_key", name="recommendation_decision_event_key"),
        Index(
            "ix_recommendation_decisions_recommendation_occurred",
            "recommendation_id",
            "occurred_at",
        ),
    )

    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    defer_until: Mapped[date | None] = mapped_column(Date)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Report(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('weekly', 'project', 'milestone', 'risk', 'comparison')",
            name="type_allowed",
        ),
        CheckConstraint("status IN ('completed', 'partial')", name="status_allowed"),
        CheckConstraint("period_end >= period_start", name="period_order"),
        UniqueConstraint("project_id", "input_hash", name="report_project_input"),
        Index("ix_reports_project_type_created", "project_id", "report_type", "created_at"),
        Index("ix_reports_version_period", "version_id", "period_start", "period_end"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    narrative_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    narrative_failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ProductMetricEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_metric_events"
    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_nonnegative"),
        Index("ix_product_metrics_name_occurred", "name", "occurred_at"),
        Index("ix_product_metrics_project_occurred", "project_id", "occurred_at"),
        Index("ix_product_metrics_run_occurred", "run_id", "occurred_at"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_attributes: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


@event.listens_for(RecommendationEvidence, "before_update")
@event.listens_for(RecommendationEvidence, "before_delete")
@event.listens_for(RecommendationDecision, "before_update")
@event.listens_for(RecommendationDecision, "before_delete")
@event.listens_for(Report, "before_update")
@event.listens_for(Report, "before_delete")
@event.listens_for(ProductMetricEvent, "before_update")
@event.listens_for(ProductMetricEvent, "before_delete")
def _prevent_insight_history_mutation(*_: object) -> None:
    raise ValueError("Evidence, decisions, reports, and metric events are append-only.")
