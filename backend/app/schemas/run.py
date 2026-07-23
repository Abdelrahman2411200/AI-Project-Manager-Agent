"""API contracts for persistent planning runs and clarification resume."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanningRunRequest(BaseModel):
    token_budget: int = Field(default=50_000, ge=1_000, le=200_000)


class AgentRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    workflow: str
    status: str
    current_step: str
    token_budget: int
    tokens_used: int
    cancel_requested: bool
    proposed_plan_version_id: UUID | None
    outcome: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AgentRunStepView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mode: str
    purpose: str
    attempt: int
    status: str
    input_refs: list[dict[str, Any]]
    output_refs: list[dict[str, Any]]
    validation: list[dict[str, Any]]
    usage: dict[str, Any]
    failure_code: str | None
    retryable: bool
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class ClarificationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    stable_key: str
    question: str
    reason: str
    affects: list[str]
    required: bool
    answer_type: str
    options: list[str]
    default_assumption: str | None
    source_fact_refs: list[str]
    answer_json: Any | None
    status: str
    created_at: datetime
    updated_at: datetime


class ClarificationAnswer(BaseModel):
    question_id: UUID
    answer: Any


class ClarificationAnswerRequest(BaseModel):
    run_id: UUID
    answers: list[ClarificationAnswer] = Field(min_length=1, max_length=30)


class ClarificationResumeView(BaseModel):
    run: AgentRunView
    questions: list[ClarificationView]
    resumed: bool
