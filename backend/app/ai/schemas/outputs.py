"""Strict semantic contracts for all model-authored Phase 4 output."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=3, max_length=120)]
Description = Annotated[str, Field(min_length=20, max_length=2000)]
Reference = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_-]{1,79}$", max_length=80)]
ModuleId = Annotated[str, Field(pattern=r"^MOD-[0-9]{3,5}$")]
MilestoneId = Annotated[str, Field(pattern=r"^MS-[0-9]{3,5}$")]
TaskId = Annotated[str, Field(pattern=r"^TASK-[0-9]{3,5}$")]
DependencyId = Annotated[str, Field(pattern=r"^DEP-[0-9]{3,5}$")]
RiskId = Annotated[str, Field(pattern=r"^RISK-[0-9]{3,5}$")]
QuestionId = Annotated[str, Field(pattern=r"^Q-[0-9]{3,5}$")]
RecommendationId = Annotated[str, Field(pattern=r"^REC-[0-9]{3,5}$")]
Score = Annotated[int, Field(ge=0, le=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FactItem(StrictModel):
    text: Annotated[str, Field(min_length=3, max_length=500)]
    fact_ref: Reference


class DecisionDraft(StrictModel):
    text: Annotated[str, Field(min_length=3, max_length=500)]
    rationale: Annotated[str, Field(min_length=10, max_length=1000)]
    source_fact_refs: Annotated[list[Reference], Field(max_length=20)] = []
    confirmed: Literal[False] = False


class ModuleDraft(StrictModel):
    temp_id: ModuleId
    name: Text
    description: Description
    objective: Annotated[str, Field(min_length=10, max_length=500)]
    deliverables: Annotated[list[Text], Field(min_length=1, max_length=8)]
    workstreams: Annotated[list[Text], Field(min_length=1, max_length=5)]
    requirement_refs: Annotated[list[Reference], Field(min_length=1, max_length=20)]
    mvp_required: bool


class MilestoneDraft(StrictModel):
    temp_id: MilestoneId
    module_refs: Annotated[list[ModuleId], Field(min_length=1, max_length=10)]
    name: Text
    description: Description
    objective: Annotated[str, Field(min_length=10, max_length=500)]
    deliverable: Annotated[str, Field(min_length=3, max_length=500)]
    sequence: Annotated[int, Field(ge=1, le=9999)]
    target_date: date | None = None
    planned_effort_hours: Annotated[float, Field(gt=0, le=100_000)]
    acceptance_criteria: Annotated[list[Text], Field(min_length=1, max_length=10)]
    dependency_refs: Annotated[list[MilestoneId], Field(max_length=20)] = []

    @model_validator(mode="after")
    def cannot_depend_on_self(self) -> Self:
        if self.temp_id in self.dependency_refs:
            raise ValueError("A milestone cannot depend on itself.")
        return self


class TaskDraft(StrictModel):
    temp_id: TaskId
    milestone_ref: MilestoneId
    parent_ref: TaskId | None = None
    title: Text
    description: Description
    deliverable: Annotated[str, Field(min_length=3, max_length=500)]
    acceptance_criteria: Annotated[list[Text], Field(min_length=1, max_length=10)]
    definition_of_done: Annotated[list[Text], Field(min_length=1, max_length=10)]
    effort_min_hours: Annotated[float, Field(gt=0, le=100_000)]
    effort_likely_hours: Annotated[float, Field(gt=0, le=100_000)]
    effort_max_hours: Annotated[float, Field(gt=0, le=100_000)]
    complexity: Literal["trivial", "low", "medium", "high"]
    workstreams: Annotated[list[Text], Field(min_length=1, max_length=3)]
    skill_tags: Annotated[list[Text], Field(max_length=8)] = []
    mvp_necessity: Score
    user_value: Score
    deadline_urgency: Score
    risk_reduction: Score
    user_preference: Score
    source: Literal["ai", "user"]
    requirement_refs: Annotated[list[Reference], Field(max_length=20)] = []
    assumption_refs: Annotated[list[Reference], Field(max_length=20)] = []
    locked: Literal[False] = False

    @model_validator(mode="after")
    def validate_estimate_order_and_parent(self) -> Self:
        if not self.effort_min_hours <= self.effort_likely_hours <= self.effort_max_hours:
            raise ValueError("Task effort must satisfy min <= likely <= max.")
        if self.parent_ref == self.temp_id:
            raise ValueError("A task cannot be its own parent.")
        return self


class DependencySuggestion(StrictModel):
    temp_id: DependencyId
    predecessor_ref: TaskId
    successor_ref: TaskId
    type: Literal["finish_to_start"]
    reason: Annotated[str, Field(min_length=10, max_length=1000)]
    evidence_refs: Annotated[list[Reference], Field(min_length=1, max_length=20)]
    confidence_label: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def endpoints_must_differ(self) -> Self:
        if self.predecessor_ref == self.successor_ref:
            raise ValueError("Dependency endpoints must be distinct.")
        return self


class RiskDraft(StrictModel):
    temp_id: RiskId
    category: Literal[
        "technical", "schedule", "scope", "dependency", "security", "quality", "external"
    ]
    description: Description
    probability: Literal["unlikely", "possible", "likely"]
    impact: Literal["low", "medium", "high", "critical"]
    trigger: Annotated[str, Field(min_length=10, max_length=500)]
    mitigation: Annotated[str, Field(min_length=10, max_length=1000)]
    contingency: Annotated[str, Field(min_length=10, max_length=1000)]
    related_refs: Annotated[list[Reference], Field(max_length=20)] = []
    source_fact_refs: Annotated[list[Reference], Field(min_length=1, max_length=20)]


class ClarificationQuestion(StrictModel):
    temp_id: QuestionId
    question: Annotated[str, Field(min_length=10, max_length=500)]
    reason: Annotated[str, Field(min_length=10, max_length=1000)]
    affects: Annotated[
        list[Literal["scope", "schedule", "architecture", "quality", "cost"]],
        Field(min_length=1, max_length=5),
    ]
    required: bool
    answer_type: Literal["text", "single_choice", "multi_choice", "boolean", "date", "number"]
    options: Annotated[list[Text], Field(max_length=6)] = []
    default_assumption: Annotated[str, Field(min_length=3, max_length=500)] | None = None
    source_fact_refs: Annotated[list[Reference], Field(max_length=20)] = []

    @model_validator(mode="after")
    def validate_answer_options(self) -> Self:
        if self.answer_type in {"single_choice", "multi_choice"}:
            if not 2 <= len(self.options) <= 6:
                raise ValueError("Choice questions require between two and six options.")
        elif self.options:
            raise ValueError("Only choice questions may define options.")
        return self


class RecommendationDraft(StrictModel):
    temp_id: RecommendationId
    type: Literal[
        "dependency_warning",
        "schedule_warning",
        "scope_warning",
        "risk_mitigation",
        "priority_adjustment",
        "next_action",
    ]
    detection_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")]
    evidence_refs: Annotated[list[Reference], Field(min_length=1, max_length=20)]
    why_it_matters: Annotated[str, Field(min_length=10, max_length=1000)]
    suggested_action: Annotated[str, Field(min_length=10, max_length=1000)]
    expected_impact: Annotated[str, Field(min_length=10, max_length=1000)]
    urgency: Literal["low", "medium", "high", "immediate"]
    risk: Annotated[str, Field(min_length=3, max_length=500)]
    approval_required: bool
    verification_step: Annotated[str, Field(min_length=10, max_length=1000)]
    alternatives: Annotated[list[Text], Field(min_length=1, max_length=5)]


class CitedStatement(StrictModel):
    text: Annotated[str, Field(min_length=3, max_length=1000)]
    evidence_refs: Annotated[list[Reference], Field(min_length=1, max_length=20)]


class WeeklyReportNarrative(StrictModel):
    title: Text
    period_summary: Annotated[str, Field(min_length=20, max_length=2000)]
    completed_items: Annotated[list[CitedStatement], Field(max_length=50)] = []
    progress_statement: CitedStatement
    blockers: Annotated[list[CitedStatement], Field(max_length=30)] = []
    risks: Annotated[list[CitedStatement], Field(max_length=30)] = []
    next_actions: Annotated[list[CitedStatement], Field(max_length=30)] = []
    decisions_needed: Annotated[list[CitedStatement], Field(max_length=30)] = []
    caveats: Annotated[list[Text], Field(max_length=20)] = []


class ProjectAnalysisOutput(StrictModel):
    summary: Annotated[str, Field(min_length=20, max_length=2000)]
    project_type: Annotated[str, Field(min_length=3, max_length=80)]
    intended_users: Annotated[list[Text], Field(min_length=1, max_length=10)]
    objectives: Annotated[list[FactItem], Field(min_length=1, max_length=15)]
    success_criteria: Annotated[list[FactItem], Field(min_length=1, max_length=20)]
    modules: Annotated[list[ModuleDraft], Field(max_length=20)] = []
    workstreams: Annotated[list[Text], Field(min_length=1, max_length=20)]
    assumptions: Annotated[list[DecisionDraft], Field(max_length=30)] = []
    open_questions: Annotated[list[ClarificationQuestion], Field(max_length=30)] = []
    constraints: Annotated[list[FactItem], Field(max_length=30)] = []
    complexity: Literal["low", "medium", "high", "very_high"]
    risks: Annotated[list[RiskDraft], Field(max_length=30)] = []
    mvp_boundary: Annotated[list[Text], Field(min_length=1, max_length=30)]
    excluded_scope: Annotated[list[Text], Field(max_length=30)] = []

    @model_validator(mode="after")
    def unique_module_names_and_objectives(self) -> Self:
        names = [item.name.casefold() for item in self.modules]
        objectives = [" ".join(item.objective.casefold().split()) for item in self.modules]
        if len(names) != len(set(names)):
            raise ValueError("Module names must be unique.")
        if len(objectives) != len(set(objectives)):
            raise ValueError("Module objectives must be unique.")
        return self


class ModuleDraftBatch(StrictModel):
    items: Annotated[list[ModuleDraft], Field(min_length=1, max_length=20)]


class MilestoneDraftBatch(StrictModel):
    items: Annotated[list[MilestoneDraft], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_sequences(self) -> Self:
        sequences = [item.sequence for item in self.items]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Milestone sequence values must be unique.")
        return self


class TaskDraftBatch(StrictModel):
    items: Annotated[list[TaskDraft], Field(min_length=1, max_length=100)]


class DependencySuggestionBatch(StrictModel):
    items: Annotated[list[DependencySuggestion], Field(max_length=300)]


class RiskDraftBatch(StrictModel):
    items: Annotated[list[RiskDraft], Field(max_length=100)]


class ClarificationQuestionBatch(StrictModel):
    items: Annotated[list[ClarificationQuestion], Field(max_length=30)]


class RecommendationDraftBatch(StrictModel):
    items: Annotated[list[RecommendationDraft], Field(max_length=30)]
