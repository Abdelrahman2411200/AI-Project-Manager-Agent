"""Authenticated operational limits without exposing other users or infrastructure."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import AuthUsageContext, require_user_usage
from app.schemas.operations import OwnerQuotaView
from app.services.budgets import quota_from_totals

router = APIRouter(tags=["operations"])


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
