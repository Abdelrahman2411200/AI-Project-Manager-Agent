"""API contracts for active task execution and deterministic monitoring."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskStatus = Literal[
    "pending",
    "ready",
    "in_progress",
    "blocked",
    "completed",
    "cancelled",
]


class TaskStatusTransitionRequest(BaseModel):
    to_status: TaskStatus
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_reason_for_exception_state(self) -> TaskStatusTransitionRequest:
        if self.to_status in {"blocked", "cancelled"} and (
            self.reason is None or len(self.reason.strip()) < 3
        ):
            raise ValueError(f"A reason of at least 3 characters is required for {self.to_status}.")
        return self


class TaskProgressUpdateRequest(BaseModel):
    fraction: Decimal = Field(ge=0, le=1, decimal_places=4)
    actual_effort_hours: Decimal = Field(ge=0, le=1_000_000, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)


class TaskExecutionView(BaseModel):
    id: UUID
    task_id: UUID
    project_id: UUID
    version_id: UUID
    milestone_id: UUID
    milestone_key: str
    milestone_name: str
    parent_id: UUID | None
    stable_key: str
    title: str
    deliverable: str
    priority_score: Decimal
    priority_label: str
    planned_start: date | None
    planned_finish: date | None
    effort_likely_hours: Decimal
    workstreams: list[str]
    status: TaskStatus
    progress_fraction: Decimal
    actual_effort_hours: Decimal
    blocked_reason: str | None
    prerequisites_satisfied: bool
    ready_to_start: bool
    incomplete_predecessor_refs: list[str]
    row_version: int
    status_changed_at: datetime


class TaskStatusEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    version_id: UUID
    task_id: UUID
    actor_id: UUID | None
    actor_type: Literal["user", "system"]
    from_status: TaskStatus | None
    to_status: TaskStatus
    reason: str
    progress_fraction: Decimal
    correlation_id: str
    occurred_at: datetime


class ProgressUpdateView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    version_id: UUID
    task_id: UUID
    actor_id: UUID | None
    fraction: Decimal
    actual_effort_hours: Decimal
    note: str | None
    source: Literal["user", "system"]
    correlation_id: str
    occurred_at: datetime


class WeightedMetricView(BaseModel):
    fraction: Decimal | None
    weighted_completed_hours: Decimal
    estimated_hours: Decimal
    active_leaf_count: int
    unestimated_leaf_count: int


class MilestoneProgressView(WeightedMetricView):
    milestone_id: UUID
    stable_key: str
    name: str


class TaskProgressView(BaseModel):
    task_id: UUID
    stable_key: str
    fraction: Decimal
    status: TaskStatus


class ProjectProgressView(BaseModel):
    project_id: UUID
    version_id: UUID
    state_hash: str
    as_of: date
    calculated_at: datetime
    calculation_version: str
    project: WeightedMetricView
    milestones: list[MilestoneProgressView]
    tasks: list[TaskProgressView]
    warning_codes: list[str]
    insufficient_data: bool


class EvidenceView(BaseModel):
    rule_code: str
    values: dict[str, str]
    references: list[str]


class DetectionView(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    references: list[str]
    values: dict[str, str]
    calculation_version: str


class ProjectHealthView(BaseModel):
    project_id: UUID
    version_id: UUID
    state_hash: str
    as_of: date
    calculated_at: datetime
    label: Literal["Completed", "On track", "At risk", "Delayed", "Insufficient data"]
    rule_codes: list[str]
    evidence: list[EvidenceView]
    detections: list[DetectionView]
    forecast_finish: date | None
    project_finish: date | None
    deadline: date | None
    deadline_feasible: bool | None
    blocking_path: list[str]
    schedule_warnings: list[dict[str, Any]]
    calculation_versions: dict[str, str]


class ExecutionBoardView(BaseModel):
    project_id: UUID
    version_id: UUID
    version_number: int
    tasks: list[TaskExecutionView]
    recent_events: list[TaskStatusEventView]
    progress: ProjectProgressView
    health: ProjectHealthView


class TaskStatusMutationView(BaseModel):
    task: TaskExecutionView
    event: TaskStatusEventView
    readiness_changes: list[TaskStatusEventView]
    progress: ProjectProgressView
    health: ProjectHealthView


class TaskProgressMutationView(BaseModel):
    task: TaskExecutionView
    update: ProgressUpdateView
    progress: ProjectProgressView
    health: ProjectHealthView
