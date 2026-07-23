from datetime import date, time
from decimal import Decimal

import pytest

from app.domain.calendar import (
    WorkCalendar,
    add_working_days,
    count_working_days,
    expand_working_days,
    is_working_day,
    next_working_day,
    working_day,
)


def standard_calendar(**overrides: object) -> WorkCalendar:
    values: dict[str, object] = {
        "timezone": "Africa/Cairo",
        "weekday_hours": {weekday: Decimal(8) for weekday in range(5)},
        "parallel_limit": 2,
    }
    values.update(overrides)
    return WorkCalendar(**values)  # type: ignore[arg-type]


def test_weekends_holidays_effective_dates_and_capacity() -> None:
    calendar = standard_calendar(
        holidays=frozenset({date(2026, 7, 27)}),
        effective_from=date(2026, 7, 23),
        effective_to=date(2026, 7, 31),
        availability_factor=Decimal("0.75"),
    )

    assert is_working_day(calendar, date(2026, 7, 22)) is False
    assert is_working_day(calendar, date(2026, 7, 24)) is True
    assert is_working_day(calendar, date(2026, 7, 25)) is False
    assert is_working_day(calendar, date(2026, 7, 27)) is False
    slot = working_day(calendar, date(2026, 7, 28))
    assert slot is not None
    assert slot.nominal_hours == Decimal(8)
    assert slot.effective_hours == Decimal("6.00")
    assert working_day(calendar, date(2026, 8, 3)) is None


def test_expansion_navigation_and_counting_use_working_days() -> None:
    calendar = standard_calendar(holidays=frozenset({date(2026, 7, 27)}))
    days = expand_working_days(calendar, date(2026, 7, 23), date(2026, 7, 29))

    assert [item.day for item in days] == [
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 28),
        date(2026, 7, 29),
    ]
    assert next_working_day(calendar, date(2026, 7, 25)) == date(2026, 7, 28)
    assert next_working_day(calendar, date(2026, 7, 24), include_day=False) == date(2026, 7, 28)
    assert add_working_days(calendar, date(2026, 7, 24), 2) == date(2026, 7, 29)
    assert add_working_days(calendar, date(2026, 7, 24), 0) == date(2026, 7, 24)
    assert count_working_days(calendar, date(2026, 7, 23), date(2026, 7, 29)) == 4
    assert (
        count_working_days(
            calendar,
            date(2026, 7, 23),
            date(2026, 7, 29),
            include_start=False,
            include_end=False,
        )
        == 2
    )
    assert count_working_days(calendar, date(2026, 7, 29), date(2026, 7, 23)) == -4


def test_dst_transitions_preserve_local_schedule_and_expose_real_utc_duration() -> None:
    spring = WorkCalendar(
        timezone="America/New_York",
        weekday_hours={6: Decimal(8)},
        day_start_local=time(0),
    )
    spring_slot = working_day(spring, date(2026, 3, 8))
    assert spring_slot is not None
    assert (spring_slot.end_utc - spring_slot.start_utc).total_seconds() / 3600 == 7

    fall_slot = working_day(spring, date(2026, 11, 1))
    assert fall_slot is not None
    assert (fall_slot.end_utc - fall_slot.start_utc).total_seconds() / 3600 == 9


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timezone": "Not/A_Timezone"}, "Unknown IANA"),
        (
            {
                "effective_from": date(2026, 8, 1),
                "effective_to": date(2026, 7, 1),
            },
            "effective_to",
        ),
        ({"availability_factor": Decimal(0)}, "Availability"),
        ({"parallel_limit": 0}, "Parallel"),
        ({"weekday_hours": {7: Decimal(8)}}, "Weekday"),
        ({"weekday_hours": {0: Decimal(25)}}, "between 0 and 24"),
    ],
)
def test_calendar_configuration_is_validated(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        standard_calendar(**kwargs)


def test_date_range_and_navigation_failures_are_actionable() -> None:
    calendar = standard_calendar()
    with pytest.raises(ValueError, match="precede"):
        expand_working_days(calendar, date(2026, 7, 24), date(2026, 7, 23))
    with pytest.raises(ValueError, match="negative"):
        add_working_days(calendar, date(2026, 7, 23), -1)
    empty = standard_calendar(weekday_hours={})
    with pytest.raises(ValueError, match="no working day"):
        next_working_day(empty, date(2026, 7, 23), search_limit_days=10)
