"""Operational quota contracts safe for authenticated owners."""

from datetime import datetime

from pydantic import BaseModel


class OwnerQuotaView(BaseModel):
    daily_run_limit: int
    runs_used: int
    runs_remaining: int
    daily_token_budget: int
    tokens_reserved_or_used: int
    tokens_remaining: int
    resets_at: datetime


class SystemCapabilitiesView(BaseModel):
    planning_ai_configured: bool
    planning_model: str
