from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.audit import AuditEvent
    from app.db.models.identity import User

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="status_allowed"),
        CheckConstraint("team_size >= 1 AND team_size <= 100", name="team_size_range"),
        CheckConstraint(
            "capacity_hours_per_week > 0 AND capacity_hours_per_week <= 168",
            name="capacity_range",
        ),
        CheckConstraint(
            "deadline IS NULL OR start_date IS NULL OR deadline >= start_date", name="dates_ordered"
        ),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        Index("ix_projects_owner_status_updated", "owner_id", "status", "updated_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    desired_outcome: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    capacity_hours_per_week: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("40.00"), nullable=False
    )
    team_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="projects")
    requirements: Mapped[list["ProjectRequirement"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    constraints: Mapped[list["ProjectConstraint"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    calendars: Mapped[list["WorkCalendar"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="project")

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class ProjectRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_requirements"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('stated', 'suggestion', 'confirmed', 'excluded')", name="kind_allowed"
        ),
        CheckConstraint("source IN ('user', 'agent', 'system')", name="source_allowed"),
        CheckConstraint("status IN ('open', 'confirmed', 'rejected')", name="status_allowed"),
        UniqueConstraint(
            "project_id",
            "normalized_text",
            "kind",
            name="uq_project_requirements_project_text_kind",
        ),
        Index("ix_project_requirements_project_kind", "project_id", "kind"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)

    project: Mapped[Project] = relationship(back_populates="requirements")


class ProjectConstraint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_constraints"
    __table_args__ = (
        CheckConstraint("source IN ('user', 'agent', 'system')", name="source_allowed"),
        Index("ix_project_constraints_project", "project_id"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    constraint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)

    project: Mapped[Project] = relationship(back_populates="constraints")


class WorkCalendar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_calendars"
    __table_args__ = (
        CheckConstraint(
            "parallel_limit >= 1 AND parallel_limit <= 100", name="parallel_limit_range"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="effective_dates_ordered",
        ),
        Index("ix_work_calendars_project_effective", "project_id", "effective_from"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    weekday_hours: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    holidays: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    parallel_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="calendars")
