from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from app.domain.graph import GraphResult

PriorityLabel = Literal["Critical", "High", "Medium", "Low"]
CALCULATION_VERSION = "priority-v1"


@dataclass(frozen=True, slots=True)
class PriorityFactors:
    mvp_necessity: Decimal
    deadline_urgency: Decimal
    user_value: Decimal
    risk_reduction: Decimal
    user_preference: Decimal


@dataclass(frozen=True, slots=True)
class PriorityBreakdown:
    mvp_necessity: Decimal
    dependency_centrality: Decimal
    deadline_urgency: Decimal
    user_value: Decimal
    risk_reduction: Decimal
    user_preference: Decimal


@dataclass(frozen=True, slots=True)
class PriorityResult:
    task_id: UUID
    score: Decimal
    label: PriorityLabel
    breakdown: PriorityBreakdown
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True, slots=True)
class PriorityBatch:
    results: tuple[PriorityResult, ...]
    warning_codes: tuple[str, ...]
    calculation_version: str = CALCULATION_VERSION


def urgency_from_slack(slack_working_days: int | Decimal) -> Decimal:
    slack = Decimal(slack_working_days)
    if slack <= 0:
        return Decimal(100)
    if slack <= 2:
        return Decimal(80)
    if slack <= 5:
        return Decimal(60)
    if slack <= 10:
        return Decimal(40)
    return Decimal(20)


def dependency_centrality(
    task_id: UUID,
    graph: GraphResult,
) -> Decimal:
    if task_id not in graph.downstream:
        raise ValueError(f"Task {task_id} is not present in the validated graph.")
    denominator = max(1, len(graph.topological_order) - 1)
    value = Decimal(100) * Decimal(len(graph.downstream[task_id])) / Decimal(denominator)
    return _round(value)


def score_priorities(
    factors_by_task: dict[UUID, PriorityFactors],
    graph: GraphResult,
    *,
    high_centrality_threshold: Decimal = Decimal(65),
) -> PriorityBatch:
    if set(factors_by_task) != set(graph.topological_order):
        missing = set(graph.topological_order) - set(factors_by_task)
        extra = set(factors_by_task) - set(graph.topological_order)
        raise ValueError(
            f"Priority factors must match graph tasks; missing={missing}, extra={extra}."
        )

    results: list[PriorityResult] = []
    for task_id in graph.topological_order:
        factors = factors_by_task[task_id]
        _validate_factors(factors)
        centrality = dependency_centrality(task_id, graph)
        breakdown = PriorityBreakdown(
            mvp_necessity=_round(factors.mvp_necessity),
            dependency_centrality=centrality,
            deadline_urgency=_round(factors.deadline_urgency),
            user_value=_round(factors.user_value),
            risk_reduction=_round(factors.risk_reduction),
            user_preference=_round(factors.user_preference),
        )
        score = _round(
            Decimal("0.30") * breakdown.mvp_necessity
            + Decimal("0.20") * breakdown.dependency_centrality
            + Decimal("0.20") * breakdown.deadline_urgency
            + Decimal("0.15") * breakdown.user_value
            + Decimal("0.10") * breakdown.risk_reduction
            + Decimal("0.05") * breakdown.user_preference
        )
        results.append(
            PriorityResult(
                task_id=task_id,
                score=score,
                label=priority_label(score),
                breakdown=breakdown,
            )
        )

    saturated = critical_saturation_warning(
        tuple(results),
        high_centrality_threshold=high_centrality_threshold,
    )
    warnings = ("CRITICAL_PRIORITY_SATURATION",) if saturated else ()
    return PriorityBatch(results=tuple(results), warning_codes=warnings)


def critical_saturation_warning(
    results: tuple[PriorityResult, ...],
    *,
    high_centrality_threshold: Decimal = Decimal(65),
) -> bool:
    critical = [result for result in results if result.label == "Critical"]
    return (
        bool(results)
        and Decimal(len(critical)) / Decimal(len(results)) > Decimal("0.25")
        and any(
            result.breakdown.deadline_urgency == 0
            and result.breakdown.dependency_centrality < high_centrality_threshold
            for result in critical
        )
    )


def _validate_factors(factors: PriorityFactors) -> None:
    for name, value in (
        ("mvp_necessity", factors.mvp_necessity),
        ("deadline_urgency", factors.deadline_urgency),
        ("user_value", factors.user_value),
        ("risk_reduction", factors.risk_reduction),
        ("user_preference", factors.user_preference),
    ):
        if value < 0 or value > 100:
            raise ValueError(f"{name} must be between 0 and 100.")


def priority_label(score: Decimal) -> PriorityLabel:
    if score < 0 or score > 100:
        raise ValueError("Priority score must be between 0 and 100.")
    if score >= 85:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
