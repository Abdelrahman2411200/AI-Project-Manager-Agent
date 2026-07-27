"""Capacity-aware deterministic forecast helpers for full-version scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Literal
from uuid import UUID

from app.domain.graph import DependencyEdge, GraphTask, validate_graph

CALCULATION_VERSION = "advanced-schedule-v1"


@dataclass(frozen=True, slots=True)
class CapacityForecast:
    total_effort_hours: Decimal
    capacity_hours_per_week: Decimal
    forecast_weeks: Decimal
    forecast_finish: date
    deadline_delta_days: int | None
    feasible: bool | None
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True, slots=True)
class AdvancedScheduleTask:
    id: UUID
    stable_key: str
    version_id: UUID
    effort_min_hours: Decimal
    effort_likely_hours: Decimal
    effort_max_hours: Decimal
    workstreams: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdvancedScheduledTask:
    stable_key: str
    start_week: Decimal
    finish_week: Decimal
    duration_weeks: Decimal
    workstreams: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdvancedScheduleRange:
    scenario: Literal["optimistic", "likely", "pessimistic"]
    tasks: dict[UUID, AdvancedScheduledTask]
    finish_week: Decimal
    calculation_version: str = CALCULATION_VERSION


def schedule_capacity_ranges(
    tasks: list[AdvancedScheduleTask] | tuple[AdvancedScheduleTask, ...],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    *,
    version_id: UUID,
    workstream_capacity_hours_per_week: dict[str, Decimal],
    workstream_parallel_limit: dict[str, int] | None = None,
) -> dict[str, AdvancedScheduleRange]:
    """List-schedule optimistic/likely/pessimistic ranges over workstream slots."""
    limits = workstream_parallel_limit or {}
    for name, capacity in workstream_capacity_hours_per_week.items():
        if not name.strip() or capacity <= 0:
            raise ValueError("Every workstream capacity must have a name and be positive.")
        if limits.get(name, 1) < 1:
            raise ValueError("Every workstream parallel limit must be at least one.")
    task_by_id = {task.id: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("Advanced schedule tasks must have unique IDs.")
    for task in tasks:
        if task.version_id != version_id:
            raise ValueError(f"Task {task.stable_key} belongs to another version.")
        if (
            task.effort_min_hours <= 0
            or not task.effort_min_hours <= task.effort_likely_hours <= task.effort_max_hours
        ):
            raise ValueError(f"Task {task.stable_key} has an invalid effort range.")
        missing = set(task.workstreams) - workstream_capacity_hours_per_week.keys()
        if not task.workstreams or missing:
            raise ValueError(
                f"Task {task.stable_key} has missing workstream capacity: "
                + ", ".join(sorted(missing))
            )
    graph = validate_graph(
        [GraphTask(task.id, task.stable_key, task.version_id) for task in tasks],
        edges,
        version_id,
    )
    return {
        scenario: _schedule_range(
            task_by_id,
            graph.topological_order,
            graph.predecessors,
            workstream_capacity_hours_per_week,
            limits,
            scenario,
        )
        for scenario in ("optimistic", "likely", "pessimistic")
    }


def _schedule_range(
    task_by_id: dict[UUID, AdvancedScheduleTask],
    order: tuple[UUID, ...],
    predecessors: dict[UUID, frozenset[UUID]],
    capacities: dict[str, Decimal],
    limits: dict[str, int],
    scenario: Literal["optimistic", "likely", "pessimistic"],
) -> AdvancedScheduleRange:
    slots = {name: [Decimal(0) for _ in range(limits.get(name, 1))] for name in capacities}
    scheduled: dict[UUID, AdvancedScheduledTask] = {}
    for task_id in order:
        task = task_by_id[task_id]
        effort = {
            "optimistic": task.effort_min_hours,
            "likely": task.effort_likely_hours,
            "pessimistic": task.effort_max_hours,
        }[scenario]
        capacity = min(capacities[name] for name in task.workstreams)
        duration = (effort / capacity).quantize(Decimal("0.0001"))
        dependency_ready = max(
            (scheduled[item].finish_week for item in predecessors[task_id]),
            default=Decimal(0),
        )
        selected_slots = {
            name: min(range(len(slots[name])), key=lambda index: slots[name][index])
            for name in task.workstreams
        }
        resource_ready = max(
            (slots[name][index] for name, index in selected_slots.items()),
            default=Decimal(0),
        )
        start = max(dependency_ready, resource_ready)
        finish = start + duration
        for name, index in selected_slots.items():
            slots[name][index] = finish
        scheduled[task_id] = AdvancedScheduledTask(
            stable_key=task.stable_key,
            start_week=start,
            finish_week=finish,
            duration_weeks=duration,
            workstreams=task.workstreams,
        )
    return AdvancedScheduleRange(
        scenario=scenario,
        tasks=scheduled,
        finish_week=max(
            (task.finish_week for task in scheduled.values()),
            default=Decimal(0),
        ),
    )


def capacity_forecast(
    *,
    total_effort_hours: Decimal,
    capacity_hours_per_week: Decimal,
    start_date: date,
    deadline: date | None,
) -> CapacityForecast:
    if total_effort_hours < 0:
        raise ValueError("Total effort cannot be negative.")
    if capacity_hours_per_week <= 0:
        raise ValueError("Capacity must be positive.")
    weeks = total_effort_hours / capacity_hours_per_week
    calendar_days = int((weeks * Decimal(7)).to_integral_value(rounding=ROUND_CEILING))
    finish = start_date + timedelta(days=max(0, calendar_days))
    delta = None if deadline is None else (finish - deadline).days
    return CapacityForecast(
        total_effort_hours=total_effort_hours,
        capacity_hours_per_week=capacity_hours_per_week,
        forecast_weeks=weeks.quantize(Decimal("0.01")),
        forecast_finish=finish,
        deadline_delta_days=delta,
        feasible=None if delta is None else delta <= 0,
    )
