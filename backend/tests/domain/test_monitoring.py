from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.monitoring import (
    MonitoringInputs,
    MonitoringMilestone,
    MonitoringTask,
    detect_conditions,
)

VERSION = UUID("10000000-0000-4000-8000-000000000001")
MILESTONE = UUID("20000000-0000-4000-8000-000000000001")


def task(
    number: int,
    status: str,
    *,
    planned_finish: date | None = None,
    predecessors: tuple[UUID, ...] = (),
) -> MonitoringTask:
    return MonitoringTask(
        id=UUID(f"30000000-0000-4000-8000-{number:012d}"),
        stable_key=f"TASK-{number:03d}",
        milestone_id=MILESTONE,
        status=status,  # type: ignore[arg-type]
        planned_finish=planned_finish,
        predecessor_ids=predecessors,
    )


def test_detectors_return_stable_codes_and_concrete_evidence() -> None:
    predecessor = task(1, "blocked", planned_finish=date(2026, 7, 20))
    successor = task(
        2,
        "ready",
        planned_finish=date(2026, 7, 21),
        predecessors=(predecessor.id,),
    )
    result = detect_conditions(
        MonitoringInputs(
            as_of=date(2026, 7, 23),
            tasks=(predecessor, successor),
            milestones=(
                MonitoringMilestone(
                    id=MILESTONE,
                    stable_key="MS-001",
                    target_date=date(2026, 7, 22),
                    incomplete_task_count=2,
                ),
            ),
            graph_valid=False,
            schedule_feasible=False,
            planned_finish=date(2026, 7, 25),
            forecast_finish=date(2026, 7, 30),
            remaining_buffer_days=Decimal(1),
            remaining_planned_duration_days=Decimal(20),
            capacity_overload_ratio=Decimal("0.20"),
            scope_change_count=2,
        )
    )
    by_code = {item.code: item for item in result}
    assert set(by_code) == {
        "INCONSISTENT_STATE",
        "BLOCKED_TASKS",
        "OVERDUE_TASKS",
        "UNMET_DEPENDENCY",
        "DELAYED_MILESTONE",
        "SCHEDULE_SLIPPAGE",
        "SCHEDULE_INFEASIBLE",
        "LOW_BUFFER",
        "CAPACITY_OVERLOAD",
        "SCOPE_CHANGED",
        "READY_WORK_AVAILABLE",
    }
    assert by_code["BLOCKED_TASKS"].references == ("TASK-001",)
    assert by_code["UNMET_DEPENDENCY"].references == (
        "TASK-002",
        "TASK-001",
    )
    assert by_code["DELAYED_MILESTONE"].references == ("MS-001",)
    assert by_code["SCHEDULE_SLIPPAGE"].values["calendar_days"] == "5"
    assert all(item.calculation_version == "monitoring-v1" for item in result)


def test_detectors_do_not_invent_conditions_for_healthy_state() -> None:
    result = detect_conditions(
        MonitoringInputs(
            as_of=date(2026, 7, 23),
            tasks=(task(1, "completed"), task(2, "pending")),
            milestones=(
                MonitoringMilestone(
                    id=MILESTONE,
                    stable_key="MS-001",
                    target_date=date(2026, 8, 1),
                    incomplete_task_count=1,
                ),
            ),
            graph_valid=True,
            schedule_feasible=True,
            planned_finish=date(2026, 8, 1),
            forecast_finish=date(2026, 7, 30),
            remaining_buffer_days=Decimal(5),
            remaining_planned_duration_days=Decimal(20),
        )
    )
    assert result == ()


@pytest.mark.parametrize(
    ("overload", "buffer", "duration", "scope"),
    [
        (Decimal("-0.1"), Decimal(1), Decimal(1), 0),
        (Decimal(0), Decimal("-1"), Decimal(1), 0),
        (Decimal(0), Decimal(1), Decimal("-1"), 0),
        (Decimal(0), Decimal(1), Decimal(1), -1),
    ],
)
def test_detector_inputs_reject_invalid_values(
    overload: Decimal,
    buffer: Decimal,
    duration: Decimal,
    scope: int,
) -> None:
    with pytest.raises(ValueError):
        detect_conditions(
            MonitoringInputs(
                as_of=date(2026, 7, 23),
                tasks=(),
                milestones=(),
                graph_valid=True,
                schedule_feasible=True,
                remaining_buffer_days=buffer,
                remaining_planned_duration_days=duration,
                capacity_overload_ratio=overload,
                scope_change_count=scope,
            )
        )
