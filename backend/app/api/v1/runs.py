"""Planning run, trace, cancellation, and clarification endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.db.session import get_db
from app.schemas.run import (
    AgentRunStepView,
    AgentRunView,
    ClarificationAnswerRequest,
    ClarificationResumeView,
    ClarificationView,
    PlanningRunRequest,
)
from app.services.runs import (
    ClarificationValidationError,
    PlanningRunService,
    RunConflictError,
    RunNotFoundError,
)

router = APIRouter(tags=["planning-runs"])


def _service(request: Request, auth: AuthContext, db: Session) -> PlanningRunService:
    return PlanningRunService(
        db,
        auth.user.id,
        getattr(request.state, "request_id", "unknown"),
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Planning resource not found.")


@router.post(
    "/projects/{project_id}/planning-runs",
    response_model=AgentRunView,
    status_code=status.HTTP_201_CREATED,
)
def start_planning_run(
    project_id: UUID,
    payload: PlanningRunRequest,
    request: Request,
    idempotency_key: str = Header(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        alias="Idempotency-Key",
    ),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AgentRunView:
    try:
        run = _service(request, auth, db).start(project_id, idempotency_key, payload)
    except RunNotFoundError as error:
        raise _not_found() from error
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AgentRunView.model_validate(run)


@router.get("/agent-runs/{run_id}", response_model=AgentRunView)
def get_agent_run(
    run_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> AgentRunView:
    try:
        return AgentRunView.model_validate(_service(request, auth, db).get(run_id))
    except RunNotFoundError as error:
        raise _not_found() from error


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunView)
def cancel_agent_run(
    run_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AgentRunView:
    try:
        return AgentRunView.model_validate(_service(request, auth, db).cancel(run_id))
    except RunNotFoundError as error:
        raise _not_found() from error


@router.get("/agent-runs/{run_id}/steps", response_model=list[AgentRunStepView])
def list_agent_run_steps(
    run_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[AgentRunStepView]:
    try:
        steps = _service(request, auth, db).steps(run_id)
    except RunNotFoundError as error:
        raise _not_found() from error
    return [AgentRunStepView.model_validate(item) for item in steps]


@router.get(
    "/projects/{project_id}/clarifications",
    response_model=list[ClarificationView],
)
def list_clarifications(
    project_id: UUID,
    request: Request,
    run_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ClarificationView]:
    try:
        questions = _service(request, auth, db).list_clarifications(project_id, run_id=run_id)
    except RunNotFoundError as error:
        raise _not_found() from error
    return [ClarificationView.model_validate(item) for item in questions]


@router.post(
    "/projects/{project_id}/clarifications",
    response_model=ClarificationResumeView,
)
def answer_clarifications(
    project_id: UUID,
    payload: ClarificationAnswerRequest,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ClarificationResumeView:
    try:
        run, questions, resumed = _service(request, auth, db).answer_clarifications(
            project_id,
            payload.run_id,
            payload.answers,
        )
    except RunNotFoundError as error:
        raise _not_found() from error
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ClarificationValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ClarificationResumeView(
        run=AgentRunView.model_validate(run),
        questions=[ClarificationView.model_validate(item) for item in questions],
        resumed=resumed,
    )
