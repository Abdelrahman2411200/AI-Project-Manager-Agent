"""API and persisted factual-data contracts for Phase 9 insights."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecommendationState = Literal["open", "accepted", "dismissed", "deferred"]
RecommendationDecision = Literal["accept", "dismiss", "defer"]
ReportType = Literal["weekly", "project", "milestone", "risk", "comparison"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )


class RecommendationEvidenceView(StrictSchema):
    id: UUID
    entity_type: str
    entity_ref: str
    fact_key: str
    fact_value: Any
    captured_at: datetime


class RecommendationDecisionRequest(StrictSchema):
    reason: Annotated[str, Field(min_length=3, max_length=1000)] | None = None
    defer_until: date | None = None


class RecommendationDecisionView(StrictSchema):
    id: UUID
    recommendation_id: UUID
    decision: RecommendationDecision
    reason: str | None
    defer_until: date | None
    occurred_at: datetime


class RecommendationView(StrictSchema):
    id: UUID
    project_id: UUID
    version_id: UUID
    snapshot_id: UUID
    recommendation_type: str
    detection_code: str
    why_it_matters: str
    suggested_action: str
    expected_impact: str
    urgency: str
    risk: str
    approval_required: bool
    verification_step: str
    alternatives: list[str]
    state: RecommendationState
    explanation_source: Literal["deterministic", "ai"]
    evidence: list[RecommendationEvidenceView]
    latest_decision: RecommendationDecisionView | None = None
    row_version: int
    created_at: datetime
    updated_at: datetime


class ReportCreateRequest(StrictSchema):
    report_type: ReportType = "weekly"
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("Report period end cannot precede its start.")
        if (self.period_end - self.period_start).days > 366:
            raise ValueError("Report periods cannot exceed 367 inclusive days.")
        return self


class EvidenceFact(StrictSchema):
    entity_type: Literal[
        "task",
        "milestone",
        "dependency",
        "metric",
        "forecast",
        "detection",
        "event",
        "project",
        "risk",
        "period",
    ]
    entity_ref: Annotated[str, Field(min_length=2, max_length=80)]
    fact_key: Annotated[str, Field(min_length=2, max_length=80)]
    value: Any


class FactualReportData(StrictSchema):
    schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    project_name: Annotated[str, Field(min_length=1, max_length=120)]
    version_id: UUID
    version_number: int
    report_type: ReportType
    period_start: date
    period_end: date
    state_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    event_cursor: str | None
    evidence: dict[str, EvidenceFact]
    metrics: dict[str, Any]
    completed_refs: list[str]
    blocker_refs: list[str]
    risk_refs: list[str]
    next_action_refs: list[str]
    health_label: str
    health_rule_codes: list[str]
    calculation_versions: dict[str, str]


class ReportSummaryView(StrictSchema):
    id: UUID
    project_id: UUID
    version_id: UUID
    run_id: UUID
    report_type: ReportType
    period_start: date
    period_end: date
    status: Literal["completed", "partial"]
    narrative_failure_code: str | None
    content_hash: str
    created_at: datetime


class ReportView(ReportSummaryView):
    data: FactualReportData
    narrative: dict[str, Any] | None
    markdown: str


class ReportStartView(StrictSchema):
    run_id: UUID
    status: Literal["queued", "running", "partial", "failed", "completed"]
    report_id: UUID | None = None
    duplicate: bool = False
