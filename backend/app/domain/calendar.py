from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class WorkCalendar:
    timezone: str
    weekday_hours: dict[int, Decimal]
    holidays: frozenset[date] = frozenset()
    effective_from: date | None = None
    effective_to: date | None = None
    availability_factor: Decimal = Decimal(1)
    parallel_limit: int = 1
    day_start_local: time = time(9)

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {self.timezone}.") from exc
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Calendar effective_to cannot precede effective_from.")
        if not 0 < self.availability_factor <= 1:
            raise ValueError("Availability factor must be greater than 0 and at most 1.")
        if self.parallel_limit < 1:
            raise ValueError("Parallel limit must be at least 1.")
        for weekday, hours in self.weekday_hours.items():
            if weekday not in range(7):
                raise ValueError("Weekday keys must be integers from 0 (Monday) to 6 (Sunday).")
            if hours < 0 or hours > 24:
                raise ValueError("Working hours must be between 0 and 24 per day.")


@dataclass(frozen=True, slots=True)
class WorkingDay:
    day: date
    start_utc: datetime
    end_utc: datetime
    nominal_hours: Decimal
    effective_hours: Decimal


def is_working_day(calendar: WorkCalendar, day: date) -> bool:
    if calendar.effective_from and day < calendar.effective_from:
        return False
    if calendar.effective_to and day > calendar.effective_to:
        return False
    return (
        day not in calendar.holidays and calendar.weekday_hours.get(day.weekday(), Decimal(0)) > 0
    )


def working_day(calendar: WorkCalendar, day: date) -> WorkingDay | None:
    if not is_working_day(calendar, day):
        return None
    timezone = ZoneInfo(calendar.timezone)
    nominal_hours = calendar.weekday_hours[day.weekday()]
    local_start = datetime.combine(day, calendar.day_start_local, tzinfo=timezone)
    local_end = local_start + timedelta(hours=float(nominal_hours))
    return WorkingDay(
        day=day,
        start_utc=local_start.astimezone(UTC),
        end_utc=local_end.astimezone(UTC),
        nominal_hours=nominal_hours,
        effective_hours=nominal_hours * calendar.availability_factor,
    )


def expand_working_days(
    calendar: WorkCalendar,
    start: date,
    end: date,
) -> tuple[WorkingDay, ...]:
    if end < start:
        raise ValueError("End date cannot precede start date.")
    result: list[WorkingDay] = []
    cursor = start
    while cursor <= end:
        slot = working_day(calendar, cursor)
        if slot is not None:
            result.append(slot)
        cursor += timedelta(days=1)
    return tuple(result)


def next_working_day(
    calendar: WorkCalendar,
    day: date,
    *,
    include_day: bool = True,
    search_limit_days: int = 3660,
) -> date:
    cursor = day if include_day else day + timedelta(days=1)
    for _ in range(search_limit_days + 1):
        if is_working_day(calendar, cursor):
            return cursor
        cursor += timedelta(days=1)
    raise ValueError("Calendar has no working day within the search horizon.")


def add_working_days(
    calendar: WorkCalendar,
    day: date,
    count: int,
) -> date:
    if count < 0:
        raise ValueError("Working-day count cannot be negative.")
    if count == 0:
        return day
    cursor = day
    remaining = count
    while remaining:
        cursor = next_working_day(calendar, cursor, include_day=False)
        remaining -= 1
    return cursor


def count_working_days(
    calendar: WorkCalendar,
    start: date,
    end: date,
    *,
    include_start: bool = True,
    include_end: bool = True,
) -> int:
    if end < start:
        return -count_working_days(
            calendar,
            end,
            start,
            include_start=include_end,
            include_end=include_start,
        )
    cursor = start
    count = 0
    while cursor <= end:
        if (
            (include_start or cursor != start)
            and (include_end or cursor != end)
            and is_working_day(calendar, cursor)
        ):
            count += 1
        cursor += timedelta(days=1)
    return count
