from datetime import date
from decimal import Decimal

import pytest

from app.domain.calendar import WorkCalendar
from app.domain.health import (
    HealthInputs,
    VelocityPeriod,
    evaluate_health,
    forecast_completion,
)


def healthy_inputs(**overrides: object) -> HealthInputs:
    values: dict[str, object] = {
        "as_of": date(2026, 7, 23),
        "noncancelled_leaf_count": 5,
        "all_non_cancelled_complete": False,
        "has_active_plan": True,
        "deadline": date(2026, 8, 31),
        "has_calendar": True,
        "graph_valid": True,
        "progress_insufficient": False,
        "forecast_finish": date(2026, 8, 20),
        "remaining_buffer_days": Decimal(5),
        "remaining_planned_duration_days": Decimal(20),
        "blocked_effort_hours": Decimal(0),
        "remaining_effort_hours": Decimal(100),
        "capacity_overload_ratio": Decimal(0),
    }
    values.update(overrides)
    return HealthInputs(**values)  # type: ignore[arg-type]


def test_completed_has_highest_precedence() -> None:
    result = evaluate_health(
        healthy_inputs(
            all_non_cancelled_complete=True,
            has_active_plan=False,
            deadline=None,
            graph_valid=False,
        )
    )
    assert result.label == "Completed"
    assert result.rule_codes == ("ALL_WORK_COMPLETE",)


def test_insufficient_data_precedes_delay_and_reports_every_reason() -> None:
    result = evaluate_health(
        healthy_inputs(
            has_active_plan=False,
            deadline=None,
            has_calendar=False,
            graph_valid=False,
            progress_insufficient=True,
            forecast_finish=date(2027, 1, 1),
        )
    )
    assert result.label == "Insufficient data"
    assert result.rule_codes == (
        "NO_ACTIVE_PLAN",
        "MISSING_DEADLINE",
        "MISSING_CALENDAR",
        "INVALID_GRAPH",
        "UNESTIMATED_THRESHOLD",
    )


def test_delayed_rules_precede_at_risk_rules_and_include_evidence() -> None:
    result = evaluate_health(
        healthy_inputs(
            as_of=date(2026, 9, 1),
            forecast_finish=date(2026, 9, 5),
            overdue_critical_milestone_refs=("MS-003",),
            blocked_critical_path_refs=("TASK-014",),
        )
    )
    assert result.label == "Delayed"
    assert result.rule_codes == (
        "DEADLINE_PASSED_INCOMPLETE",
        "FORECAST_AFTER_DEADLINE",
        "OVERDUE_CRITICAL_MILESTONE",
    )
    assert result.evidence[-1].references == ("MS-003",)


def test_at_risk_rules_use_exact_thresholds_and_stable_references() -> None:
    result = evaluate_health(
        healthy_inputs(
            remaining_buffer_days=Decimal(2),
            remaining_planned_duration_days=Decimal(20),
            blocked_effort_hours=Decimal(15),
            blocked_critical_path_refs=("TASK-014",),
            delayed_milestone_refs=("MS-004",),
            capacity_overload_ratio=Decimal("0.11"),
        )
    )
    assert result.label == "At risk"
    assert result.rule_codes == (
        "LOW_REMAINING_BUFFER",
        "BLOCKED_EFFORT_THRESHOLD",
        "BLOCKED_CRITICAL_TASK",
        "MILESTONE_FORECAST_LATE",
        "CAPACITY_OVERLOAD",
    )
    assert result.evidence[2].references == ("TASK-014",)


def test_on_track_is_returned_only_when_no_adverse_rule_matches() -> None:
    result = evaluate_health(healthy_inputs())
    assert result.label == "On track"
    assert result.rule_codes == ("NO_ADVERSE_RULES",)
    assert result.calculation_version == "health-v1"


def test_velocity_forecast_requires_three_periods_and_caps_velocity() -> None:
    calendar = WorkCalendar(
        timezone="Africa/Cairo",
        weekday_hours={weekday: Decimal(8) for weekday in range(5)},
    )
    baseline = date(2026, 8, 6)
    too_little = forecast_completion(
        as_of=date(2026, 7, 23),
        baseline_finish=baseline,
        remaining_working_days=10,
        calendar=calendar,
        velocity_periods=(
            VelocityPeriod(Decimal(5), Decimal(10)),
            VelocityPeriod(Decimal(5), Decimal(10)),
        ),
    )
    assert too_little.velocity_adjusted_finish is None
    assert too_little.periods_used == 2

    slow = forecast_completion(
        as_of=date(2026, 7, 23),
        baseline_finish=baseline,
        remaining_working_days=10,
        calendar=calendar,
        velocity_periods=(
            VelocityPeriod(Decimal(2), Decimal(10)),
            VelocityPeriod(Decimal(2), Decimal(10)),
            VelocityPeriod(Decimal(2), Decimal(10)),
        ),
    )
    assert slow.velocity_factor == Decimal("0.50")
    assert slow.velocity_adjusted_finish == date(2026, 8, 20)

    fast = forecast_completion(
        as_of=date(2026, 7, 23),
        baseline_finish=baseline,
        remaining_working_days=10,
        calendar=calendar,
        velocity_periods=(
            VelocityPeriod(Decimal(20), Decimal(10)),
            VelocityPeriod(Decimal(20), Decimal(10)),
            VelocityPeriod(Decimal(20), Decimal(10)),
        ),
    )
    assert fast.velocity_factor == Decimal("1.25")
    assert fast.velocity_adjusted_finish == date(2026, 8, 4)


def test_invalid_health_and_forecast_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="count"):
        evaluate_health(healthy_inputs(noncancelled_leaf_count=-1))
    with pytest.raises(ValueError, match="blocked_effort_hours"):
        evaluate_health(healthy_inputs(blocked_effort_hours=Decimal(-1)))
    with pytest.raises(ValueError, match="remaining_buffer_days"):
        evaluate_health(healthy_inputs(remaining_buffer_days=Decimal(-1)))

    calendar = WorkCalendar(
        timezone="Africa/Cairo",
        weekday_hours={weekday: Decimal(8) for weekday in range(5)},
    )
    with pytest.raises(ValueError, match="Remaining"):
        forecast_completion(
            as_of=date(2026, 7, 23),
            baseline_finish=date(2026, 7, 23),
            remaining_working_days=-1,
            calendar=calendar,
        )
    with pytest.raises(ValueError, match="completed_planned_hours"):
        forecast_completion(
            as_of=date(2026, 7, 23),
            baseline_finish=date(2026, 7, 23),
            remaining_working_days=1,
            calendar=calendar,
            velocity_periods=(VelocityPeriod(Decimal(-1), Decimal(1)),),
        )
