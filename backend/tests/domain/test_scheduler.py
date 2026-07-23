import time
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.calendar import WorkCalendar
from app.domain.graph import DependencyEdge
from app.domain.scheduler import ScheduleTask, schedule_tasks

VERSION = UUID(int=21)


def calendar(*, team_parallelism: int = 1) -> WorkCalendar:
    return WorkCalendar(
        timezone="Africa/Cairo",
        weekday_hours={weekday: Decimal(8) for weekday in range(5)},
        parallel_limit=team_parallelism,
    )


def item(
    number: int,
    *,
    effort: Decimal = Decimal(8),
    priority: Decimal = Decimal(50),
    version: UUID = VERSION,
) -> ScheduleTask:
    return ScheduleTask(
        id=UUID(int=2000 + number),
        stable_key=f"TASK-{number:04d}",
        version_id=version,
        likely_effort_hours=effort,
        priority_score=priority,
        workstreams=("backend",),
    )


def dependency(predecessor: int, successor: int) -> DependencyEdge:
    return DependencyEdge(
        predecessor_id=item(predecessor).id,
        successor_id=item(successor).id,
        version_id=VERSION,
    )


def test_scheduler_respects_priority_capacity_dependencies_buffer_and_deadline() -> None:
    tasks = [
        item(1, priority=Decimal(80)),
        item(2, effort=Decimal(4), priority=Decimal(90)),
        item(3, priority=Decimal(100)),
    ]
    result = schedule_tasks(
        tasks,
        [dependency(1, 3)],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(),
        team_size=1,
        deadline=date(2026, 7, 27),
    )

    assert result.placement_order == (item(2).id, item(1).id, item(3).id)
    assert result.tasks[item(2).id].start_date == date(2026, 7, 23)
    assert result.tasks[item(1).id].start_date == date(2026, 7, 24)
    assert result.tasks[item(3).id].start_date == date(2026, 7, 27)
    assert result.project_finish == date(2026, 7, 27)
    assert result.buffer_working_days == 1
    assert result.forecast_finish == date(2026, 7, 28)
    assert result.deadline_feasible is False
    assert result.shortfall_working_days == 1
    assert result.blocking_path == ("TASK-0001", "TASK-0003")
    assert result.warnings[0].code == "DEADLINE_INFEASIBLE"


def test_parallel_limit_and_team_capacity_are_applied_deterministically() -> None:
    tasks = [
        item(1, effort=Decimal(6), priority=Decimal(90)),
        item(2, effort=Decimal(6), priority=Decimal(80)),
    ]
    result = schedule_tasks(
        tasks,
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(team_parallelism=2),
        team_size=2,
        buffer_ratio=Decimal(0),
    )

    assert result.tasks[item(1).id].start_date == date(2026, 7, 23)
    assert result.tasks[item(2).id].start_date == date(2026, 7, 23)
    assert sum(
        allocation.hours
        for scheduled in result.tasks.values()
        for allocation in scheduled.allocations
        if allocation.day == date(2026, 7, 23)
    ) == Decimal("12.00")
    assert result == schedule_tasks(
        list(reversed(tasks)),
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(team_parallelism=2),
        team_size=2,
        buffer_ratio=Decimal(0),
    )

    capacity_bound = schedule_tasks(
        [item(1, priority=Decimal(90)), item(2, priority=Decimal(80)), item(3)],
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(team_parallelism=3),
        team_size=2,
        buffer_ratio=Decimal(0),
    )
    assert capacity_bound.tasks[item(3).id].start_date == date(2026, 7, 24)


def test_effort_can_span_multiple_working_days_and_feasible_deadline_has_no_warning() -> None:
    result = schedule_tasks(
        [item(1, effort=Decimal(20))],
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(),
        team_size=1,
        deadline=date(2026, 8, 1),
        buffer_ratio=Decimal(0),
    )
    assert len(result.tasks[item(1).id].allocations) == 3
    assert [allocation.hours for allocation in result.tasks[item(1).id].allocations] == [
        Decimal("8.00"),
        Decimal("8.00"),
        Decimal("4.00"),
    ]
    assert result.project_finish == date(2026, 7, 27)
    assert result.deadline_feasible is True
    assert result.warnings == ()


def test_empty_plan_and_missing_capacity_return_typed_results() -> None:
    empty = schedule_tasks(
        [],
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(),
        team_size=1,
        deadline=date(2026, 8, 1),
    )
    assert empty.tasks == {}
    assert empty.deadline_feasible is True

    infeasible = schedule_tasks(
        [item(1)],
        [],
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=WorkCalendar(timezone="Africa/Cairo", weekday_hours={}),
        team_size=1,
    )
    assert infeasible.tasks == {}
    assert infeasible.deadline_feasible is False
    assert infeasible.warnings[0].code == "NO_WORKING_CAPACITY"
    assert infeasible.blocking_path == ("TASK-0001",)


@pytest.mark.parametrize(
    ("tasks", "team_size", "buffer_ratio", "message"),
    [
        ([item(1)], 0, Decimal("0.1"), "Team size"),
        ([item(1)], 1, Decimal("-0.1"), "Buffer ratio"),
        ([item(1, effort=Decimal(0))], 1, Decimal("0.1"), "positive effort"),
        ([item(1, priority=Decimal(101))], 1, Decimal("0.1"), "priority"),
        ([item(1, version=UUID(int=999))], 1, Decimal("0.1"), "another version"),
        ([item(1), item(1)], 1, Decimal("0.1"), "Duplicate"),
    ],
)
def test_scheduler_rejects_invalid_inputs(
    tasks: list[ScheduleTask],
    team_size: int,
    buffer_ratio: Decimal,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        schedule_tasks(
            tasks,
            [],
            version_id=VERSION,
            project_start=date(2026, 7, 23),
            calendar=calendar(),
            team_size=team_size,
            buffer_ratio=buffer_ratio,
        )


def test_thousand_task_three_thousand_edge_benchmark_is_under_two_seconds() -> None:
    tasks = [
        item(number, effort=Decimal("0.5"), priority=Decimal(number % 101))
        for number in range(1, 1001)
    ]
    edges: list[DependencyEdge] = []
    seen: set[tuple[int, int]] = set()
    for successor in range(2, 1001):
        for distance in (1, 7, 31):
            predecessor = successor - distance
            if predecessor >= 1 and (predecessor, successor) not in seen:
                seen.add((predecessor, successor))
                edges.append(dependency(predecessor, successor))

    started = time.perf_counter()
    result = schedule_tasks(
        tasks,
        edges,
        version_id=VERSION,
        project_start=date(2026, 7, 23),
        calendar=calendar(team_parallelism=8),
        team_size=8,
        buffer_ratio=Decimal(0),
    )
    duration = time.perf_counter() - started

    assert len(edges) >= 2900
    assert len(result.tasks) == 1000
    assert duration < 2.0
