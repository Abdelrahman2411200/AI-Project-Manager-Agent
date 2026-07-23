"""Pure, evidence-first monitoring detectors for active execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

MonitoringStatus = Literal[
    "pending",
    "ready",
    "in_progress",
    "blocked",
    "completed",
    "cancelled",
]
CALCULATION_VERSION = "monitoring-v1"


@dataclass(frozen=True, slots=True)
class MonitoringTask:
    id: UUID
    stable_key: str
    milestone_id: UUID
    status: MonitoringStatus
    planned_finish: date | None
    predecessor_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class MonitoringMilestone:
    id: UUID
    stable_key: str
    target_date: date | None
    incomplete_task_count: int


@dataclass(frozen=True, slots=True)
class MonitoringInputs:
    as_of: date
    tasks: tuple[MonitoringTask, ...]
    milestones: tuple[MonitoringMilestone, ...]
    graph_valid: bool
    schedule_feasible: bool | None
    remaining_buffer_days: Decimal | None
    remaining_planned_duration_days: Decimal | None
    planned_finish: date | None = None
    forecast_finish: date | None = None
    capacity_overload_ratio: Decimal = Decimal(0)
    scope_change_count: int = 0


@dataclass(frozen=True, slots=True)
class Detection:
    code: str
    severity: Literal["info", "warning", "critical"]
    references: tuple[str, ...]
    values: dict[str, str]
    calculation_version: str = CALCULATION_VERSION


def detect_conditions(inputs: MonitoringInputs) -> tuple[Detection, ...]:
    if inputs.capacity_overload_ratio < 0:
        raise ValueError("Capacity overload ratio cannot be negative.")
    if inputs.scope_change_count < 0:
        raise ValueError("Scope change count cannot be negative.")
    if inputs.remaining_buffer_days is not None and inputs.remaining_buffer_days < 0:
        raise ValueError("Remaining buffer cannot be negative.")
    if (
        inputs.remaining_planned_duration_days is not None
        and inputs.remaining_planned_duration_days < 0
    ):
        raise ValueError("Remaining planned duration cannot be negative.")

    task_by_id = {task.id: task for task in inputs.tasks}
    if len(task_by_id) != len(inputs.tasks):
        raise ValueError("Monitoring task IDs must be unique.")
    detections: list[Detection] = []

    if not inputs.graph_valid:
        detections.append(_detection("INCONSISTENT_STATE", "critical"))

    blocked = tuple(task.stable_key for task in inputs.tasks if task.status == "blocked")
    if blocked:
        detections.append(
            _detection(
                "BLOCKED_TASKS",
                "warning",
                references=blocked,
                blocked_count=str(len(blocked)),
            )
        )

    overdue = tuple(
        task.stable_key
        for task in inputs.tasks
        if task.status not in {"completed", "cancelled"}
        and task.planned_finish is not None
        and task.planned_finish < inputs.as_of
    )
    if overdue:
        detections.append(
            _detection(
                "OVERDUE_TASKS",
                "warning",
                references=overdue,
                overdue_count=str(len(overdue)),
                as_of=inputs.as_of.isoformat(),
            )
        )

    unmet: list[str] = []
    for task in inputs.tasks:
        if task.status not in {"ready", "in_progress"}:
            continue
        incomplete = [
            task_by_id[item].stable_key if item in task_by_id else str(item)
            for item in task.predecessor_ids
            if item not in task_by_id or task_by_id[item].status != "completed"
        ]
        if incomplete:
            unmet.extend((task.stable_key, *incomplete))
    if unmet:
        detections.append(
            _detection(
                "UNMET_DEPENDENCY",
                "critical",
                references=tuple(dict.fromkeys(unmet)),
            )
        )

    delayed_milestones = tuple(
        milestone.stable_key
        for milestone in inputs.milestones
        if milestone.target_date is not None
        and milestone.target_date < inputs.as_of
        and milestone.incomplete_task_count > 0
    )
    if delayed_milestones:
        detections.append(
            _detection(
                "DELAYED_MILESTONE",
                "critical",
                references=delayed_milestones,
                as_of=inputs.as_of.isoformat(),
            )
        )

    if (
        inputs.planned_finish is not None
        and inputs.forecast_finish is not None
        and inputs.forecast_finish > inputs.planned_finish
    ):
        detections.append(
            _detection(
                "SCHEDULE_SLIPPAGE",
                "warning",
                planned_finish=inputs.planned_finish.isoformat(),
                forecast_finish=inputs.forecast_finish.isoformat(),
                calendar_days=str((inputs.forecast_finish - inputs.planned_finish).days),
            )
        )

    if inputs.schedule_feasible is False:
        detections.append(_detection("SCHEDULE_INFEASIBLE", "critical"))

    if (
        inputs.remaining_buffer_days is not None
        and inputs.remaining_planned_duration_days is not None
        and inputs.remaining_planned_duration_days > 0
        and inputs.remaining_buffer_days <= inputs.remaining_planned_duration_days * Decimal("0.10")
    ):
        detections.append(
            _detection(
                "LOW_BUFFER",
                "warning",
                remaining_buffer_days=str(inputs.remaining_buffer_days),
                remaining_planned_duration_days=str(inputs.remaining_planned_duration_days),
            )
        )

    if inputs.capacity_overload_ratio > Decimal("0.10"):
        detections.append(
            _detection(
                "CAPACITY_OVERLOAD",
                "warning",
                overload_ratio=str(inputs.capacity_overload_ratio),
            )
        )

    if inputs.scope_change_count:
        detections.append(
            _detection(
                "SCOPE_CHANGED",
                "info",
                changed_items=str(inputs.scope_change_count),
            )
        )

    ready = tuple(task.stable_key for task in inputs.tasks if task.status == "ready")
    if ready:
        detections.append(
            _detection(
                "READY_WORK_AVAILABLE",
                "info",
                references=ready,
                ready_count=str(len(ready)),
            )
        )

    return tuple(detections)


def _detection(
    code: str,
    severity: Literal["info", "warning", "critical"],
    *,
    references: tuple[str, ...] = (),
    **values: str,
) -> Detection:
    return Detection(
        code=code,
        severity=severity,
        references=references,
        values=values,
    )
