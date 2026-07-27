"""Authenticated operational limits without exposing other users or infrastructure."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_user
from app.db.session import get_db
from app.schemas.operations import OwnerQuotaView
from app.services.budgets import BudgetService

router = APIRouter(tags=["operations"])


@router.get("/usage/quota", response_model=OwnerQuotaView)
def get_owner_quota(
    auth: AuthContext = Depends(require_user),
    db: Session = Depends(get_db),
) -> OwnerQuotaView:
    quota = BudgetService(db, auth.user.id).quota()
    return OwnerQuotaView.model_validate(quota, from_attributes=True)
