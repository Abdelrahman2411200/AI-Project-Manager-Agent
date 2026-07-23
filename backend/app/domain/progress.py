from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

ProgressStatus = Literal["pending", "ready", "in_progress", "blocked", "completed", "cancelled"]
PROGRESS_STATUSES = frozenset(
    {"pending", "ready", "in_progress", "blocked", "completed", "cancelled"}
)
CALCULATION_VERSION = "progress-v1"


@dataclass(frozen=True, slots=True)
class ProgressTask:
    id: UUID
    milestone_id: UUID
    parent_id: UUID | None
    status: ProgressStatus
    likely_effort_hours: Decimal | None
    progress_fraction: Decimal | None = None


@dataclass(frozen=True, slots=True)
class WeightedMetric:
    fraction: Decimal | None
    weighted_completed_hours: Decimal
    estimated_hours: Decimal
    active_leaf_count: int
    unestimated_leaf_count: int


@dataclass(frozen=True, slots=True)
class ProgressResult:
    project: WeightedMetric
    milestones: dict[UUID, WeightedMetric]
    task_fractions: dict[UUID, Decimal]
    warning_codes: tuple[str, ...]
    insufficient_data: bool
    calculation_version: str = CALCULATION_VERSION


def calculate_weighted_progress(
    tasks: list[ProgressTask] | tuple[ProgressTask, ...],
) -> ProgressResult:
    task_ids = {task.id for task in tasks}
    if len(task_ids) != len(tasks):
        raise ValueError("Task IDs must be unique.")
    for task in tasks:
        if task.status not in PROGRESS_STATUSES:
            raise ValueError(f"Unsupported task status: {task.status}.")
        if task.parent_id is not None and task.parent_id not in task_ids:
            raise ValueError(f"Task {task.id} references a missing parent.")
        if task.parent_id == task.id:
            raise ValueError(f"Task {task.id} cannot be its own parent.")
        if task.likely_effort_hours is not None and task.likely_effort_hours <= 0:
            raise ValueError("Estimated effort must be positive.")
        if task.progress_fraction is not None and not 0 <= task.progress_fraction <= 1:
            raise ValueError("Progress fractions must be between 0 and 1.")
    _validate_parent_hierarchy(tasks)

    parent_ids = {task.parent_id for task in tasks if task.parent_id is not None}
    leaves = [task for task in tasks if task.id not in parent_ids and task.status != "cancelled"]
    task_fractions = {task.id: _task_fraction(task) for task in leaves}

    project = _weighted_metric(leaves, task_fractions)
    milestone_ids = sorted({task.milestone_id for task in tasks}, key=str)
    milestones = {
        milestone_id: _weighted_metric(
            [task for task in leaves if task.milestone_id == milestone_id],
            task_fractions,
        )
        for milestone_id in milestone_ids
    }

    unestimated_ratio = (
        Decimal(project.unestimated_leaf_count) / Decimal(project.active_leaf_count)
        if project.active_leaf_count
        else Decimal(0)
    )
    insufficient_data = bool(leaves) and (
        unestimated_ratio > Decimal("0.20") or project.estimated_hours == 0
    )
    warnings: list[str] = []
    if project.unestimated_leaf_count:
        warnings.append("UNESTIMATED_ACTIVE_LEAVES")
    if insufficient_data:
        warnings.append("PROGRESS_INSUFFICIENT_DATA")
    return ProgressResult(
        project=project,
        milestones=milestones,
        task_fractions=task_fractions,
        warning_codes=tuple(warnings),
        insufficient_data=insufficient_data,
    )


def _task_fraction(task: ProgressTask) -> Decimal:
    if task.status == "completed":
        return Decimal(1)
    if task.status in {"pending", "ready"}:
        return Decimal(0)
    return _round(task.progress_fraction or Decimal(0))


def _validate_parent_hierarchy(
    tasks: list[ProgressTask] | tuple[ProgressTask, ...],
) -> None:
    parent_by_id = {task.id: task.parent_id for task in tasks}
    validated: set[UUID] = set()
    for task in tasks:
        path: set[UUID] = set()
        cursor: UUID | None = task.id
        while cursor is not None and cursor not in validated:
            if cursor in path:
                raise ValueError(f"Task hierarchy contains a cycle at {cursor}.")
            path.add(cursor)
            cursor = parent_by_id[cursor]
        validated.update(path)


def _weighted_metric(
    leaves: list[ProgressTask],
    task_fractions: dict[UUID, Decimal],
) -> WeightedMetric:
    estimated = [task for task in leaves if task.likely_effort_hours is not None]
    estimated_hours = sum(
        (task.likely_effort_hours or Decimal(0) for task in estimated),
        start=Decimal(0),
    )
    completed_hours = sum(
        ((task.likely_effort_hours or Decimal(0)) * task_fractions[task.id] for task in estimated),
        start=Decimal(0),
    )
    fraction = _round(completed_hours / estimated_hours) if estimated_hours else None
    return WeightedMetric(
        fraction=fraction,
        weighted_completed_hours=_round(completed_hours),
        estimated_hours=_round(estimated_hours),
        active_leaf_count=len(leaves),
        unestimated_leaf_count=len(leaves) - len(estimated),
    )


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
