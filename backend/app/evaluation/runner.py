"""Score fixed MVP fixtures without network or model-dependent judgment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    fixture_id: str
    module_coverage: float
    missing_task_rate: float
    task_size_compliance: float
    dependency_validity: float
    hallucination_rate: float
    schedule_match: bool
    passed: bool


def _coverage(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    normalized = {item.casefold() for item in actual}
    return sum(item.casefold() in normalized for item in expected) / len(expected)


def evaluate_fixture(fixture: dict[str, Any]) -> EvaluationResult:
    module_coverage = _coverage(
        fixture["expected_module_concepts"],
        fixture["candidate_module_concepts"],
    )
    task_coverage = _coverage(
        fixture["required_task_concepts"],
        fixture["candidate_task_concepts"],
    )
    efforts = fixture["leaf_effort_hours"]
    task_size_compliance = (
        sum(4 <= effort <= 24 for effort in efforts) / len(efforts) if efforts else 1.0
    )
    proposed_edges = fixture["proposed_dependency_count"]
    dependency_validity = (
        fixture["valid_dependency_count"] / proposed_edges if proposed_edges else 1.0
    )
    claims = fixture["candidate_claims"]
    forbidden = {item.casefold() for item in fixture["forbidden_claims"]}
    unsupported = sum(claim.casefold() in forbidden for claim in claims)
    hallucination_rate = unsupported / len(claims) if claims else 0.0
    schedule_match = fixture["expected_feasible"] == fixture["calculated_feasible"]
    passed = (
        module_coverage >= 0.70
        and 1 - task_coverage <= 0.10
        and task_size_compliance >= 0.90
        and dependency_validity >= 0.98
        and hallucination_rate <= 0.01
        and schedule_match
        and not fixture["accepted_cycle"]
    )
    return EvaluationResult(
        fixture_id=fixture["fixture_id"],
        module_coverage=module_coverage,
        missing_task_rate=1 - task_coverage,
        task_size_compliance=task_size_compliance,
        dependency_validity=dependency_validity,
        hallucination_rate=hallucination_rate,
        schedule_match=schedule_match,
        passed=passed,
    )
