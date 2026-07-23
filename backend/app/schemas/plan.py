"""API contracts for draft editing, validation, review, and activation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlanState = Literal[
    "idea",
    "clarification_required",
    "generating",
    "draft",
    "under_review",
    "approved",
    "active",
    "archived",
    "superseded",
]
Complexity = Literal["trivial", "low", "medium", "high"]


class ProjectAnalysisView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_id: UUID
    summary: str
    project_type: str
    intended_users: list[str]
    objectives: list[dict[str, Any]]
    success_criteria: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    workstreams: list[str]
    assumptions: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    complexity: str
    mvp_boundary: list[str]
    excluded_scope: list[str]


class PlanApprovalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    version_id: UUID
    actor_id: UUID
    decision: str
    reason: str | None
    content_hash: str
    created_at: datetime


class MilestoneView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_id: UUID
    stable_key: str
    module_refs: list[str]
    name: str
    description: str
    objective: str
    deliverable: str
    sequence: int
    target_date: date | None
    planned_effort_hours: Decimal
    acceptance_criteria: list[str]
    planned_start: date | None
    planned_finish: date | None
    status: str
    source: str
    protected: bool
    locked: bool
    row_version: int


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_id: UUID
    milestone_id: UUID
    parent_id: UUID | None
    stable_key: str
    title: str
    description: str
    deliverable: str
    acceptance_criteria: list[str]
    definition_of_done: list[str]
    effort_min_hours: Decimal
    effort_likely_hours: Decimal
    effort_max_hours: Decimal
    complexity: str
    workstreams: list[str]
    skill_tags: list[str]
    source: str
    requirement_refs: list[str]
    assumption_refs: list[str]
    locked: bool
    protected: bool
    priority_score: Decimal
    priority_label: str
    priority_breakdown: dict[str, Any]
    planned_start: date | None
    planned_finish: date | None
    status: str
    row_version: int


class DependencyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dependency_type: str
    reason: str
    evidence_refs: list[str]
    confidence_label: str
    source: str
    protected: bool


class RiskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_id: UUID
    stable_key: str
    category: str
    description: str
    probability: str
    impact: str
    severity: int
    trigger: str
    mitigation: str
    contingency: str
    related_refs: list[str]
    source_fact_refs: list[str]
    status: str


class PlanVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    number: int
    state: PlanState
    based_on_id: UUID | None
    reason: str
    content_hash: str
    quality_status: str
    row_version: int
    created_at: datetime
    updated_at: datetime


class PlanGraphView(PlanVersionSummary):
    quality_report: dict[str, Any]
    analysis: ProjectAnalysisView | None
    milestones: list[MilestoneView]
    tasks: list[TaskView]
    dependencies: list[DependencyView]
    risks: list[RiskView]
    approvals: list[PlanApprovalView]


class PlanMetadataUpdate(BaseModel):
    reason: str | None = Field(default=None, min_length=3, max_length=500)
    analysis_summary: str | None = Field(default=None, min_length=20, max_length=2000)
    mvp_boundary: list[str] | None = Field(default=None, min_length=1, max_length=30)
    excluded_scope: list[str] | None = Field(default=None, max_length=30)
    assumptions: list[dict[str, Any]] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def require_one_change(self) -> PlanMetadataUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one plan field must be supplied.")
        return self


class MilestoneCreate(BaseModel):
    module_refs: list[str] = Field(min_length=1, max_length=10)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20, max_length=2000)
    objective: str = Field(min_length=10, max_length=500)
    deliverable: str = Field(min_length=3, max_length=500)
    sequence: int = Field(ge=1, le=9999)
    target_date: date | None = None
    planned_effort_hours: Decimal = Field(gt=0, le=100_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=10)
    locked: bool = False


class MilestoneUpdate(BaseModel):
    module_refs: list[str] | None = Field(default=None, min_length=1, max_length=10)
    name: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, min_length=20, max_length=2000)
    objective: str | None = Field(default=None, min_length=10, max_length=500)
    deliverable: str | None = Field(default=None, min_length=3, max_length=500)
    sequence: int | None = Field(default=None, ge=1, le=9999)
    target_date: date | None = None
    planned_effort_hours: Decimal | None = Field(default=None, gt=0, le=100_000)
    acceptance_criteria: list[str] | None = Field(default=None, min_length=1, max_length=10)
    locked: bool | None = None

    @model_validator(mode="after")
    def require_one_change(self) -> MilestoneUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one milestone field must be supplied.")
        return self


class PriorityFactorsInput(BaseModel):
    mvp_necessity: int = Field(ge=0, le=100)
    deadline_urgency: int = Field(ge=0, le=100)
    user_value: int = Field(ge=0, le=100)
    risk_reduction: int = Field(ge=0, le=100)
    user_preference: int = Field(ge=0, le=100)


class TaskCreate(BaseModel):
    milestone_id: UUID
    parent_id: UUID | None = None
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20, max_length=2000)
    deliverable: str = Field(min_length=3, max_length=500)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=10)
    definition_of_done: list[str] = Field(min_length=1, max_length=10)
    effort_min_hours: Decimal = Field(gt=0, le=100_000)
    effort_likely_hours: Decimal = Field(gt=0, le=100_000)
    effort_max_hours: Decimal = Field(gt=0, le=100_000)
    complexity: Complexity
    workstreams: list[str] = Field(min_length=1, max_length=3)
    skill_tags: list[str] = Field(default_factory=list, max_length=8)
    requirement_refs: list[str] = Field(default_factory=list, max_length=20)
    assumption_refs: list[str] = Field(default_factory=list, max_length=20)
    priority_factors: PriorityFactorsInput
    locked: bool = False

    @model_validator(mode="after")
    def validate_effort(self) -> TaskCreate:
        if not self.effort_min_hours <= self.effort_likely_hours <= self.effort_max_hours:
            raise ValueError("Task effort must satisfy min <= likely <= max.")
        return self


class TaskUpdate(BaseModel):
    milestone_id: UUID | None = None
    parent_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, min_length=20, max_length=2000)
    deliverable: str | None = Field(default=None, min_length=3, max_length=500)
    acceptance_criteria: list[str] | None = Field(default=None, min_length=1, max_length=10)
    definition_of_done: list[str] | None = Field(default=None, min_length=1, max_length=10)
    effort_min_hours: Decimal | None = Field(default=None, gt=0, le=100_000)
    effort_likely_hours: Decimal | None = Field(default=None, gt=0, le=100_000)
    effort_max_hours: Decimal | None = Field(default=None, gt=0, le=100_000)
    complexity: Complexity | None = None
    workstreams: list[str] | None = Field(default=None, min_length=1, max_length=3)
    skill_tags: list[str] | None = Field(default=None, max_length=8)
    requirement_refs: list[str] | None = Field(default=None, max_length=20)
    assumption_refs: list[str] | None = Field(default=None, max_length=20)
    priority_factors: PriorityFactorsInput | None = None
    locked: bool | None = None

    @model_validator(mode="after")
    def require_one_change(self) -> TaskUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one task field must be supplied.")
        return self


class DependencyCreate(BaseModel):
    predecessor_id: UUID
    successor_id: UUID
    reason: str = Field(min_length=10, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    confidence_label: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def endpoints_differ(self) -> DependencyCreate:
        if self.predecessor_id == self.successor_id:
            raise ValueError("Dependency endpoints must differ.")
        return self


class PlanValidationView(BaseModel):
    passed: bool
    issues: list[dict[str, Any]]
    warning_codes: list[str]
    calculation_versions: dict[str, str]
    content_hash: str
    row_version: int


class ApprovalRequest(BaseModel):
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str | None = Field(default=None, min_length=3, max_length=1000)


class ChangesRequestedInput(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class PlanDiffView(BaseModel):
    from_version_id: UUID
    to_version_id: UUID
    changes: list[dict[str, Any]]


class MilestoneMutationView(BaseModel):
    item: MilestoneView
    plan: PlanVersionSummary


class TaskMutationView(BaseModel):
    item: TaskView
    plan: PlanVersionSummary


class DependencyMutationView(BaseModel):
    item: DependencyView
    plan: PlanVersionSummary
