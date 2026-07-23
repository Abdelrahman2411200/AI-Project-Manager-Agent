from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RequirementKind = Literal["stated", "suggestion", "confirmed", "excluded"]
RequirementSource = Literal["user", "agent", "system"]
RequirementStatus = Literal["open", "confirmed", "rejected"]


class RequirementInput(BaseModel):
    kind: RequirementKind = "stated"
    text: str = Field(min_length=1, max_length=2000)
    source: RequirementSource = "user"
    status: RequirementStatus = "open"

    @field_validator("text")
    @classmethod
    def normalize_visible_text(cls, value: str) -> str:
        return " ".join(value.split())


class ConstraintInput(BaseModel):
    constraint_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    value_json: dict[str, Any]
    source: RequirementSource = "user"
    confirmed: bool = False


class WorkCalendarInput(BaseModel):
    weekday_hours: dict[str, float] = Field(
        default_factory=lambda: {
            "monday": 8.0,
            "tuesday": 8.0,
            "wednesday": 8.0,
            "thursday": 8.0,
            "friday": 8.0,
        }
    )
    holidays: list[date] = Field(default_factory=list, max_length=366)
    effective_from: date | None = None
    effective_to: date | None = None
    parallel_limit: int = Field(default=1, ge=1, le=100)

    @field_validator("weekday_hours")
    @classmethod
    def validate_weekday_hours(cls, value: dict[str, float]) -> dict[str, float]:
        allowed = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        if not value or not set(value).issubset(allowed):
            raise ValueError("weekday_hours must use recognized weekday names")
        if any(hours < 0 or hours > 24 for hours in value.values()):
            raise ValueError("weekday hours must be between 0 and 24")
        return value

    @model_validator(mode="after")
    def validate_effective_dates(self) -> Self:
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=4000)
    desired_outcome: str | None = Field(default=None, max_length=4000)
    start_date: date | None = None
    deadline: date | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    capacity_hours_per_week: Decimal = Field(default=Decimal("40"), gt=0, le=168)
    team_size: int = Field(default=1, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=8000)
    requirements: list[RequirementInput] = Field(default_factory=list, max_length=100)
    constraints: list[ConstraintInput] = Field(default_factory=list, max_length=50)
    work_calendar: WorkCalendarInput | None = None

    @field_validator("name", "goal")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA identifier") from exc
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.start_date and self.deadline and self.deadline < self.start_date:
            raise ValueError("deadline must not precede start_date")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal: str | None = Field(default=None, min_length=1, max_length=4000)
    desired_outcome: str | None = Field(default=None, max_length=4000)
    start_date: date | None = None
    deadline: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    capacity_hours_per_week: Decimal | None = Field(default=None, gt=0, le=168)
    team_size: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def require_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one project field is required")
        if self.timezone is not None:
            ProjectCreate.validate_timezone(self.timezone)
        return self


class RequirementView(RequirementInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class ConstraintView(ConstraintInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class WorkCalendarView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    weekday_hours: dict[str, float]
    holidays: list[date]
    effective_from: date | None
    effective_to: date | None
    parallel_limit: int


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    goal: str
    desired_outcome: str | None
    start_date: date | None
    deadline: date | None
    timezone: str
    capacity_hours_per_week: Decimal
    team_size: int
    status: str
    notes: str | None
    row_version: int
    created_at: datetime
    updated_at: datetime
    requirements: list[RequirementView]
    constraints: list[ConstraintView]
    calendars: list[WorkCalendarView]


class ProjectList(BaseModel):
    items: list[ProjectView]
    next_cursor: UUID | None = None
