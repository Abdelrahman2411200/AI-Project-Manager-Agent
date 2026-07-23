"""Plan graph CRUD, validation, review, approval, and activation endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.auth.policies import PlanLifecycleConflictError, PlanResourceNotFoundError
from app.db.session import get_db
from app.schemas.plan import (
    ApprovalRequest,
    ChangesRequestedInput,
    DependencyCreate,
    DependencyMutationView,
    DependencyView,
    MilestoneCreate,
    MilestoneMutationView,
    MilestoneUpdate,
    MilestoneView,
    PlanDiffView,
    PlanGraphView,
    PlanMetadataUpdate,
    PlanValidationView,
    PlanVersionSummary,
    TaskCreate,
    TaskMutationView,
    TaskUpdate,
    TaskView,
)
from app.services.approval import ApprovalService
from app.services.plans import PlanGraph, PlanService

router = APIRouter(tags=["plans"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _version(if_match: str = Header(alias="If-Match")) -> int:
    try:
        value = int(if_match.strip('"'))
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a numeric row version.",
        ) from error
    if value < 1:
        raise HTTPException(
            status_code=422,
            detail="If-Match must contain a positive row version.",
        )
    return value


def _service(request: Request, auth: AuthContext, db: Session) -> PlanService:
    return PlanService(db, auth.user.id, _request_id(request))


def _approval(request: Request, auth: AuthContext, db: Session) -> ApprovalService:
    return ApprovalService(db, auth.user.id, _request_id(request))


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Plan resource not found.")


def _conflict(error: PlanLifecycleConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


def _graph_view(graph: PlanGraph) -> PlanGraphView:
    summary = PlanVersionSummary.model_validate(graph.plan).model_dump()
    return PlanGraphView(
        **summary,
        quality_report=graph.plan.quality_report,
        analysis=graph.analysis,
        milestones=graph.milestones,
        tasks=graph.tasks,
        dependencies=graph.dependencies,
        risks=graph.risks,
        approvals=graph.approvals,
    )


@router.get(
    "/projects/{project_id}/plan-versions",
    response_model=list[PlanVersionSummary],
)
def list_plan_versions(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PlanVersionSummary]:
    try:
        plans = _service(request, auth, db).list_versions(project_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return [PlanVersionSummary.model_validate(item) for item in plans]


@router.get("/plan-versions/{version_id}", response_model=PlanGraphView)
def get_plan_version(
    version_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        return _graph_view(_service(request, auth, db).graph(version_id))
    except PlanResourceNotFoundError as error:
        raise _not_found() from error


@router.patch("/plan-versions/{version_id}", response_model=PlanGraphView)
def update_plan_version(
    version_id: UUID,
    payload: PlanMetadataUpdate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        graph = _service(request, auth, db).update_plan(
            version_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return _graph_view(graph)


@router.post("/plan-versions/{version_id}/validate", response_model=PlanValidationView)
def validate_plan_version(
    version_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanValidationView:
    try:
        plan, report = _service(request, auth, db).validate(version_id, expected_version)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return PlanValidationView(
        **report.model_dump(mode="json"),
        content_hash=plan.content_hash,
        row_version=plan.row_version,
    )


@router.post("/plan-versions/{version_id}/submit-review", response_model=PlanGraphView)
def submit_plan_review(
    version_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        graph = _service(request, auth, db).submit_review(version_id, expected_version)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return _graph_view(graph)


@router.post("/plan-versions/{version_id}/request-changes", response_model=PlanGraphView)
def request_plan_changes(
    version_id: UUID,
    payload: ChangesRequestedInput,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        graph = _approval(request, auth, db).request_changes(
            version_id,
            expected_version,
            payload.reason,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return _graph_view(graph)


@router.post("/plan-versions/{version_id}/approve", response_model=PlanGraphView)
def approve_plan_version(
    version_id: UUID,
    payload: ApprovalRequest,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        graph = _approval(request, auth, db).approve_and_activate(
            version_id,
            expected_version,
            payload.content_hash,
            payload.reason,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return _graph_view(graph)


@router.post("/plan-versions/{version_id}/archive", response_model=PlanGraphView)
def archive_plan_version(
    version_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanGraphView:
    try:
        graph = _service(request, auth, db).archive(version_id, expected_version)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return _graph_view(graph)


@router.get(
    "/plan-versions/{from_id}/compare/{to_id}",
    response_model=PlanDiffView,
)
def compare_plan_versions(
    from_id: UUID,
    to_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> PlanDiffView:
    try:
        changes = _service(request, auth, db).compare(from_id, to_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return PlanDiffView(
        from_version_id=from_id,
        to_version_id=to_id,
        changes=changes,
    )


@router.get(
    "/plan-versions/{version_id}/milestones",
    response_model=list[MilestoneView],
)
def list_milestones(
    version_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[MilestoneView]:
    try:
        items = _service(request, auth, db).list_milestones(version_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return [MilestoneView.model_validate(item) for item in items]


@router.post(
    "/plan-versions/{version_id}/milestones",
    response_model=MilestoneMutationView,
    status_code=status.HTTP_201_CREATED,
)
def create_milestone(
    version_id: UUID,
    payload: MilestoneCreate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MilestoneMutationView:
    try:
        item, plan = _service(request, auth, db).create_milestone(
            version_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return MilestoneMutationView(item=item, plan=plan)


@router.patch(
    "/plan-versions/{version_id}/milestones/{milestone_id}",
    response_model=MilestoneMutationView,
)
def update_milestone(
    version_id: UUID,
    milestone_id: UUID,
    payload: MilestoneUpdate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MilestoneMutationView:
    try:
        item, plan = _service(request, auth, db).update_milestone(
            version_id,
            milestone_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return MilestoneMutationView(item=item, plan=plan)


@router.delete(
    "/plan-versions/{version_id}/milestones/{milestone_id}",
    response_model=PlanVersionSummary,
)
def delete_milestone(
    version_id: UUID,
    milestone_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanVersionSummary:
    try:
        plan = _service(request, auth, db).delete_milestone(
            version_id,
            milestone_id,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return PlanVersionSummary.model_validate(plan)


@router.get("/plan-versions/{version_id}/tasks", response_model=list[TaskView])
def list_tasks(
    version_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TaskView]:
    try:
        items = _service(request, auth, db).list_tasks(version_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return [TaskView.model_validate(item) for item in items]


@router.post(
    "/plan-versions/{version_id}/tasks",
    response_model=TaskMutationView,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    version_id: UUID,
    payload: TaskCreate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskMutationView:
    try:
        item, plan = _service(request, auth, db).create_task(
            version_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return TaskMutationView(item=item, plan=plan)


@router.patch(
    "/plan-versions/{version_id}/tasks/{task_id}",
    response_model=TaskMutationView,
)
def update_task(
    version_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaskMutationView:
    try:
        item, plan = _service(request, auth, db).update_task(
            version_id,
            task_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return TaskMutationView(item=item, plan=plan)


@router.delete(
    "/plan-versions/{version_id}/tasks/{task_id}",
    response_model=PlanVersionSummary,
)
def delete_task(
    version_id: UUID,
    task_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanVersionSummary:
    try:
        plan = _service(request, auth, db).delete_task(
            version_id,
            task_id,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return PlanVersionSummary.model_validate(plan)


@router.get(
    "/plan-versions/{version_id}/dependencies",
    response_model=list[DependencyView],
)
def list_dependencies(
    version_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[DependencyView]:
    try:
        items = _service(request, auth, db).list_dependencies(version_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return [DependencyView.model_validate(item) for item in items]


@router.post(
    "/plan-versions/{version_id}/dependencies",
    response_model=DependencyMutationView,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    version_id: UUID,
    payload: DependencyCreate,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> DependencyMutationView:
    try:
        item, plan = _service(request, auth, db).create_dependency(
            version_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return DependencyMutationView(item=item, plan=plan)


@router.delete(
    "/plan-versions/{version_id}/dependencies/{dependency_id}",
    response_model=PlanVersionSummary,
)
def delete_dependency(
    version_id: UUID,
    dependency_id: UUID,
    request: Request,
    expected_version: int = Depends(_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> PlanVersionSummary:
    try:
        plan = _service(request, auth, db).delete_dependency(
            version_id,
            dependency_id,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return PlanVersionSummary.model_validate(plan)
