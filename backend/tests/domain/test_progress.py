from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.progress import ProgressTask, calculate_weighted_progress

MILESTONE_A = UUID(int=501)
MILESTONE_B = UUID(int=502)


def progress_task(
    number: int,
    *,
    milestone_id: UUID = MILESTONE_A,
    parent_id: UUID | None = None,
    status: str = "pending",
    effort: Decimal | None = Decimal(8),
    fraction: Decimal | None = None,
) -> ProgressTask:
    return ProgressTask(
        id=UUID(int=600 + number),
        milestone_id=milestone_id,
        parent_id=parent_id,
        status=status,  # type: ignore[arg-type]
        likely_effort_hours=effort,
        progress_fraction=fraction,
    )


def test_weighted_progress_uses_leaf_effort_only() -> None:
    parent = progress_task(1, effort=Decimal(100))
    tasks = [
        parent,
        progress_task(2, parent_id=parent.id, status="completed", effort=Decimal(10)),
        progress_task(
            3,
            parent_id=parent.id,
            status="in_progress",
            effort=Decimal(30),
            fraction=Decimal("0.50"),
        ),
        progress_task(4, milestone_id=MILESTONE_B, status="blocked", effort=Decimal(20)),
    ]

    result = calculate_weighted_progress(tasks)

    assert result.project.estimated_hours == Decimal("60.0000")
    assert result.project.weighted_completed_hours == Decimal("25.0000")
    assert result.project.fraction == Decimal("0.4167")
    assert parent.id not in result.task_fractions
    assert result.milestones[MILESTONE_A].fraction == Decimal("0.6250")
    assert result.milestones[MILESTONE_B].fraction == Decimal("0.0000")


def test_cancelled_leaves_are_excluded_and_completed_forces_one() -> None:
    completed = progress_task(1, status="completed", fraction=Decimal("0.20"))
    cancelled = progress_task(2, status="cancelled", effort=Decimal(100))
    result = calculate_weighted_progress([completed, cancelled])

    assert result.project.active_leaf_count == 1
    assert result.project.fraction == Decimal("1.0000")
    assert completed.id in result.task_fractions
    assert cancelled.id not in result.task_fractions


@pytest.mark.parametrize("status", ["pending", "ready"])
def test_pending_and_ready_ignore_stored_fraction(status: str) -> None:
    item = progress_task(1, status=status, fraction=Decimal("0.75"))
    result = calculate_weighted_progress([item])
    assert result.task_fractions[item.id] == 0


def test_unestimated_threshold_is_explicit() -> None:
    tasks = [
        progress_task(1, effort=Decimal(8)),
        progress_task(2, effort=Decimal(8)),
        progress_task(3, effort=Decimal(8)),
        progress_task(4, effort=None),
    ]
    result = calculate_weighted_progress(tasks)
    assert result.project.fraction == Decimal("0.0000")
    assert result.project.unestimated_leaf_count == 1
    assert result.insufficient_data is True
    assert result.warning_codes == (
        "UNESTIMATED_ACTIVE_LEAVES",
        "PROGRESS_INSUFFICIENT_DATA",
    )

    boundary = calculate_weighted_progress(
        [
            progress_task(number, effort=None if number == 5 else Decimal(8))
            for number in range(1, 6)
        ]
    )
    assert boundary.project.unestimated_leaf_count == 1
    assert boundary.insufficient_data is False


def test_no_active_leaves_is_not_marked_insufficient() -> None:
    result = calculate_weighted_progress([progress_task(1, status="cancelled")])
    assert result.project.fraction is None
    assert result.insufficient_data is False


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([progress_task(1), progress_task(1)], "unique"),
        ([progress_task(1, status="unknown")], "Unsupported"),
        ([progress_task(1, parent_id=UUID(int=999))], "missing parent"),
        (
            [
                ProgressTask(
                    id=UUID(int=601),
                    milestone_id=MILESTONE_A,
                    parent_id=UUID(int=601),
                    status="pending",
                    likely_effort_hours=Decimal(8),
                )
            ],
            "own parent",
        ),
        ([progress_task(1, effort=Decimal(0))], "positive"),
        ([progress_task(1, fraction=Decimal("1.01"))], "between 0 and 1"),
    ],
)
def test_invalid_progress_inputs_are_rejected(
    tasks: list[ProgressTask],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        calculate_weighted_progress(tasks)


def test_parent_hierarchy_cycles_are_rejected() -> None:
    first = progress_task(1, parent_id=UUID(int=602))
    second = progress_task(2, parent_id=first.id)
    with pytest.raises(ValueError, match="cycle"):
        calculate_weighted_progress([first, second])
