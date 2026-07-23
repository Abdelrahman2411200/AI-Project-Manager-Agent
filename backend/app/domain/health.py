from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Literal

from app.domain.calendar import WorkCalendar, add_working_days

HealthLabel = Literal["Completed", "Insufficient data", "Delayed", "At risk", "On track"]
CALCULATION_VERSION = "health-v1"


@dataclass(frozen=True, slots=True)
class HealthEvidence:
    rule_code: str
    values: dict[str, str]
    references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HealthInputs:
    as_of: date
    noncancelled_leaf_count: int
    all_non_cancelled_complete: bool
    has_active_plan: bool
    deadline: date | None
    has_calendar: bool
    graph_valid: bool
    progress_insufficient: bool
    forecast_finish: date | None
    overdue_critical_milestone_refs: tuple[str, ...] = ()
    remaining_buffer_days: Decimal | None = None
    remaining_planned_duration_days: Decimal | None = None
    blocked_effort_hours: Decimal = Decimal(0)
    remaining_effort_hours: Decimal = Decimal(0)
    blocked_critical_path_refs: tuple[str, ...] = ()
    delayed_milestone_refs: tuple[str, ...] = ()
    capacity_overload_ratio: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class HealthResult:
    label: HealthLabel
    rule_codes: tuple[str, ...]
    evidence: tuple[HealthEvidence, ...]
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True, slots=True)
class VelocityPeriod:
    completed_planned_hours: Decimal
    available_capacity_hours: Decimal


@dataclass(frozen=True, slots=True)
class ForecastResult:
    baseline_finish: date
    velocity_adjusted_finish: date | None
    velocity_factor: Decimal | None
    periods_used: int
    calculation_version: str = CALCULATION_VERSION


def evaluate_health(inputs: HealthInputs) -> HealthResult:
    if inputs.noncancelled_leaf_count < 0:
        raise ValueError("Leaf task count cannot be negative.")
    _validate_nonnegative(
        blocked_effort_hours=inputs.blocked_effort_hours,
        remaining_effort_hours=inputs.remaining_effort_hours,
        capacity_overload_ratio=inputs.capacity_overload_ratio,
    )
    if inputs.remaining_buffer_days is not None:
        _validate_nonnegative(remaining_buffer_days=inputs.remaining_buffer_days)
    if inputs.remaining_planned_duration_days is not None:
        _validate_nonnegative(
            remaining_planned_duration_days=inputs.remaining_planned_duration_days
        )

    if inputs.noncancelled_leaf_count > 0 and inputs.all_non_cancelled_complete:
        evidence = HealthEvidence(
            rule_code="ALL_WORK_COMPLETE",
            values={"leaf_count": str(inputs.noncancelled_leaf_count)},
        )
        return _result("Completed", (evidence,))

    insufficient: list[HealthEvidence] = []
    if not inputs.has_active_plan:
        insufficient.append(_evidence("NO_ACTIVE_PLAN"))
    if inputs.deadline is None:
        insufficient.append(_evidence("MISSING_DEADLINE"))
    if not inputs.has_calendar:
        insufficient.append(_evidence("MISSING_CALENDAR"))
    if not inputs.graph_valid:
        insufficient.append(_evidence("INVALID_GRAPH"))
    if inputs.progress_insufficient:
        insufficient.append(_evidence("UNESTIMATED_THRESHOLD"))
    if insufficient:
        return _result("Insufficient data", tuple(insufficient))

    delayed: list[HealthEvidence] = []
    if inputs.deadline is not None and inputs.as_of > inputs.deadline:
        delayed.append(
            _evidence(
                "DEADLINE_PASSED_INCOMPLETE",
                as_of=inputs.as_of.isoformat(),
                deadline=inputs.deadline.isoformat(),
            )
        )
    if (
        inputs.deadline is not None
        and inputs.forecast_finish is not None
        and inputs.forecast_finish > inputs.deadline
    ):
        delayed.append(
            _evidence(
                "FORECAST_AFTER_DEADLINE",
                forecast_finish=inputs.forecast_finish.isoformat(),
                deadline=inputs.deadline.isoformat(),
            )
        )
    if inputs.overdue_critical_milestone_refs:
        delayed.append(
            _evidence(
                "OVERDUE_CRITICAL_MILESTONE",
                references=inputs.overdue_critical_milestone_refs,
                milestone_count=str(len(inputs.overdue_critical_milestone_refs)),
            )
        )
    if delayed:
        return _result("Delayed", tuple(delayed))

    at_risk: list[HealthEvidence] = []
    if (
        inputs.remaining_buffer_days is not None
        and inputs.remaining_planned_duration_days is not None
        and inputs.remaining_planned_duration_days > 0
        and inputs.remaining_buffer_days <= inputs.remaining_planned_duration_days * Decimal("0.10")
    ):
        at_risk.append(
            _evidence(
                "LOW_REMAINING_BUFFER",
                remaining_buffer_days=str(inputs.remaining_buffer_days),
                remaining_planned_duration_days=str(inputs.remaining_planned_duration_days),
            )
        )
    if (
        inputs.remaining_effort_hours > 0
        and inputs.blocked_effort_hours / inputs.remaining_effort_hours >= Decimal("0.15")
    ):
        at_risk.append(
            _evidence(
                "BLOCKED_EFFORT_THRESHOLD",
                blocked_effort_hours=str(inputs.blocked_effort_hours),
                remaining_effort_hours=str(inputs.remaining_effort_hours),
            )
        )
    if inputs.blocked_critical_path_refs:
        at_risk.append(
            _evidence(
                "BLOCKED_CRITICAL_TASK",
                references=inputs.blocked_critical_path_refs,
                blocked_count=str(len(inputs.blocked_critical_path_refs)),
            )
        )
    if inputs.delayed_milestone_refs:
        at_risk.append(
            _evidence(
                "MILESTONE_FORECAST_LATE",
                references=inputs.delayed_milestone_refs,
                milestone_count=str(len(inputs.delayed_milestone_refs)),
            )
        )
    if inputs.capacity_overload_ratio > Decimal("0.10"):
        at_risk.append(
            _evidence(
                "CAPACITY_OVERLOAD",
                overload_ratio=str(inputs.capacity_overload_ratio),
            )
        )
    if at_risk:
        return _result("At risk", tuple(at_risk))

    return _result("On track", (_evidence("NO_ADVERSE_RULES"),))


