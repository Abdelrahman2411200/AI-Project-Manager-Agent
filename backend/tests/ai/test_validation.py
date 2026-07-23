import asyncio
from copy import deepcopy

from pydantic import BaseModel

from app.ai.schemas.outputs import (
    ModuleDraftBatch,
    RecommendationDraftBatch,
    TaskDraftBatch,
)
from app.ai.validation import (
    ValidationContext,
    ValidationIssue,
    ValidationStage,
    validate_candidate,
    validate_with_repair,
)
from tests.ai.fixtures import MODULE, RECOMMENDATION, TASK


def test_validation_ladder_accepts_supplied_and_generated_references() -> None:
    result = validate_candidate(
        {"items": [MODULE]},
        ModuleDraftBatch,
        ValidationContext(allowed_refs=frozenset({"REQ-001"})),
    )
    assert result.is_valid
    assert result.candidate is not None


def test_unknown_reference_fails_identifier_stage() -> None:
    result = validate_candidate(
        {"items": [MODULE]},
        ModuleDraftBatch,
        ValidationContext(),
    )
    assert not result.is_valid
    assert {issue.code for issue in result.issues} == {"identifier.unknown_reference"}


def test_duplicate_temporary_reference_fails_closed() -> None:
    duplicate = deepcopy(MODULE)
    duplicate["name"] = "Second module"
    duplicate["objective"] = "Cover a different project objective."
    result = validate_candidate(
        {"items": [MODULE, duplicate]},
        ModuleDraftBatch,
        ValidationContext(allowed_refs=frozenset({"REQ-001"})),
    )
    assert any(issue.code == "identifier.duplicate_temp_id" for issue in result.issues)


def test_locked_user_edited_item_is_protected_from_regeneration() -> None:
    result = validate_candidate(
        {"items": [MODULE]},
        ModuleDraftBatch,
        ValidationContext(
            allowed_refs=frozenset({"REQ-001"}),
            protected_refs=frozenset({"MOD-001"}),
        ),
    )
    assert any(issue.stage == ValidationStage.PERMISSION for issue in result.issues)


def test_leaf_task_size_is_enforced_by_business_validation() -> None:
    oversized = {**TASK, "effort_likely_hours": 40, "effort_max_hours": 50}
    result = validate_candidate(
        {"items": [oversized]},
        TaskDraftBatch,
        ValidationContext(allowed_refs=frozenset({"MS-001", "REQ-001"})),
    )
    assert any(issue.code == "business.leaf_task_size" for issue in result.issues)


def test_unsupported_report_fact_is_rejected() -> None:
    unsupported = deepcopy(RECOMMENDATION)
    unsupported["expected_impact"] = "Moves delivery to 2026-09-01."
    result = validate_candidate(
        {"items": [unsupported]},
        RecommendationDraftBatch,
        ValidationContext(
            allowed_refs=frozenset({"TASK-001", "DEP-001", "FORECAST-LATEST"}),
        ),
    )
    assert any(issue.code == "business.unsupported_fact_token" for issue in result.issues)


def test_deterministic_check_runs_after_other_layers() -> None:
    def reject(_: BaseModel) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                ValidationStage.DETERMINISTIC,
                "deterministic.graph_cycle",
                "$.items",
                "The proposed edges contain a cycle.",
            )
        ]

    result = validate_candidate(
        {"items": [MODULE]},
        ModuleDraftBatch,
        ValidationContext(
            allowed_refs=frozenset({"REQ-001"}),
            deterministic_checks=(reject,),
        ),
    )
    assert [issue.code for issue in result.issues] == ["deterministic.graph_cycle"]


def test_one_repair_receives_only_candidate_and_machine_readable_errors() -> None:
    calls: list[tuple[dict, list[dict]]] = []

    async def repair(candidate: dict, issues: list[dict]) -> dict:
        calls.append((candidate, issues))
        return {"items": [MODULE]}

    result = asyncio.run(
        validate_with_repair(
            {"items": [{**MODULE, "temp_id": "bad"}]},
            ModuleDraftBatch,
            ValidationContext(allowed_refs=frozenset({"REQ-001"})),
            repair=repair,
        )
    )
    assert result.is_valid
    assert result.repaired
    assert len(calls) == 1
    assert calls[0][1][0]["stage"] == "schema"
    assert set(calls[0][1][0]) == {"stage", "code", "path", "message"}


def test_second_invalid_repair_is_rejected_without_another_attempt() -> None:
    calls = 0

    async def repair(_: dict, __: list[dict]) -> dict:
        nonlocal calls
        calls += 1
        return {"items": [{**MODULE, "temp_id": "still-bad"}]}

    result = asyncio.run(
        validate_with_repair(
            {"items": [{**MODULE, "temp_id": "bad"}]},
            ModuleDraftBatch,
            ValidationContext(allowed_refs=frozenset({"REQ-001"})),
            repair=repair,
        )
    )
    assert not result.is_valid
    assert result.candidate is None
    assert result.repaired
    assert calls == 1
