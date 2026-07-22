from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.db.session import get_db
from app.schemas.project import (
    ConstraintInput,
    ConstraintView,
    ProjectCreate,
    ProjectList,
    ProjectUpdate,
    ProjectView,
    RequirementInput,
    RequirementView,
    WorkCalendarInput,
    WorkCalendarView,
)
from app.services.projects import ProjectConflictError, ProjectNotFoundError, ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _version(if_match: str = Header(alias="If-Match")) -> int:
    try:
        value = int(if_match.strip('"'))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="If-Match must contain a numeric row version."
        ) from exc
    if value < 1:
        raise HTTPException(status_code=422, detail="If-Match must contain a positive row version.")
    return value


def _service(request: Request, auth: AuthContext, db: Session) -> ProjectService:
    return ProjectService(db, auth.user.id, _request_id(request))


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Project not found.")


def _conflict(exc: ProjectConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=ProjectList)
def list_projects(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    after: UUID | None = None,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectList:
    try:
        items, next_cursor = _service(request, auth, db).list_projects(limit=limit, after=after)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return ProjectList(
        items=[ProjectView.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).create(payload)
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)


@router.get("/{project_id}", response_model=ProjectView)
def get_project(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        return ProjectView.model_validate(_service(request, auth, db).get(project_id))
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{project_id}", response_model=ProjectView)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).update(project_id, payload, expected_version)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)


@router.delete("/{project_id}", response_model=ProjectView)
def archive_project(
    project_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).archive(project_id, expected_version)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)


@router.get("/{project_id}/requirements", response_model=list[RequirementView])
def list_requirements(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[RequirementView]:
    try:
        project = _service(request, auth, db).get(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return [RequirementView.model_validate(item) for item in project.requirements]


@router.put("/{project_id}/requirements", response_model=ProjectView)
def replace_requirements(
    project_id: UUID,
    payload: list[RequirementInput],
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).replace_requirements(
            project_id, payload, expected_version
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)


@router.get("/{project_id}/constraints", response_model=list[ConstraintView])
def list_constraints(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ConstraintView]:
    try:
        project = _service(request, auth, db).get(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return [ConstraintView.model_validate(item) for item in project.constraints]


@router.put("/{project_id}/constraints", response_model=ProjectView)
def replace_constraints(
    project_id: UUID,
    payload: list[ConstraintInput],
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).replace_constraints(
            project_id, payload, expected_version
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)


@router.get("/{project_id}/calendar", response_model=WorkCalendarView | None)
def get_calendar(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkCalendarView | None:
    try:
        project = _service(request, auth, db).get(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return WorkCalendarView.model_validate(project.calendars[0]) if project.calendars else None


@router.put("/{project_id}/calendar", response_model=ProjectView)
def replace_calendar(
    project_id: UUID,
    payload: WorkCalendarInput,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ProjectView:
    try:
        project = _service(request, auth, db).replace_calendar(
            project_id, payload, expected_version
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    return ProjectView.model_validate(project)
