from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.ai.openai_provider import validate_schema_is_strict
from app.ai.schemas.outputs import (
    ClarificationQuestion,
    DependencySuggestion,
    MilestoneDraft,
    ModuleDraft,
    ProjectAnalysisOutput,
    RecommendationDraft,
    RiskDraft,
    TaskDraft,
    WeeklyReportNarrative,
)
from tests.ai.fixtures import (
    ANALYSIS,
    DEPENDENCY,
    MILESTONE,
    MODULE,
    QUESTION,
    RECOMMENDATION,
    RISK,
    TASK,
    WEEKLY_REPORT,
)

SCHEMA_EXAMPLES = (
    (ProjectAnalysisOutput, ANALYSIS),
    (ModuleDraft, MODULE),
    (MilestoneDraft, MILESTONE),
    (TaskDraft, TASK),
    (DependencySuggestion, DEPENDENCY),
    (RiskDraft, RISK),
    (ClarificationQuestion, QUESTION),
    (RecommendationDraft, RECOMMENDATION),
    (WeeklyReportNarrative, WEEKLY_REPORT),
)


@pytest.mark.parametrize(("schema", "example"), SCHEMA_EXAMPLES)
def test_required_semantic_examples_parse_and_are_strict(schema: type, example: dict) -> None:
    parsed = schema.model_validate(example)
    assert parsed.model_dump(mode="json")
    validate_schema_is_strict(schema)


@pytest.mark.parametrize(("schema", "example"), SCHEMA_EXAMPLES)
def test_required_semantic_schemas_reject_additional_fields(schema: type, example: dict) -> None:
    invalid = deepcopy(example)
    invalid["ignore_previous_instructions"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        schema.model_validate(invalid)


def test_bad_temporary_identifier_is_rejected() -> None:
    invalid = {**TASK, "temp_id": "task-1"}
    with pytest.raises(ValidationError, match="String should match pattern"):
        TaskDraft.model_validate(invalid)


def test_task_estimate_order_is_rejected() -> None:
    invalid = {**TASK, "effort_min_hours": 20, "effort_likely_hours": 12}
    with pytest.raises(ValidationError, match="min <= likely <= max"):
        TaskDraft.model_validate(invalid)


def test_dependency_self_edge_is_rejected() -> None:
    invalid = {**DEPENDENCY, "successor_ref": "TASK-001"}
    with pytest.raises(ValidationError, match="endpoints must be distinct"):
        DependencySuggestion.model_validate(invalid)


def test_choice_question_requires_options() -> None:
    invalid = {**QUESTION, "options": ["Only one"]}
    with pytest.raises(ValidationError, match="between two and six options"):
        ClarificationQuestion.model_validate(invalid)


def test_analysis_rejects_duplicate_normalized_module_objectives() -> None:
    duplicate = deepcopy(MODULE)
    duplicate["temp_id"] = "MOD-002"
    duplicate["name"] = "Checkout"
    invalid = deepcopy(ANALYSIS)
    invalid["modules"].append(duplicate)
    with pytest.raises(ValidationError, match="objectives must be unique"):
        ProjectAnalysisOutput.model_validate(invalid)
