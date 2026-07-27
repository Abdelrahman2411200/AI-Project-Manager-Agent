"""Grounded recommendations, immutable factual reports, and safe Markdown export."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.db.session import get_db
from app.schemas.insight import (
    RecommendationDecisionRequest,
    RecommendationView,
    ReportCreateRequest,
    ReportStartView,
    ReportSummaryView,
    ReportView,
)
from app.services.budgets import BudgetExceededError
from app.services.recommendations import (
    RecommendationConflictError,
    RecommendationNotFoundError,
    RecommendationService,
)
from app.services.reports import (
    ReportConflictError,
    ReportNotFoundError,
    ReportService,
)

router = APIRouter(tags=["insights"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _idempotency_key(
    value: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> str:
    return value


def _version(if_match: str = Header(alias="If-Match")) -> int:
    try:
        value = int(if_match.strip('"'))
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="If-Match must be a numeric row version."
        ) from error
    if value < 1:
        raise HTTPException(status_code=422, detail="If-Match must be positive.")
    return value


def _recommendations(request: Request, auth: AuthContext, db: Session) -> RecommendationService:
    return RecommendationService(db, auth.user.id, _request_id(request))


def _reports(request: Request, auth: AuthContext, db: Session) -> ReportService:
    return ReportService(db, auth.user.id, _request_id(request))


@router.get(
    "/projects/{project_id}/recommendations",
    response_model=list[RecommendationView],
)
def list_recommendations(
    project_id: UUID,
    request: Request,
    state_filter: Literal["open", "accepted", "dismissed", "deferred"] | None = Query(
        default=None,
        alias="state",
    ),
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[RecommendationView]:
    try:
        return _recommendations(request, auth, db).list(project_id, state=state_filter)
    except RecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Recommendation resource not found.") from error


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationView)
def get_recommendation(
    recommendation_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> RecommendationView:
    try:
        return _recommendations(request, auth, db).get(recommendation_id)
    except RecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Recommendation resource not found.") from error


@router.post(
    "/recommendations/{recommendation_id}/decisions/{decision}",
    response_model=RecommendationView,
)
def decide_recommendation(
    recommendation_id: UUID,
    decision: Literal["accept", "dismiss", "defer"],
    payload: RecommendationDecisionRequest,
    request: Request,
    expected_version: int = Depends(_version),
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RecommendationView:
    try:
        return _recommendations(request, auth, db).decide(
            recommendation_id,
            decision,
            payload,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except RecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Recommendation resource not found.") from error
    except RecommendationConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/projects/{project_id}/reports", response_model=list[ReportSummaryView])
def list_reports(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ReportSummaryView]:
    try:
        return _reports(request, auth, db).list(project_id)
    except ReportNotFoundError as error:
        raise HTTPException(status_code=404, detail="Report resource not found.") from error


@router.post(
    "/projects/{project_id}/reports",
    response_model=ReportStartView,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_report(
    project_id: UUID,
    payload: ReportCreateRequest,
    request: Request,
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ReportStartView:
    try:
        return _reports(request, auth, db).start(
            project_id,
            payload,
            idempotency_key=idempotency_key,
        )
    except ReportNotFoundError as error:
        raise HTTPException(status_code=404, detail="Report resource not found.") from error
    except ReportConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except BudgetExceededError as error:
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after), "X-Error-Code": error.code},
        ) from error


@router.get("/reports/{report_id}", response_model=ReportView)
def get_report(
    report_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ReportView:
    try:
        return _reports(request, auth, db).get(report_id)
    except ReportNotFoundError as error:
        raise HTTPException(status_code=404, detail="Report resource not found.") from error


@router.get("/reports/{report_id}/export.md")
def export_report_markdown(
    report_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        markdown, filename = _reports(request, auth, db).export_markdown(report_id)
    except ReportNotFoundError as error:
        raise HTTPException(status_code=404, detail="Report resource not found.") from error
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
