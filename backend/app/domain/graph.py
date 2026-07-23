from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

TaskStatus = Literal["pending", "ready", "in_progress", "blocked", "completed", "cancelled"]
TASK_STATUSES = frozenset({"pending", "ready", "in_progress", "blocked", "completed", "cancelled"})


@dataclass(frozen=True, slots=True)
class GraphTask:
    id: UUID
    stable_key: str
    version_id: UUID
    status: TaskStatus = "pending"


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    predecessor_id: UUID
    successor_id: UUID
    version_id: UUID


@dataclass(frozen=True, slots=True)
class GraphResult:
    version_id: UUID
    topological_order: tuple[UUID, ...]
    predecessors: dict[UUID, frozenset[UUID]]
    successors: dict[UUID, frozenset[UUID]]
    downstream: dict[UUID, frozenset[UUID]]


@dataclass(frozen=True, slots=True)
class ReadinessProjection:
    task_id: UUID
    projected_status: TaskStatus
    prerequisites_satisfied: bool
    ready_to_start: bool
    incomplete_predecessor_ids: tuple[UUID, ...]


class GraphValidationError(ValueError):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        references: tuple[str, ...] = (),
        cycle_path: tuple[str, ...] = (),
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.references = references
        self.cycle_path = cycle_path


def validate_graph(
    tasks: list[GraphTask] | tuple[GraphTask, ...],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    version_id: UUID,
) -> GraphResult:
    task_by_id: dict[UUID, GraphTask] = {}
    key_to_id: dict[str, UUID] = {}
    for task in tasks:
        if task.status not in TASK_STATUSES:
            raise GraphValidationError(
                "INVALID_TASK_STATUS",
                f"Task {task.stable_key} has unsupported status {task.status}.",
                references=(task.stable_key,),
            )
        if task.version_id != version_id:
            raise GraphValidationError(
                "CROSS_VERSION_TASK",
                f"Task {task.stable_key} does not belong to the requested version.",
                references=(task.stable_key,),
            )
        if task.id in task_by_id:
            raise GraphValidationError(
                "DUPLICATE_TASK_ID",
                f"Task ID {task.id} occurs more than once.",
                references=(str(task.id),),
            )
        if task.stable_key in key_to_id:
            raise GraphValidationError(
                "DUPLICATE_STABLE_KEY",
                f"Task key {task.stable_key} occurs more than once.",
                references=(task.stable_key,),
            )
        task_by_id[task.id] = task
        key_to_id[task.stable_key] = task.id

    successors: dict[UUID, set[UUID]] = {task_id: set() for task_id in task_by_id}
    predecessors: dict[UUID, set[UUID]] = {task_id: set() for task_id in task_by_id}
    seen_edges: set[tuple[UUID, UUID]] = set()

    for edge in edges:
        if edge.version_id != version_id:
            raise GraphValidationError(
                "CROSS_VERSION_EDGE",
                "Dependency does not belong to the requested version.",
                references=(str(edge.predecessor_id), str(edge.successor_id)),
            )
        missing_ids = tuple(
            str(task_id)
            for task_id in (edge.predecessor_id, edge.successor_id)
            if task_id not in task_by_id
        )
        if missing_ids:
            raise GraphValidationError(
                "MISSING_TASK_REFERENCE",
                "Dependency references a task outside the version.",
                references=missing_ids,
            )
        if edge.predecessor_id == edge.successor_id:
            key = task_by_id[edge.predecessor_id].stable_key
            raise GraphValidationError(
                "SELF_DEPENDENCY",
                f"Task {key} cannot depend on itself.",
                references=(key,),
            )
        pair = (edge.predecessor_id, edge.successor_id)
        if pair in seen_edges:
            predecessor_key = task_by_id[edge.predecessor_id].stable_key
            successor_key = task_by_id[edge.successor_id].stable_key
            raise GraphValidationError(
                "DUPLICATE_DEPENDENCY",
                f"Dependency {predecessor_key} -> {successor_key} occurs more than once.",
                references=(predecessor_key, successor_key),
            )
        seen_edges.add(pair)
        successors[edge.predecessor_id].add(edge.successor_id)
        predecessors[edge.successor_id].add(edge.predecessor_id)

    indegree = {task_id: len(incoming) for task_id, incoming in predecessors.items()}
    queue = [
        (task_by_id[task_id].stable_key, task_id)
        for task_id, degree in indegree.items()
        if degree == 0
    ]
    heapq.heapify(queue)
    order: list[UUID] = []

    while queue:
        _, task_id = heapq.heappop(queue)
        order.append(task_id)
        for successor_id in sorted(
            successors[task_id], key=lambda item: task_by_id[item].stable_key
        ):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                heapq.heappush(queue, (task_by_id[successor_id].stable_key, successor_id))

    if len(order) != len(task_by_id):
        remaining = {task_id for task_id, degree in indegree.items() if degree > 0}
        cycle_ids = _first_cycle(remaining, successors, task_by_id)
        cycle_keys = tuple(task_by_id[task_id].stable_key for task_id in cycle_ids)
        raise GraphValidationError(
            "DEPENDENCY_CYCLE",
            f"Dependency cycle detected: {' -> '.join(cycle_keys)}.",
            references=cycle_keys,
            cycle_path=cycle_keys,
        )

    downstream = _calculate_downstream(tuple(reversed(order)), successors)
    return GraphResult(
        version_id=version_id,
        topological_order=tuple(order),
        predecessors={task_id: frozenset(items) for task_id, items in predecessors.items()},
        successors={task_id: frozenset(items) for task_id, items in successors.items()},
        downstream=downstream,
    )


