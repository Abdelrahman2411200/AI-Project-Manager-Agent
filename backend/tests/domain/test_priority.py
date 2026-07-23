from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.graph import DependencyEdge, GraphTask, validate_graph
from app.domain.priority import (
    PriorityBreakdown,
    PriorityFactors,
    PriorityResult,
    critical_saturation_warning,
    dependency_centrality,
    priority_label,
    score_priorities,
    urgency_from_slack,
)

VERSION = UUID(int=11)


def graph_for(count: int, edges: tuple[tuple[int, int], ...] = ()):
    tasks = tuple(
        GraphTask(
            id=UUID(int=1000 + number),
            stable_key=f"TASK-{number:03d}",
            version_id=VERSION,
        )
        for number in range(1, count + 1)
    )
    dependencies = tuple(
        DependencyEdge(
            predecessor_id=tasks[predecessor - 1].id,
            successor_id=tasks[successor - 1].id,
            version_id=VERSION,
        )
        for predecessor, successor in edges
    )
    return tasks, validate_graph(tasks, dependencies, VERSION)


@pytest.mark.parametrize(
    ("slack", "expected"),
    [
        (-1, Decimal(100)),
        (0, Decimal(100)),
        (1, Decimal(80)),
        (2, Decimal(80)),
        (3, Decimal(60)),
        (5, Decimal(60)),
        (6, Decimal(40)),
        (10, Decimal(40)),
        (11, Decimal(20)),
    ],
)
def test_urgency_piecewise_boundaries(slack: int, expected: Decimal) -> None:
    assert urgency_from_slack(slack) == expected


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (Decimal("0"), "Low"),
        (Decimal("39.99"), "Low"),
        (Decimal("40"), "Medium"),
        (Decimal("64.99"), "Medium"),
        (Decimal("65"), "High"),
        (Decimal("84.99"), "High"),
        (Decimal("85"), "Critical"),
        (Decimal("100"), "Critical"),
    ],
)
def test_priority_label_boundaries(score: Decimal, label: str) -> None:
    assert priority_label(score) == label


@pytest.mark.parametrize("score", [Decimal("-0.01"), Decimal("100.01")])
def test_priority_label_rejects_out_of_range_score(score: Decimal) -> None:
    with pytest.raises(ValueError):
        priority_label(score)


def test_priority_score_has_auditable_factor_breakdown() -> None:
    tasks, graph = graph_for(2, ((1, 2),))
    factors = {
        tasks[0].id: PriorityFactors(
            mvp_necessity=Decimal(100),
            deadline_urgency=Decimal(80),
            user_value=Decimal(60),
            risk_reduction=Decimal(40),
            user_preference=Decimal(20),
        ),
        tasks[1].id: PriorityFactors(
            mvp_necessity=Decimal(50),
            deadline_urgency=Decimal(20),
            user_value=Decimal(50),
            risk_reduction=Decimal(50),
            user_preference=Decimal(50),
        ),
    }

    batch = score_priorities(factors, graph)
    first = batch.results[0]
    assert first.breakdown.dependency_centrality == Decimal("100.00")
    assert first.score == Decimal("80.00")
    assert first.label == "High"
    assert dependency_centrality(tasks[1].id, graph) == Decimal("0.00")
    assert batch == score_priorities(factors, graph)


def test_critical_saturation_check_does_not_change_calculated_scores() -> None:
    tasks, graph = graph_for(4, ((1, 2), (2, 3), (3, 4)))
    factors = {
        task.id: PriorityFactors(
            mvp_necessity=Decimal(100),
            deadline_urgency=Decimal(100),
            user_value=Decimal(100),
            risk_reduction=Decimal(100),
            user_preference=Decimal(100),
        )
        for task in tasks
    }

    batch = score_priorities(factors, graph)
    assert batch.results[0].score == Decimal("100.00")
    assert "CRITICAL_PRIORITY_SATURATION" not in batch.warning_codes

    unjustified = PriorityResult(
        task_id=UUID(int=999),
        score=Decimal(90),
        label="Critical",
        breakdown=PriorityBreakdown(
            mvp_necessity=Decimal(100),
            dependency_centrality=Decimal(10),
            deadline_urgency=Decimal(0),
            user_value=Decimal(100),
            risk_reduction=Decimal(100),
            user_preference=Decimal(100),
        ),
    )
    low = PriorityResult(
        task_id=UUID(int=998),
        score=Decimal(10),
        label="Low",
        breakdown=PriorityBreakdown(
            mvp_necessity=Decimal(0),
            dependency_centrality=Decimal(0),
            deadline_urgency=Decimal(0),
            user_value=Decimal(0),
            risk_reduction=Decimal(0),
            user_preference=Decimal(0),
        ),
    )
    assert critical_saturation_warning((unjustified, low, low)) is True


def test_priority_factor_task_sets_and_ranges_are_validated() -> None:
    tasks, graph = graph_for(1)
    with pytest.raises(ValueError, match="must match"):
        score_priorities({}, graph)
    with pytest.raises(ValueError, match="between 0 and 100"):
        score_priorities(
            {
                tasks[0].id: PriorityFactors(
                    mvp_necessity=Decimal(101),
                    deadline_urgency=Decimal(0),
                    user_value=Decimal(0),
                    risk_reduction=Decimal(0),
                    user_preference=Decimal(0),
                )
            },
            graph,
        )
    with pytest.raises(ValueError, match="not present"):
        dependency_centrality(UUID(int=9999), graph)
