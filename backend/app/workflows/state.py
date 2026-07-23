"""Persisted, versioned workflow checkpoints constructed only by application code."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowStatus = Literal[
    "queued", "running", "waiting_for_user", "partial", "failed", "completed", "cancelled"
]
ContentHash = Annotated[str, Field(pattern=r"^(sha256:[0-9a-f]{64}|v[0-9]+)$")]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EntityReference(StateModel):
    entity_type: Annotated[str, Field(min_length=2, max_length=80)]
    entity_id: UUID
    version_or_hash: ContentHash


class AgentStateBase(StateModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    project_id: UUID
    workflow: str
    status: WorkflowStatus
    current_step: Annotated[str, Field(min_length=2, max_length=80)]
    completed_steps: Annotated[list[str], Field(max_length=100)] = []
    failed_steps: Annotated[list[str], Field(max_length=100)] = []
    retry_counts: dict[str, Annotated[int, Field(ge=0, le=10)]] = {}
    warnings: Annotated[list[str], Field(max_length=100)] = []
    input_refs: Annotated[list[EntityReference], Field(max_length=100)] = []
    output_refs: Annotated[list[EntityReference], Field(max_length=100)] = []
    started_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_common_state(self) -> Self:
        if self.updated_at < self.started_at:
            raise ValueError("updated_at cannot precede started_at.")
        overlap = set(self.completed_steps) & set(self.failed_steps)
        if overlap:
            raise ValueError(f"Steps cannot be both completed and failed: {sorted(overlap)}")
        if self.status == "failed" and not self.failed_steps:
            raise ValueError("Failed states require at least one failed step.")
        return self


class PlanningAgentState(AgentStateBase):
    workflow: Literal["planning"] = "planning"
    project_version: Annotated[int, Field(ge=1)]
    intake_ref: EntityReference
    clarification_ids: Annotated[list[UUID], Field(max_length=30)] = []
    decision_ids: Annotated[list[UUID], Field(max_length=100)] = []
    analysis_ref: EntityReference | None = None
    module_refs: Annotated[list[EntityReference], Field(max_length=100)] = []
    milestone_refs: Annotated[list[EntityReference], Field(max_length=500)] = []
    task_refs: Annotated[list[EntityReference], Field(max_length=5000)] = []
    dependency_refs: Annotated[list[EntityReference], Field(max_length=10_000)] = []
    risk_refs: Annotated[list[EntityReference], Field(max_length=500)] = []
    validation_report_ref: EntityReference | None = None
    proposed_plan_version_id: UUID | None = None
    approval_required: bool = True

    @model_validator(mode="after")
    def validate_planning_terminal_state(self) -> Self:
        if self.status == "waiting_for_user" and not self.clarification_ids:
            raise ValueError("waiting_for_user requires at least one open clarification.")
        if self.status == "completed" and (
            self.proposed_plan_version_id is None or self.validation_report_ref is None
        ):
            raise ValueError("Completed planning requires a persisted draft and quality report.")
        return self


class MonitoringAgentState(AgentStateBase):
    workflow: Literal["monitoring"] = "monitoring"
    active_plan_version_id: UUID
    event_cursor: Annotated[str, Field(min_length=1, max_length=200)]
    readiness_result_ref: EntityReference | None = None
    progress_result_ref: EntityReference | None = None
    schedule_result_ref: EntityReference | None = None
    health_result_ref: EntityReference | None = None
    detected_condition_codes: Annotated[list[str], Field(max_length=100)] = []
    recommendation_ids: Annotated[list[UUID], Field(max_length=100)] = []
    state_hash: ContentHash
    state_is_current: bool = True
    stale_requeued: bool = False

    @model_validator(mode="after")
    def validate_monitoring_terminal_state(self) -> Self:
        if self.status == "completed" and not (self.state_is_current or self.stale_requeued):
            raise ValueError("Completed monitoring must be current or marked stale and requeued.")
        if self.state_is_current and self.stale_requeued:
            raise ValueError("A current monitoring state cannot also be stale and requeued.")
        return self


class ReportingAgentState(AgentStateBase):
    workflow: Literal["reporting"] = "reporting"
    active_plan_version_id: UUID
    report_type: Literal["weekly", "on_demand"]
    period_start: date
    period_end: date
    event_cursor: Annotated[str, Field(min_length=1, max_length=200)]
    report_data_ref: EntityReference | None = None
    narrative_ref: EntityReference | None = None
    report_id: UUID | None = None
    export_format: Literal["markdown", "pdf"]
    markdown_export_ref: EntityReference | None = None
    pdf_export_ref: EntityReference | None = None
    claim_validation_errors: Annotated[list[str], Field(max_length=100)] = []

    @model_validator(mode="after")
    def validate_reporting_state(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("Report period_end cannot precede period_start.")
        if self.status == "completed" and (
            self.report_data_ref is None
            or self.report_id is None
            or self.markdown_export_ref is None
        ):
            raise ValueError("Completed reporting requires stored data, report, and Markdown.")
        if (
            self.export_format == "pdf"
            and "render_pdf" in self.failed_steps
            and self.status != "partial"
        ):
            raise ValueError("A PDF rendering failure must produce a partial report state.")
        return self