def project_readiness(
    tasks: list[GraphTask] | tuple[GraphTask, ...],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    version_id: UUID,
) -> dict[UUID, ReadinessProjection]:
    graph = validate_graph(tasks, edges, version_id)
    task_by_id = {task.id: task for task in tasks}
    projections: dict[UUID, ReadinessProjection] = {}

    for task_id in graph.topological_order:
        task = task_by_id[task_id]
        incomplete = tuple(
            sorted(
                (
                    predecessor_id
                    for predecessor_id in graph.predecessors[task_id]
                    if task_by_id[predecessor_id].status != "completed"
                ),
                key=lambda item: task_by_id[item].stable_key,
            )
        )
        prerequisites_satisfied = not incomplete
        ready_to_start = prerequisites_satisfied and task.status in {"pending", "ready"}
        projected_status: TaskStatus = task.status
        if task.status == "pending" and prerequisites_satisfied:
            projected_status = "ready"
        elif task.status == "ready" and not prerequisites_satisfied:
            projected_status = "pending"
        projections[task_id] = ReadinessProjection(
            task_id=task_id,
            projected_status=projected_status,
            prerequisites_satisfied=prerequisites_satisfied,
            ready_to_start=ready_to_start,
            incomplete_predecessor_ids=incomplete,
        )
    return projections


def _calculate_downstream(
    reverse_topological_order: tuple[UUID, ...],
    successors: dict[UUID, set[UUID]],
) -> dict[UUID, frozenset[UUID]]:
    downstream: dict[UUID, frozenset[UUID]] = {}
    for task_id in reverse_topological_order:
        reachable: set[UUID] = set()
        for successor_id in successors[task_id]:
            reachable.add(successor_id)
            reachable.update(downstream[successor_id])
        downstream[task_id] = frozenset(reachable)
    return downstream


def _first_cycle(
    remaining: set[UUID],
    successors: dict[UUID, set[UUID]],
    task_by_id: dict[UUID, GraphTask],
) -> tuple[UUID, ...]:
    color: defaultdict[UUID, int] = defaultdict(int)
    stack: list[UUID] = []
    stack_index: dict[UUID, int] = {}

    def visit(task_id: UUID) -> tuple[UUID, ...] | None:
        color[task_id] = 1
        stack_index[task_id] = len(stack)
        stack.append(task_id)
        for successor_id in sorted(
            successors[task_id], key=lambda item: task_by_id[item].stable_key
        ):
            if successor_id not in remaining:
                continue
            if color[successor_id] == 0:
                cycle = visit(successor_id)
                if cycle is not None:
                    return cycle
            elif color[successor_id] == 1:
                return tuple([*stack[stack_index[successor_id] :], successor_id])
        stack.pop()
        stack_index.pop(task_id)
        color[task_id] = 2
        return None

    for task_id in sorted(remaining, key=lambda item: task_by_id[item].stable_key):
        if color[task_id] == 0:
            cycle = visit(task_id)
            if cycle is not None:
                return cycle
    raise RuntimeError("Cycle detection failed for a graph known to be cyclic.")
