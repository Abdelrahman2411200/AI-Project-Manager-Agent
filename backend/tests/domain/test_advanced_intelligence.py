from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.advanced_schedule import (
    AdvancedScheduleTask,
    capacity_forecast,
    schedule_capacity_ranges,
)
from app.domain.critical_path import CriticalPathTask, calculate_critical_path
from app.domain.graph import DependencyEdge, GraphValidationError


def test_critical_path_calculates_forward_backward_pass_and_slack() -> None:
    version_id = uuid4()
    first, second, parallel, final = [uuid4() for _ in range(4)]
    result = calculate_critical_path(
        [
            CriticalPathTask(first, "TASK-001", version_id, Decimal("8")),
            CriticalPathTask(second, "TASK-002", version_id, Decimal("12")),
            CriticalPathTask(parallel, "TASK-003", version_id, Decimal("4")),
            CriticalPathTask(final, "TASK-004", version_id, Decimal("6")),
        ],
        [
            DependencyEdge(first, second, version_id),
            DependencyEdge(first, parallel, version_id),
            DependencyEdge(second, final, version_id),
            DependencyEdge(parallel, final, version_id),
        ],
        version_id,
    )

    assert result.duration_hours == Decimal("26")
    assert result.critical_keys == ("TASK-001", "TASK-002", "TASK-004")
    assert result.nodes[parallel].slack_hours == Decimal("8")
    assert result.nodes[parallel].critical is False


def test_critical_path_rejects_cycle_and_cross_version_input() -> None:
    version_id = uuid4()
    one, two = uuid4(), uuid4()
    tasks = [
        CriticalPathTask(one, "TASK-001", version_id, Decimal("1")),
        CriticalPathTask(two, "TASK-002", version_id, Decimal("1")),
    ]
    with pytest.raises(GraphValidationError, match="cycle"):
        calculate_critical_path(
            tasks,
            [
                DependencyEdge(one, two, version_id),
                DependencyEdge(two, one, version_id),
            ],
            version_id,
        )
    with pytest.raises(ValueError, match="another version"):
        calculate_critical_path(
            [CriticalPathTask(one, "TASK-001", uuid4(), Decimal("1"))],
            [],
            version_id,
        )


def test_capacity_forecast_is_deterministic_and_reports_deadline_delta() -> None:
    result = capacity_forecast(
        total_effort_hours=Decimal("60"),
        capacity_hours_per_week=Decimal("30"),
        start_date=date(2026, 7, 1),
        deadline=date(2026, 7, 12),
    )

    assert result.forecast_weeks == Decimal("2.00")
    assert result.forecast_finish == date(2026, 7, 15)
    assert result.deadline_delta_days == 3
    assert result.feasible is False


def test_critical_path_handles_one_thousand_nodes() -> None:
    version_id = uuid4()
    ids = [uuid4() for _ in range(1000)]
    tasks = [
        CriticalPathTask(task_id, f"TASK-{index + 1:03d}", version_id, Decimal("1"))
        for index, task_id in enumerate(ids)
    ]
    edges = [
        DependencyEdge(ids[index], ids[index + 1], version_id) for index in range(len(ids) - 1)
    ]

    result = calculate_critical_path(tasks, edges, version_id)

    assert result.duration_hours == Decimal("1000")
    assert len(result.critical_keys) == 1000


def test_advanced_schedule_respects_dependency_workstream_slots_and_ranges() -> None:
    version_id = uuid4()
    first, parallel, final = uuid4(), uuid4(), uuid4()
    result = schedule_capacity_ranges(
        [
            AdvancedScheduleTask(
                first,
                "TASK-001",
                version_id,
                Decimal("10"),
                Decimal("20"),
                Decimal("30"),
                ("backend",),
            ),
            AdvancedScheduleTask(
                parallel,
                "TASK-002",
                version_id,
                Decimal("10"),
                Decimal("20"),
                Decimal("30"),
                ("backend",),
            ),
            AdvancedScheduleTask(
                final,
                "TASK-003",
                version_id,
                Decimal("5"),
                Decimal("10"),
                Decimal("15"),
                ("frontend",),
            ),
        ],
        [
            DependencyEdge(first, final, version_id),
            DependencyEdge(parallel, final, version_id),
        ],
        version_id=version_id,
        workstream_capacity_hours_per_week={
            "backend": Decimal("20"),
            "frontend": Decimal("10"),
        },
        workstream_parallel_limit={"backend": 1, "frontend": 1},
    )

    assert result["likely"].tasks[parallel].start_week == Decimal("1.0000")
    assert result["likely"].tasks[final].start_week == Decimal("2.0000")
    assert result["optimistic"].finish_week < result["likely"].finish_week
    assert result["likely"].finish_week < result["pessimistic"].finish_week
