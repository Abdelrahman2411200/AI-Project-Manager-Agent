from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from uuid import UUID

from app.domain.calendar import (
    WorkCalendar,
    add_working_days,
    count_working_days,
    next_working_day,
    working_day,
)
from app.domain.graph import DependencyEdge, GraphTask, validate_graph

CALCULATION_VERSION = "scheduler-v1"


@dataclass(frozen=True, slots=True)
class ScheduleTask:
    id: UUID
    stable_key: str
    version_id: UUID
    likely_effort_hours: Decimal
    priority_score: Decimal
    workstreams: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DailyAllocation:
    day: date
    hours: Decimal


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    task_id: UUID
    stable_key: str
    start_date: date
    finish_date: date
    allocations: tuple[DailyAllocation, ...]


@dataclass(frozen=True, slots=True)
class ScheduleWarning:
    code: str
    detail: str
    task_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    tasks: dict[UUID, ScheduledTask]
    placement_order: tuple[UUID, ...]
    project_finish: date | None
    forecast_finish: date | None
    buffer_working_days: int
    deadline_feasible: bool | None
    shortfall_working_days: int
    shortfall_hours: Decimal
    blocking_path: tuple[str, ...]
    warnings: tuple[ScheduleWarning, ...]
    calculation_version: str = CALCULATION_VERSION


def schedule_tasks(
    tasks: list[ScheduleTask] | tuple[ScheduleTask, ...],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    *,
    version_id: UUID,
    project_start: date,
    calendar: WorkCalendar,
    team_size: int,
    deadline: date | None = None,
    buffer_ratio: Decimal = Decimal("0.10"),
) -> ScheduleResult:
    if team_size < 1:
        raise ValueError("Team size must be at least 1.")
    if buffer_ratio < 0 or buffer_ratio > 1:
        raise ValueError("Buffer ratio must be between 0 and 1.")

    task_by_id: dict[UUID, ScheduleTask] = {}
    for task in tasks:
        if task.id in task_by_id:
            raise ValueError(f"Duplicate task ID: {task.id}.")
        if task.version_id != version_id:
            raise ValueError(f"Task {task.stable_key} belongs to another version.")
        if task.likely_effort_hours <= 0:
            raise ValueError(f"Task {task.stable_key} must have positive effort.")
        if task.priority_score < 0 or task.priority_score > 100:
            raise ValueError(f"Task {task.stable_key} priority must be between 0 and 100.")
        task_by_id[task.id] = task

    graph_tasks = tuple(
        GraphTask(id=task.id, stable_key=task.stable_key, version_id=task.version_id)
        for task in tasks
    )
    graph = validate_graph(graph_tasks, edges, version_id)
    if not tasks:
        return ScheduleResult(
            tasks={},
            placement_order=(),
            project_finish=None,
            forecast_finish=None,
            buffer_working_days=0,
            deadline_feasible=None if deadline is None else True,
            shortfall_working_days=0,
            shortfall_hours=Decimal(0),
            blocking_path=(),
            warnings=(),
        )

    placement_order = _priority_topological_order(task_by_id, graph.predecessors, graph.successors)
    remaining_capacity: dict[date, Decimal] = {}
    allocated_task_ids: defaultdict[date, set[UUID]] = defaultdict(set)
    scheduled: dict[UUID, ScheduledTask] = {}

    for task_id in placement_order:
        task = task_by_id[task_id]
        predecessor_finishes = [
            scheduled[predecessor_id].finish_date for predecessor_id in graph.predecessors[task_id]
        ]
        earliest = project_start
        if predecessor_finishes:
            earliest = max(predecessor_finishes) + timedelta(days=1)
        try:
            allocations = _allocate_task(
                task,
                earliest=earliest,
                calendar=calendar,
                team_size=team_size,
                remaining_capacity=remaining_capacity,
                allocated_task_ids=allocated_task_ids,
            )
        except ValueError as exc:
            return ScheduleResult(
                tasks={},
                placement_order=placement_order,
                project_finish=None,
                forecast_finish=None,
                buffer_working_days=0,
                deadline_feasible=False,
                shortfall_working_days=0,
                shortfall_hours=task.likely_effort_hours,
                blocking_path=(task.stable_key,),
                warnings=(
                    ScheduleWarning(
                        code="NO_WORKING_CAPACITY",
                        detail=str(exc),
                        task_keys=(task.stable_key,),
                    ),
                ),
            )

        scheduled[task_id] = ScheduledTask(
            task_id=task_id,
            stable_key=task.stable_key,
            start_date=allocations[0].day,
            finish_date=allocations[-1].day,
            allocations=tuple(allocations),
        )

    project_finish = max(item.finish_date for item in scheduled.values())
    first_start = min(item.start_date for item in scheduled.values())
    scheduled_working_days = count_working_days(calendar, first_start, project_finish)
    buffer_days = int(
        (Decimal(scheduled_working_days) * buffer_ratio).to_integral_value(rounding=ROUND_CEILING)
    )
    forecast_finish = add_working_days(calendar, project_finish, buffer_days)
    deadline_feasible = None if deadline is None else forecast_finish <= deadline
    shortfall_days = (
        0
        if deadline is None or forecast_finish <= deadline
        else count_working_days(
            calendar,
            deadline,
            forecast_finish,
            include_start=False,
            include_end=True,
        )
    )
    average_daily_capacity = _average_daily_capacity(
        calendar, first_start, project_finish, team_size
    )
    shortfall_hours = _round(Decimal(shortfall_days) * average_daily_capacity)
    blocking_ids = _blocking_path(scheduled, graph.predecessors, task_by_id)
    blocking_keys = tuple(task_by_id[task_id].stable_key for task_id in blocking_ids)
    warnings: list[ScheduleWarning] = []
    if deadline_feasible is False:
        warnings.append(
            ScheduleWarning(
                code="DEADLINE_INFEASIBLE",
                detail=(
                    f"Buffered forecast {forecast_finish.isoformat()} is "
                    f"{shortfall_days} working day(s) after the deadline."
                ),
                task_keys=blocking_keys,
            )
        )
    return ScheduleResult(
        tasks=scheduled,
        placement_order=placement_order,
        project_finish=project_finish,
        forecast_finish=forecast_finish,
        buffer_working_days=buffer_days,
        deadline_feasible=deadline_feasible,
        shortfall_working_days=shortfall_days,
        shortfall_hours=shortfall_hours,
        blocking_path=blocking_keys,
        warnings=tuple(warnings),
    )


