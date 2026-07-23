from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.db.base import utc_now
from app.db.models.project import Project, ProjectConstraint, ProjectRequirement, WorkCalendar
from app.schemas.project import (
    ConstraintInput,
    ProjectCreate,
    ProjectUpdate,
    RequirementInput,
    WorkCalendarInput,
)
from app.services.audit import AuditRecorder


class ProjectNotFoundError(Exception):
    pass


class ProjectConflictError(Exception):
    pass


def normalize_requirement_text(value: str) -> str:
    return " ".join(value.split()).casefold()


class ProjectService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.audit = AuditRecorder(session)

    def _query(self) -> Select[tuple[Project]]:
        return (
            select(Project)
            .where(Project.owner_id == self.owner_id)
            .options(
                selectinload(Project.requirements),
                selectinload(Project.constraints),
                selectinload(Project.calendars),
            )
        )

    def get(self, project_id: UUID) -> Project:
        project = self.session.scalar(self._query().where(Project.id == project_id))
        if project is None:
            raise ProjectNotFoundError
        return project

    def list_projects(
        self, *, limit: int, after: UUID | None = None
    ) -> tuple[list[Project], UUID | None]:
        query = (
            self._query().order_by(Project.created_at.desc(), Project.id.desc()).limit(limit + 1)
        )
        if after is not None:
            cursor_project = self.session.scalar(
                select(Project).where(Project.id == after, Project.owner_id == self.owner_id)
            )
            if cursor_project is None:
                raise ProjectNotFoundError
            query = query.where(
                (Project.created_at < cursor_project.created_at)
                | (
                    (Project.created_at == cursor_project.created_at)
                    & (Project.id < cursor_project.id)
                )
            )
        projects = list(self.session.scalars(query).all())
        next_cursor = projects[limit - 1].id if len(projects) > limit else None
        return projects[:limit], next_cursor

    def create(self, payload: ProjectCreate) -> Project:
        project = Project(
            owner_id=self.owner_id,
            name=payload.name,
            goal=payload.goal,
            desired_outcome=payload.desired_outcome,
            start_date=payload.start_date,
            deadline=payload.deadline,
            timezone=payload.timezone,
            capacity_hours_per_week=payload.capacity_hours_per_week,
            team_size=payload.team_size,
            notes=payload.notes,
        )
        project.requirements = [self._requirement(item) for item in payload.requirements]
        project.constraints = [self._constraint(item) for item in payload.constraints]
        if payload.work_calendar is not None:
            project.calendars = [self._calendar(payload.work_calendar)]
        self.session.add(project)
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=project.id,
                action="ProjectCreated",
                entity_type="Project",
                entity_id=project.id,
                request_id=self.request_id,
                after_ref={"row_version": project.row_version, "status": project.status},
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as exc:
            self.session.rollback()
            raise ProjectConflictError(
                "Project intake contains duplicate or invalid values."
            ) from exc
        return self.get(project.id)

    def update(self, project_id: UUID, payload: ProjectUpdate, expected_version: int) -> Project:
        project = self.get(project_id)
        self._require_version(project, expected_version)
        values = payload.model_dump(exclude_unset=True)
        start_date = values.get("start_date", project.start_date)
        deadline = values.get("deadline", project.deadline)
        if isinstance(start_date, date) and isinstance(deadline, date) and deadline < start_date:
            raise ProjectConflictError("deadline must not precede start_date")
        before = {"row_version": project.row_version, "status": project.status}
        for field, value in values.items():
            setattr(project, field, value)
        self._commit_mutation(project, "ProjectUpdated", before)
        return self.get(project.id)

    def archive(self, project_id: UUID, expected_version: int) -> Project:
        project = self.get(project_id)
        self._require_version(project, expected_version)
        before = {"row_version": project.row_version, "status": project.status}
        project.status = "archived"
        self._commit_mutation(project, "ProjectArchived", before)
        return self.get(project.id)

    def replace_requirements(
        self, project_id: UUID, items: list[RequirementInput], expected_version: int
    ) -> Project:
        project = self.get(project_id)
        self._require_version(project, expected_version)
        before = {"row_version": project.row_version, "count": len(project.requirements)}
        project.requirements = [self._requirement(item) for item in items]
        self._commit_mutation(project, "RequirementsChanged", before, {"count": len(items)})
        return self.get(project.id)

    def replace_constraints(
        self, project_id: UUID, items: list[ConstraintInput], expected_version: int
    ) -> Project:
        project = self.get(project_id)
        self._require_version(project, expected_version)
        before = {"row_version": project.row_version, "count": len(project.constraints)}
        project.constraints = [self._constraint(item) for item in items]
        self._commit_mutation(project, "ConstraintsChanged", before, {"count": len(items)})
        return self.get(project.id)

    def replace_calendar(
        self, project_id: UUID, item: WorkCalendarInput, expected_version: int
    ) -> Project:
        project = self.get(project_id)
        self._require_version(project, expected_version)
        before = {"row_version": project.row_version, "count": len(project.calendars)}
        project.calendars = [self._calendar(item)]
        self._commit_mutation(project, "WorkCalendarChanged", before, {"count": 1})
        return self.get(project.id)

    def _commit_mutation(
        self,
        project: Project,
        action: str,
        before: dict[str, Any],
        after: dict[str, Any] | None = None,
    ) -> None:
        project.updated_at = utc_now()
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=project.id,
                action=action,
                entity_type="Project",
                entity_id=project.id,
                request_id=self.request_id,
                before_ref=before,
                after_ref=after or {"row_version": project.row_version, "status": project.status},
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as exc:
            self.session.rollback()
            raise ProjectConflictError("Project change conflicts with persisted data.") from exc

    @staticmethod
    def _require_version(project: Project, expected_version: int) -> None:
        if project.row_version != expected_version:
            raise ProjectConflictError(
                "Project version conflict: "
                f"expected {expected_version}, current {project.row_version}."
            )

    @staticmethod
    def _requirement(item: RequirementInput) -> ProjectRequirement:
        return ProjectRequirement(
            kind=item.kind,
            text=item.text,
            normalized_text=normalize_requirement_text(item.text),
            source=item.source,
            status=item.status,
        )

    @staticmethod
    def _constraint(item: ConstraintInput) -> ProjectConstraint:
        return ProjectConstraint(
            constraint_type=item.constraint_type,
            value_json=item.value_json,
            source=item.source,
            confirmed=item.confirmed,
        )

    @staticmethod
    def _calendar(item: WorkCalendarInput) -> WorkCalendar:
        return WorkCalendar(
            weekday_hours=item.weekday_hours,
            holidays=[holiday.isoformat() for holiday in item.holidays],
            effective_from=item.effective_from,
            effective_to=item.effective_to,
            parallel_limit=item.parallel_limit,
        )
