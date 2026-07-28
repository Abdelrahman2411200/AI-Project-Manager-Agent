"""Typed contracts for full-version comparison, scenarios, and regeneration."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal["task", "milestone"]


class CriticalPathNodeView(BaseModel):
    stable_key: str
    earliest_start_hours: Decimal
    earliest_finish_hours: Decimal
    latest_start_hours: Decimal
    latest_finish_hours: Decimal
    slack_hours: Decimal
    critical: bool


class ScenarioOverrides(BaseModel):
    capacity_hours_per_week: Decimal | None = Field(default=None, gt=0, le=10_000)
    deadline: date | None = None
    task_effort_hours: dict[str, Decimal] = Field(default_factory=dict, max_length=500)

    @model_validator(mode="after")
    def require_override(self) -> ScenarioOverrides:
        if (
            self.capacity_hours_per_week is None
            and self.deadline is None
            and not self.task_effort_hours
        ):
            raise ValueError("At least one scenario override is required.")
        invalid = [
            key
            for key, value in self.task_effort_hours.items()
            if not key.startswith("TASK-") or value <= 0 or value > 100_000
        ]
        if invalid:
            raise ValueError(f"Invalid task effort overrides: {', '.join(sorted(invalid))}.")
        return self


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    baseline_version_id: UUID | None = None
    overrides: ScenarioOverrides


class ScenarioView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    baseline_version_id: UUID
    name: str
    overrides_json: dict[str, Any]
    result_json: dict[str, Any]
    explanation_json: dict[str, Any] | None
    status: str
    baseline_content_hash: str
    calculation_version: str
    created_at: datetime


class PlanComparisonView(BaseModel):
    from_version_id: UUID
    to_version_id: UUID
    changes: list[dict[str, Any]]
    summary: dict[str, int]
    schedule_delta_days: int | None
    risk_delta: int
    scope_delta: int


class RegenerationTarget(BaseModel):
    entity_type: EntityType
    stable_key: str = Field(pattern=r"^(TASK|MS)-\d{3,}$")
    fields: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def key_matches_entity(self) -> RegenerationTarget:
        prefix = "TASK-" if self.entity_type == "task" else "MS-"
        if not self.stable_key.startswith(prefix):
            raise ValueError("Stable key does not match entity type.")
        if len(self.fields) != len(set(self.fields)):
            raise ValueError("Regeneration fields must be unique.")
        return self


class RegenerationReplacement(BaseModel):
    entity_type: EntityType
    stable_key: str = Field(pattern=r"^(TASK|MS)-\d{3,}$")
    values: dict[str, Any] = Field(min_length=1, max_length=12)


class RegenerationCreate(BaseModel):
    targets: list[RegenerationTarget] = Field(min_length=1, max_length=50)
    replacements: list[RegenerationReplacement] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def exact_target_coverage(self) -> RegenerationCreate:
        target_map = {
            (item.entity_type, item.stable_key): set(item.fields) for item in self.targets
        }
        if len(target_map) != len(self.targets):
            raise ValueError("Regeneration targets must be unique.")
        replacement_map = {
            (item.entity_type, item.stable_key): set(item.values) for item in self.replacements
        }
        if target_map != replacement_map:
            raise ValueError("Replacements must exactly match every selected target and field.")
        return self


class RegenerationDecision(BaseModel):
    reason: str | None = Field(default=None, min_length=3, max_length=1000)


class RegenerationProposalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    version_id: UUID
    baseline_content_hash: str
    selection_json: list[dict[str, Any]]
    replacements_json: list[dict[str, Any]]
    diff_json: list[dict[str, Any]]
    impact_json: dict[str, Any]
    status: str
    row_version: int
    created_at: datetime
    updated_at: datetime


class RiskRelationInput(BaseModel):
    entity_type: Literal["task", "milestone", "dependency", "requirement"]
    entity_ref: str = Field(min_length=3, max_length=80)


class RiskCreate(BaseModel):
    category: Literal[
        "technical",
        "schedule",
        "scope",
        "dependency",
        "security",
        "quality",
        "external",
    ]
    description: str = Field(min_length=10, max_length=2000)
    probability: Literal["unlikely", "possible", "likely"]
    impact: Literal["low", "medium", "high", "critical"]
    trigger: str = Field(min_length=3, max_length=500)
    mitigation: str = Field(min_length=10, max_length=1000)
    contingency: str = Field(min_length=10, max_length=1000)
    relations: list[RiskRelationInput] = Field(default_factory=list, max_length=50)
    source_fact_refs: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_relations(self) -> RiskCreate:
        values = {(item.entity_type, item.entity_ref) for item in self.relations}
        if len(values) != len(self.relations):
            raise ValueError("Risk relations must be unique.")
        return self


class RiskUpdate(BaseModel):
    category: (
        Literal[
            "technical",
            "schedule",
            "scope",
            "dependency",
            "security",
            "quality",
            "external",
        ]
        | None
    ) = None
    description: str | None = Field(default=None, min_length=10, max_length=2000)
    probability: Literal["unlikely", "possible", "likely"] | None = None
    impact: Literal["low", "medium", "high", "critical"] | None = None
    trigger: str | None = Field(default=None, min_length=3, max_length=500)
    mitigation: str | None = Field(default=None, min_length=10, max_length=1000)
    contingency: str | None = Field(default=None, min_length=10, max_length=1000)
    relations: list[RiskRelationInput] | None = Field(default=None, max_length=50)
    source_fact_refs: list[str] | None = Field(default=None, max_length=30)
    status: Literal["open", "mitigated", "closed"] | None = None

    @model_validator(mode="after")
    def require_change_and_unique_relations(self) -> RiskUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one risk field must be supplied.")
        if self.relations is not None:
            values = {(item.entity_type, item.entity_ref) for item in self.relations}
            if len(values) != len(self.relations):
                raise ValueError("Risk relations must be unique.")
        return self


class RiskRelationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    risk_id: UUID
    version_id: UUID
    entity_type: str
    entity_ref: str


class AdvancedRiskView(BaseModel):
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
    source_fact_refs: list[str]
    status: str
    relations: list[RiskRelationView]


class RiskMutationView(BaseModel):
    item: AdvancedRiskView
    plan_row_version: int
    plan_content_hash: str


class RiskDeleteView(BaseModel):
    stable_key: str
    plan_row_version: int
    plan_content_hash: str
