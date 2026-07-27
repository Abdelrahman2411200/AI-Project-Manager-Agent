"""Deterministic critical-path calculation over a validated task DAG."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.graph import DependencyEdge, GraphTask, validate_graph

CALCULATION_VERSION = "critical-path-v1"
SCHEDULING_QUANTUM_HOURS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class CriticalPathTask:
    id: UUID
    stable_key: str
    version_id: UUID
    duration_hours: Decimal


@dataclass(frozen=True, slots=True)
class CriticalPathNode:
    stable_key: str
    earliest_start_hours: Decimal
    earliest_finish_hours: Decimal
    latest_start_hours: Decimal
    latest_finish_hours: Decimal
    slack_hours: Decimal
    critical: bool


@dataclass(frozen=True, slots=True)
class CriticalPathResult:
    nodes: dict[UUID, CriticalPathNode]
    critical_keys: tuple[str, ...]
    duration_hours: Decimal
    calculation_version: str = CALCULATION_VERSION


def calculate_critical_path(
    tasks: list[CriticalPathTask] | tuple[CriticalPathTask, ...],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    version_id: UUID,
) -> CriticalPathResult:
    task_by_id = {task.id: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("Critical path tasks must have unique IDs.")
    for task in tasks:
        if task.version_id != version_id:
            raise ValueError(f"Task {task.stable_key} belongs to another version.")
        if task.duration_hours <= 0:
            raise ValueError(f"Task {task.stable_key} must have positive duration.")
    graph = validate_graph(
        [
            GraphTask(id=task.id, stable_key=task.stable_key, version_id=task.version_id)
            for task in tasks
        ],
        edges,
        version_id,
    )
    if not tasks:
        return CriticalPathResult(nodes={}, critical_keys=(), duration_hours=Decimal(0))

    earliest_start: dict[UUID, Decimal] = {}
    earliest_finish: dict[UUID, Decimal] = {}
    for task_id in graph.topological_order:
        earliest_start[task_id] = max(
            (earliest_finish[item] for item in graph.predecessors[task_id]),
            default=Decimal(0),
        )
        earliest_finish[task_id] = earliest_start[task_id] + task_by_id[task_id].duration_hours

    project_finish = max(earliest_finish.values(), default=Decimal(0))
    latest_start: dict[UUID, Decimal] = {}
    latest_finish: dict[UUID, Decimal] = {}
    for task_id in reversed(graph.topological_order):
        latest_finish[task_id] = min(
            (latest_start[item] for item in graph.successors[task_id]),
            default=project_finish,
        )
        latest_start[task_id] = latest_finish[task_id] - task_by_id[task_id].duration_hours

    nodes: dict[UUID, CriticalPathNode] = {}
    for task_id in graph.topological_order:
        slack = latest_start[task_id] - earliest_start[task_id]
        nodes[task_id] = CriticalPathNode(
            stable_key=task_by_id[task_id].stable_key,
            earliest_start_hours=earliest_start[task_id],
            earliest_finish_hours=earliest_finish[task_id],
            latest_start_hours=latest_start[task_id],
            latest_finish_hours=latest_finish[task_id],
            slack_hours=slack,
            critical=slack <= SCHEDULING_QUANTUM_HOURS,
        )
    critical_keys = tuple(
        nodes[task_id].stable_key for task_id in graph.topological_order if nodes[task_id].critical
    )
    return CriticalPathResult(
        nodes=nodes,
        critical_keys=critical_keys,
        duration_hours=project_finish,
    )
