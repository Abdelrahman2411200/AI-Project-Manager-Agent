"""Full-version intelligence endpoints with explicit virtual/approval semantics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_csrf, require_user
from app.auth.policies import PlanLifecycleConflictError, PlanResourceNotFoundError
from app.db.models.advanced import RiskRelation
from app.db.models.plan import Risk
from app.db.session import get_db
from app.schemas.advanced import (
    AdvancedRiskView,
    PlanComparisonView,
    RegenerationCreate,
    RegenerationDecision,
    RegenerationProposalView,
    RiskCreate,
    RiskMutationView,
    RiskRelationView,
    RiskUpdate,
    ScenarioCreate,
    ScenarioView,
)
from app.services.advanced import AdvancedIntelligenceService

router = APIRouter(tags=["advanced-intelligence"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _service(
    request: Request,
    auth: AuthContext,
    db: Session,
) -> AdvancedIntelligenceService:
    return AdvancedIntelligenceService(db, auth.user.id, _request_id(request))


def _idempotency_key(
    value: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
) -> str:
    return value


def _proposal_version(if_match: str = Header(alias="If-Match")) -> int:
    try:
        value = int(if_match.strip('"'))
    except ValueError as error:
        raise HTTPException(422, "If-Match must contain a numeric row version.") from error
    if value < 1:
        raise HTTPException(422, "If-Match must contain a positive row version.")
    return value


def _not_found() -> HTTPException:
    return HTTPException(404, "Advanced intelligence resource not found.")


def _conflict(error: PlanLifecycleConflictError) -> HTTPException:
    return HTTPException(409, str(error))


def _risk_view(risk: Risk, relations: list[RiskRelation]) -> AdvancedRiskView:
    return AdvancedRiskView(
        id=risk.id,
        version_id=risk.version_id,
        stable_key=risk.stable_key,
        category=risk.category,
        description=risk.description,
        probability=risk.probability,
        impact=risk.impact,
        severity=risk.severity,
        trigger=risk.trigger,
        mitigation=risk.mitigation,
        contingency=risk.contingency,
        source_fact_refs=risk.source_fact_refs,
        status=risk.status,
        relations=[RiskRelationView.model_validate(item) for item in relations],
    )


@router.get(
    "/plan-versions/{from_id}/compare/{to_id}/impact",
    response_model=PlanComparisonView,
)
def compare_plan_impact(
    from_id: UUID,
    to_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> PlanComparisonView:
    try:
        result = _service(request, auth, db).compare(from_id, to_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return PlanComparisonView(
        from_version_id=from_id,
        to_version_id=to_id,
        changes=result["changes"],
        summary=result["summary"],
        schedule_delta_days=result["schedule_delta_days"],
        risk_delta=result["risk_delta"],
        scope_delta=result["scope_delta"],
    )


@router.get(
    "/plan-versions/{version_id}/risks",
    response_model=list[AdvancedRiskView],
)
def list_risks(
    version_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[AdvancedRiskView]:
    try:
        items = _service(request, auth, db).list_risks(version_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return [_risk_view(risk, relations) for risk, relations in items]


@router.post(
    "/plan-versions/{version_id}/risks",
    response_model=RiskMutationView,
    status_code=201,
)
def create_risk(
    version_id: UUID,
    payload: RiskCreate,
    request: Request,
    expected_version: int = Depends(_proposal_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RiskMutationView:
    try:
        risk, relations, plan = _service(request, auth, db).create_risk(
            version_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return RiskMutationView(
        item=_risk_view(risk, relations),
        plan_row_version=plan.row_version,
        plan_content_hash=plan.content_hash,
    )


@router.patch(
    "/plan-versions/{version_id}/risks/{risk_id}",
    response_model=RiskMutationView,
)
def update_risk(
    version_id: UUID,
    risk_id: UUID,
    payload: RiskUpdate,
    request: Request,
    expected_version: int = Depends(_proposal_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RiskMutationView:
    try:
        risk, relations, plan = _service(request, auth, db).update_risk(
            version_id,
            risk_id,
            payload,
            expected_version,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return RiskMutationView(
        item=_risk_view(risk, relations),
        plan_row_version=plan.row_version,
        plan_content_hash=plan.content_hash,
    )


@router.post("/projects/{project_id}/scenarios", response_model=ScenarioView, status_code=201)
def create_scenario(
    project_id: UUID,
    payload: ScenarioCreate,
    request: Request,
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ScenarioView:
    try:
        scenario = _service(request, auth, db).create_scenario(project_id, payload, idempotency_key)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return ScenarioView.model_validate(scenario)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioView)
def get_scenario(
    scenario_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> ScenarioView:
    try:
        scenario = _service(request, auth, db).get_scenario(scenario_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return ScenarioView.model_validate(scenario)


@router.post(
    "/plan-versions/{version_id}/regenerations",
    response_model=RegenerationProposalView,
    status_code=201,
)
def create_regeneration(
    version_id: UUID,
    payload: RegenerationCreate,
    request: Request,
    idempotency_key: str = Depends(_idempotency_key),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RegenerationProposalView:
    try:
        proposal = _service(request, auth, db).propose_regeneration(
            version_id, payload, idempotency_key
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return RegenerationProposalView.model_validate(proposal)


@router.get(
    "/regeneration-proposals/{proposal_id}",
    response_model=RegenerationProposalView,
)
def get_regeneration(
    proposal_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> RegenerationProposalView:
    try:
        proposal = _service(request, auth, db).get_regeneration(proposal_id)
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    return RegenerationProposalView.model_validate(proposal)


@router.post(
    "/regeneration-proposals/{proposal_id}/approve",
    response_model=RegenerationProposalView,
)
def approve_regeneration(
    proposal_id: UUID,
    payload: RegenerationDecision,
    request: Request,
    expected_version: int = Depends(_proposal_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RegenerationProposalView:
    try:
        proposal = _service(request, auth, db).decide_regeneration(
            proposal_id,
            approve=True,
            expected_version=expected_version,
            reason=payload.reason,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return RegenerationProposalView.model_validate(proposal)


@router.post(
    "/regeneration-proposals/{proposal_id}/reject",
    response_model=RegenerationProposalView,
)
def reject_regeneration(
    proposal_id: UUID,
    payload: RegenerationDecision,
    request: Request,
    expected_version: int = Depends(_proposal_version),
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> RegenerationProposalView:
    try:
        proposal = _service(request, auth, db).decide_regeneration(
            proposal_id,
            approve=False,
            expected_version=expected_version,
            reason=payload.reason,
        )
    except PlanResourceNotFoundError as error:
        raise _not_found() from error
    except PlanLifecycleConflictError as error:
        raise _conflict(error) from error
    return RegenerationProposalView.model_validate(proposal)