def _allocate_task(
    task: ScheduleTask,
    *,
    earliest: date,
    calendar: WorkCalendar,
    team_size: int,
    remaining_capacity: dict[date, Decimal],
    allocated_task_ids: defaultdict[date, set[UUID]],
) -> list[DailyAllocation]:
    cursor = next_working_day(calendar, earliest)
    effort_remaining = task.likely_effort_hours
    allocations: list[DailyAllocation] = []
    while effort_remaining > 0:
        slot = working_day(calendar, cursor)
        if slot is None:
            cursor = next_working_day(calendar, cursor, include_day=False)
            continue
        capacity = slot.effective_hours * Decimal(team_size)
        available = remaining_capacity.setdefault(cursor, capacity)
        day_tasks = allocated_task_ids[cursor]
        if available <= 0 or (
            task.id not in day_tasks and len(day_tasks) >= calendar.parallel_limit
        ):
            cursor = next_working_day(calendar, cursor, include_day=False)
            continue
        allocated = min(effort_remaining, available)
        allocations.append(DailyAllocation(day=cursor, hours=_round(allocated)))
        effort_remaining -= allocated
        remaining_capacity[cursor] = available - allocated
        day_tasks.add(task.id)
        if effort_remaining > 0:
            cursor = next_working_day(calendar, cursor, include_day=False)
    return allocations


def _priority_topological_order(
    task_by_id: dict[UUID, ScheduleTask],
    predecessors: dict[UUID, frozenset[UUID]],
    successors: dict[UUID, frozenset[UUID]],
) -> tuple[UUID, ...]:
    indegree = {task_id: len(items) for task_id, items in predecessors.items()}
    queue = [
        (-task_by_id[task_id].priority_score, task_by_id[task_id].stable_key, task_id)
        for task_id, degree in indegree.items()
        if degree == 0
    ]
    heapq.heapify(queue)
    result: list[UUID] = []
    while queue:
        _, _, task_id = heapq.heappop(queue)
        result.append(task_id)
        for successor_id in sorted(
            successors[task_id], key=lambda item: task_by_id[item].stable_key
        ):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                successor = task_by_id[successor_id]
                heapq.heappush(
                    queue,
                    (-successor.priority_score, successor.stable_key, successor_id),
                )
    return tuple(result)


def _blocking_path(
    scheduled: dict[UUID, ScheduledTask],
    predecessors: dict[UUID, frozenset[UUID]],
    task_by_id: dict[UUID, ScheduleTask],
) -> tuple[UUID, ...]:
    terminal_id = max(
        scheduled,
        key=lambda task_id: (
            scheduled[task_id].finish_date,
            task_by_id[task_id].stable_key,
        ),
    )
    reverse_path = [terminal_id]
    cursor = terminal_id
    while predecessors[cursor]:
        cursor = max(
            predecessors[cursor],
            key=lambda task_id: (
                scheduled[task_id].finish_date,
                task_by_id[task_id].stable_key,
            ),
        )
        reverse_path.append(cursor)
    return tuple(reversed(reverse_path))


def _average_daily_capacity(
    calendar: WorkCalendar,
    start: date,
    end: date,
    team_size: int,
) -> Decimal:
    capacities: list[Decimal] = []
    cursor = start
    while cursor <= end:
        slot = working_day(calendar, cursor)
        if slot is not None:
            capacities.append(slot.effective_hours * Decimal(team_size))
        cursor += timedelta(days=1)
    if not capacities:
        return Decimal(0)
    return sum(capacities, start=Decimal(0)) / Decimal(len(capacities))


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
