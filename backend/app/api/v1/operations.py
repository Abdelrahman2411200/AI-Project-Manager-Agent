"""Authenticated operational limits without exposing other users or infrastructure."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import AuthContext, AuthUsageContext, require_user, require_user_usage
from app.core.config import get_settings
from app.schemas.operations import OwnerQuotaView, SystemCapabilitiesView
from app.services.budgets import quota_from_totals

router = APIRouter(tags=["operations"])


@router.get("/system/capabilities", response_model=SystemCapabilitiesView)
def get_system_capabilities(
    _auth: AuthContext = Depends(require_user),
) -> SystemCapabilitiesView:
    settings = get_settings()
    return SystemCapabilitiesView(
        planning_ai_configured=settings.planning_ai_configured,
        planning_provider=settings.planning_provider,
        planning_model=settings.planning_model,
        planning_run_default_token_budget=settings.planning_run_default_token_budget,
    )


@router.get("/usage/quota", response_model=OwnerQuotaView)
def get_owner_quota(
    usage: AuthUsageContext = Depends(require_user_usage),
) -> OwnerQuotaView:
    quota = quota_from_totals(
        runs_used=usage.runs_used,
        reserved_or_used=usage.tokens_reserved_or_used,
        resets_at=usage.resets_at,
    )
    return OwnerQuotaView.model_validate(quota, from_attributes=True)
