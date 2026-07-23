"""Active execution, immutable event history, progress, and health endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.db.session import get_db
from app.schemas.execution import (
    ExecutionBoardView,
    ProjectHealthView,
    ProjectProgressView,
    TaskProgressMutationView,
    TaskProgressUpdateRequest,
    TaskStatusEventView,
    TaskStatusMutationView,
    TaskStatusTransitionRequest,
)
from app.services.execution import (
    ExecutionConflictError,
    ExecutionResourceNotFoundError,
    ExecutionService,
)
from app.services.monitoring import MonitoringResourceNotFoundError

router = APIRouter(tags=["execution"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _version(if_match: str = Header(alias="If-Match")) -> int:
    try:
        value = int(if_match.strip('"'))
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a numeric execution row version.",
        ) from error
    if value < 1:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a positive execution row version.",
        )
    return value


def _idempotency_key(
    value: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
) -> str:
    key = value.strip()
    if len(key) < 8:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain at least 8 non-whitespace characters.",
        )
    return key


def _service(request: Request, auth: AuthContext, db: Session) -> ExecutionService:
    return ExecutionService(db, auth.user.id, _request_id(request))


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail="Active execution resource not found.",
    )


def _conflict(error: ExecutionConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


@router.get("/projects/{project_id}/execution", response_model=ExecutionBoardView)
def get_execution_board(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ExecutionBoardView:
    try:
        return _service(request, auth, db).board(project_id)
    except (ExecutionResourceNotFoundError, MonitoringResourceNotFoundError) as error:
        raise _not_found() from error
    except ExecutionConflictError as error:
        raise _conflict(error) from error


@router.get(
    "/tasks/{task_id}/events",
    response_model=list[TaskStatusEventView],
)
def list_task_status_events(
    task_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TaskStatusEventView]:
    try:
        events = _service(request, auth, db).status_history(task_id)
    except ExecutionResourceNotFoundError as error:
        raise _not_found() from error
    return [TaskStatusEventView.model_validate(item) for item in events]


@router.post("/tasks/{task_id}/status", response_model=TaskStatusMutationView)
def update_task_status(
    task_id: UUID,
    payload: TaskStatusTransitionRequest,
    request: Request,
    expected_version: int = Depends(_version),
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskStatusMutationView:
    try:
        return _service(request, auth, db).transition(
            task_id,
            payload,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except ExecutionResourceNotFoundError as error:
        raise _not_found() from error
    except ExecutionConflictError as error:
        raise _conflict(error) from error


@router.post("/tasks/{task_id}/progress", response_model=TaskProgressMutationView)
def update_task_progress(
    task_id: UUID,
    payload: TaskProgressUpdateRequest,
    request: Request,
    expected_version: int = Depends(_version),
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskProgressMutationView:
    try:
        return _service(request, auth, db).update_progress(
            task_id,
            payload,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except ExecutionResourceNotFoundError as error:
        raise _not_found() from error
    except ExecutionConflictError as error:
        raise _conflict(error) from error


@router.get("/projects/{project_id}/progress", response_model=ProjectProgressView)
def get_project_progress(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectProgressView:
    try:
        return _service(request, auth, db).board(project_id).progress
    except (ExecutionResourceNotFoundError, MonitoringResourceNotFoundError) as error:
        raise _not_found() from error
    except ExecutionConflictError as error:
        raise _conflict(error) from error


@router.get("/projects/{project_id}/health", response_model=ProjectHealthView)
def get_project_health(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectHealthView:
    try:
        return _service(request, auth, db).board(project_id).health
    except (ExecutionResourceNotFoundError, MonitoringResourceNotFoundError) as error:
        raise _not_found() from error
    except ExecutionConflictError as error:
        raise _conflict(error) from error