def forecast_completion(
    *,
    as_of: date,
    baseline_finish: date,
    remaining_working_days: int,
    calendar: WorkCalendar,
    velocity_periods: tuple[VelocityPeriod, ...] = (),
) -> ForecastResult:
    if remaining_working_days < 0:
        raise ValueError("Remaining working days cannot be negative.")
    for period in velocity_periods:
        _validate_nonnegative(
            completed_planned_hours=period.completed_planned_hours,
            available_capacity_hours=period.available_capacity_hours,
        )
    usable_periods = tuple(
        period for period in velocity_periods if period.available_capacity_hours > 0
    )
    if len(usable_periods) < 3:
        return ForecastResult(
            baseline_finish=baseline_finish,
            velocity_adjusted_finish=None,
            velocity_factor=None,
            periods_used=len(usable_periods),
        )

    completed = sum(
        (period.completed_planned_hours for period in usable_periods),
        start=Decimal(0),
    )
    capacity = sum(
        (period.available_capacity_hours for period in usable_periods),
        start=Decimal(0),
    )
    factor = min(Decimal("1.25"), max(Decimal("0.50"), completed / capacity))
    adjusted_days = int(
        (Decimal(remaining_working_days) / factor).to_integral_value(rounding=ROUND_CEILING)
    )
    adjusted_finish = add_working_days(calendar, as_of, adjusted_days)
    return ForecastResult(
        baseline_finish=baseline_finish,
        velocity_adjusted_finish=adjusted_finish,
        velocity_factor=factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        periods_used=len(usable_periods),
    )


def _result(label: HealthLabel, evidence: tuple[HealthEvidence, ...]) -> HealthResult:
    return HealthResult(
        label=label,
        rule_codes=tuple(item.rule_code for item in evidence),
        evidence=evidence,
    )


def _evidence(
    rule_code: str,
    *,
    references: tuple[str, ...] = (),
    **values: str,
) -> HealthEvidence:
    return HealthEvidence(rule_code=rule_code, values=values, references=references)


def _validate_nonnegative(**values: Decimal) -> None:
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} cannot be negative.")
