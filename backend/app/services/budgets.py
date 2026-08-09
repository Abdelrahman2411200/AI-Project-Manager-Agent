"""Per-owner admission budgets with safe reservation for queued and active runs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.identity import User
from app.db.models.run import ACTIVE_RUN_STATUSES, AgentRun


class BudgetExceededError(RuntimeError):
    def __init__(self, code: str, detail: str, *, retry_after: int) -> None:
        super().__init__(detail)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class OwnerQuota:
    daily_run_limit: int
    runs_used: int
    runs_remaining: int
    daily_token_budget: int
    tokens_reserved_or_used: int
    tokens_remaining: int
    resets_at: datetime


def quota_from_totals(
    *,
    runs_used: int,
    reserved_or_used: int,
    resets_at: datetime,
) -> OwnerQuota:
    settings = get_settings()
    return OwnerQuota(
        daily_run_limit=settings.user_daily_run_limit,
        runs_used=runs_used,
        runs_remaining=max(0, settings.user_daily_run_limit - runs_used),
        daily_token_budget=settings.user_daily_token_budget,
        tokens_reserved_or_used=reserved_or_used,
        tokens_remaining=max(0, settings.user_daily_token_budget - reserved_or_used),
        resets_at=resets_at,
    )


class BudgetService:
    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def assert_can_start(self, requested_tokens: int) -> OwnerQuota:
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._serialize_owner_admission(day_start.date())
        owner_exists = self.session.scalar(select(User.id).where(User.id == self.owner_id))
        if owner_exists is None:
            raise LookupError("Owner no longer exists.")
        quota = self.quota(now=now)
        retry_after = max(1, int((quota.resets_at - now).total_seconds()))
        if quota.runs_remaining <= 0:
            raise BudgetExceededError(
                "daily_run_limit_exceeded",
                "Daily AI workflow run limit has been reached.",
                retry_after=retry_after,
            )
        if requested_tokens > quota.tokens_remaining:
            raise BudgetExceededError(
                "daily_token_budget_exceeded",
                "Daily AI token budget cannot reserve this run.",
                retry_after=retry_after,
            )
        return quota

    def quota(self, *, now: datetime | None = None) -> OwnerQuota:
        now = now or datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        resets_at = day_start + timedelta(days=1)
        reserved_tokens = case(
            (
                AgentRun.status.in_(ACTIVE_RUN_STATUSES),
                AgentRun.token_budget,
            ),
            else_=AgentRun.tokens_used,
        )
        runs_used, reserved_or_used = self.session.execute(
            select(
                func.count(AgentRun.id),
                func.coalesce(func.sum(reserved_tokens), 0),
            ).where(
                AgentRun.initiator_id == self.owner_id,
                AgentRun.created_at >= day_start,
            )
        ).one()
        runs_used = int(runs_used)
        reserved_or_used = int(reserved_or_used)
        return quota_from_totals(
            runs_used=runs_used,
            reserved_or_used=reserved_or_used,
            resets_at=resets_at,
        )

    def _serialize_owner_admission(self, quota_day: date) -> None:
        """Serialize only competing admissions, without locking the user FK row."""

        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            self.session.execute(
                select(func.pg_advisory_xact_lock(_admission_lock_key(self.owner_id, quota_day)))
            )
            return
        # SQLite serializes writers itself. Other supported development engines
        # retain the previous row-lock behavior where FOR UPDATE is available.
        self.session.scalar(select(User.id).where(User.id == self.owner_id).with_for_update())


def _admission_lock_key(owner_id: UUID, quota_day: date) -> int:
    payload = f"planning-admission:{owner_id}:{quota_day.isoformat()}".encode("ascii")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big", signed=True)
