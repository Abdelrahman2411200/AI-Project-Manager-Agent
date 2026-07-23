import random
from uuid import UUID

import pytest

from app.domain.graph import (
    DependencyEdge,
    GraphTask,
    GraphValidationError,
    project_readiness,
    validate_graph,
)

VERSION = UUID(int=1)
OTHER_VERSION = UUID(int=2)


def task(number: int, *, status: str = "pending", version: UUID = VERSION) -> GraphTask:
    return GraphTask(
        id=UUID(int=100 + number),
        stable_key=f"TASK-{number:03d}",
        version_id=version,
        status=status,  # type: ignore[arg-type]
    )


def edge(predecessor: int, successor: int, *, version: UUID = VERSION) -> DependencyEdge:
    return DependencyEdge(
        predecessor_id=task(predecessor).id,
        successor_id=task(successor).id,
        version_id=version,
    )


def test_topological_order_is_stable_and_downstream_is_complete() -> None:
    tasks = [task(4), task(2), task(1), task(3)]
    result = validate_graph(
        tasks,
        [edge(1, 3), edge(2, 3), edge(3, 4)],
        VERSION,
    )

    assert result.topological_order == tuple(task(number).id for number in (1, 2, 3, 4))
    assert result.downstream[task(1).id] == frozenset({task(3).id, task(4).id})
    assert result.downstream[task(4).id] == frozenset()
    empty = validate_graph([], [], VERSION)
    assert empty.topological_order == ()
    assert empty.downstream == {}


@pytest.mark.parametrize(
    ("tasks", "edges", "code"),
    [
        (
            [
                GraphTask(
                    id=UUID(int=999),
                    stable_key="TASK-999",
                    version_id=VERSION,
                    status="unknown",  # type: ignore[arg-type]
                )
            ],
            [],
            "INVALID_TASK_STATUS",
        ),
        ([task(1, version=OTHER_VERSION)], [], "CROSS_VERSION_TASK"),
        ([task(1), task(1)], [], "DUPLICATE_TASK_ID"),
        (
            [
                task(1),
                GraphTask(
                    id=UUID(int=999),
                    stable_key=task(1).stable_key,
                    version_id=VERSION,
                ),
            ],
            [],
            "DUPLICATE_STABLE_KEY",
        ),
        ([task(1), task(2)], [edge(1, 2, version=OTHER_VERSION)], "CROSS_VERSION_EDGE"),
        (
            [task(1)],
            [
                DependencyEdge(
                    predecessor_id=task(1).id,
                    successor_id=UUID(int=999),
                    version_id=VERSION,
                )
            ],
            "MISSING_TASK_REFERENCE",
        ),
        ([task(1)], [edge(1, 1)], "SELF_DEPENDENCY"),
        ([task(1), task(2)], [edge(1, 2), edge(1, 2)], "DUPLICATE_DEPENDENCY"),
    ],
)
def test_invalid_graph_inputs_fail_closed(
    tasks: list[GraphTask],
    edges: list[DependencyEdge],
    code: str,
) -> None:
    with pytest.raises(GraphValidationError) as error:
        validate_graph(tasks, edges, VERSION)
    assert error.value.code == code
    assert error.value.references


def test_cycle_error_returns_closed_stable_key_path() -> None:
    with pytest.raises(GraphValidationError) as error:
        validate_graph(
            [task(1), task(2), task(3), task(4)],
            [edge(1, 2), edge(2, 3), edge(3, 1), edge(4, 3)],
            VERSION,
        )

    assert error.value.code == "DEPENDENCY_CYCLE"
    assert error.value.cycle_path == ("TASK-001", "TASK-002", "TASK-003", "TASK-001")


def test_readiness_preserves_started_states_and_projects_pending_states() -> None:
    tasks = [
        task(1, status="completed"),
        task(2),
        task(3, status="in_progress"),
        task(4, status="blocked"),
        task(5, status="ready"),
        task(6, status="ready"),
    ]
    projections = project_readiness(
        tasks,
        [edge(1, 2), edge(2, 3), edge(2, 4), edge(2, 5)],
        VERSION,
    )

    assert projections[task(1).id].projected_status == "completed"
    assert projections[task(2).id].projected_status == "ready"
    assert projections[task(2).id].ready_to_start is True
    assert projections[task(3).id].projected_status == "in_progress"
    assert projections[task(3).id].prerequisites_satisfied is False
    assert projections[task(4).id].projected_status == "blocked"
    assert projections[task(5).id].projected_status == "pending"
    assert projections[task(5).id].incomplete_predecessor_ids == (task(2).id,)
    assert projections[task(6).id].projected_status == "ready"
    assert projections[task(6).id].ready_to_start is True


def test_seeded_dag_property_every_edge_respects_returned_order() -> None:
    randomizer = random.Random(20260723)
    tasks = [task(number) for number in range(1, 41)]
    for _ in range(25):
        edges = [
            edge(predecessor, successor)
            for predecessor in range(1, 41)
            for successor in range(predecessor + 1, 41)
            if randomizer.random() < 0.04
        ]
        shuffled = list(tasks)
        randomizer.shuffle(shuffled)
        result = validate_graph(shuffled, edges, VERSION)
        positions = {task_id: position for position, task_id in enumerate(result.topological_order)}
        assert len(result.topological_order) == len(tasks)
        assert all(positions[item.predecessor_id] < positions[item.successor_id] for item in edges)
