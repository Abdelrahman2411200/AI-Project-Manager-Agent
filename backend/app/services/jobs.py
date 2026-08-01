"""Database-backed queue with leases and stale-worker protection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models.run import ACTIVE_RUN_STATUSES, AgentJob, AgentRun


class StaleJobClaimError(RuntimeError):
    pass


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class JobQueue:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        run_id: UUID,
        job_type: str = "planning",
        idempotency_key: str,
        payload_ref: dict[str, str],
        available_at: datetime | None = None,
        max_attempts: int = 3,
    ) -> AgentJob:
        existing = self.session.scalar(
            select(AgentJob).where(AgentJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if (
                existing.run_id != run_id
                or existing.job_type != job_type
                or existing.payload_ref != payload_ref
            ):
                raise ValueError("Job idempotency key conflicts with another payload.")
            return existing
        job = AgentJob(
            run_id=run_id,
            job_type=job_type,
            status="queued",
            idempotency_key=idempotency_key,
            payload_ref=payload_ref,
            available_at=available_at or utc_now(),
            max_attempts=max_attempts,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> AgentJob | None:
        claimed_at = _as_utc(now or utc_now())
        self._reconcile_exhausted_leases(claimed_at)
        query = (
            select(AgentJob)
            .where(
                AgentJob.attempts < AgentJob.max_attempts,
                or_(
                    (AgentJob.status == "queued") & (AgentJob.available_at <= claimed_at),
                    (AgentJob.status == "claimed")
                    & (AgentJob.lease_expires_at.is_not(None))
                    & (AgentJob.lease_expires_at <= claimed_at),
                ),
            )
            .order_by(AgentJob.available_at, AgentJob.created_at, AgentJob.id)
            .limit(1)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = self.session.scalar(query)
        if job is None:
            return None
        job.status = "claimed"
        job.claimed_by = worker_id
        job.claim_token = uuid4()
        job.claimed_at = claimed_at
        job.heartbeat_at = claimed_at
        job.lease_expires_at = claimed_at + timedelta(seconds=lease_seconds)
        job.attempts += 1
        self.session.flush()
        return job

    def heartbeat(
        self,
        job_id: UUID,
        claim_token: UUID,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> AgentJob:
        job = self._claimed(job_id, claim_token)
        heartbeat_at = _as_utc(now or utc_now())
        job.heartbeat_at = heartbeat_at
        job.lease_expires_at = heartbeat_at + timedelta(seconds=lease_seconds)
        self.session.flush()
        return job

    def complete(self, job_id: UUID, claim_token: UUID) -> AgentJob:
        job = self._claimed(job_id, claim_token)
        job.status = "completed"
        self._clear_claim(job)
        self.session.flush()
        return job

    def fail(
        self,
        job_id: UUID,
        claim_token: UUID,
        *,
        error_code: str,
        retryable: bool,
        now: datetime | None = None,
    ) -> AgentJob:
        job = self._claimed(job_id, claim_token)
        job.last_error_code = error_code
        if retryable and job.attempts < job.max_attempts:
            delay_seconds = min(60, 2 ** max(0, job.attempts - 1))
            job.status = "queued"
            job.available_at = _as_utc(now or utc_now()) + timedelta(seconds=delay_seconds)
        else:
            job.status = "failed"
        self._clear_claim(job)
        if job.status == "failed":
            self._fail_active_run(job.run_id, error_code)
        self.session.flush()
        return job

    def cancel_run_jobs(self, run_id: UUID) -> None:
        self.session.execute(
            update(AgentJob)
            .where(AgentJob.run_id == run_id, AgentJob.status.in_(("queued", "claimed")))
            .values(
                status="cancelled",
                claimed_by=None,
                claim_token=None,
                claimed_at=None,
                heartbeat_at=None,
                lease_expires_at=None,
            )
        )

    def _claimed(self, job_id: UUID, claim_token: UUID) -> AgentJob:
        job = self.session.get(AgentJob, job_id)
        if (
            job is None
            or job.status != "claimed"
            or job.claim_token is None
            or job.claim_token != claim_token
        ):
            raise StaleJobClaimError("The job lease is stale or no longer owned by this worker.")
        return job

    def _reconcile_exhausted_leases(self, now: datetime) -> int:
        """Terminalize claims that cannot be reclaimed after their final lease."""

        query = select(AgentJob).where(
            AgentJob.status == "claimed",
            AgentJob.attempts >= AgentJob.max_attempts,
            AgentJob.lease_expires_at.is_not(None),
            AgentJob.lease_expires_at <= now,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        exhausted = list(self.session.scalars(query))
        for job in exhausted:
            error_code = job.last_error_code or "JOB_LEASE_EXHAUSTED"
            job.status = "failed"
            job.last_error_code = error_code
            self._clear_claim(job)
            self._fail_active_run(job.run_id, error_code)
        if exhausted:
            self.session.flush()
        return len(exhausted)

    def _fail_active_run(self, run_id: UUID, error_code: str) -> None:
        run = self.session.get(AgentRun, run_id)
        if run is None or run.status not in ACTIVE_RUN_STATUSES:
            return
        completed_at = utc_now()
        run.status = "failed"
        run.completed_at = completed_at
        run.outcome = {
            "failure_code": error_code,
            "failed_step": run.current_step,
            "recoverable": False,
        }
        state = dict(run.state_snapshot)
        failed_steps = list(state.get("failed_steps", []))
        if run.current_step not in failed_steps:
            failed_steps.append(run.current_step)
        state.update(
            {
                "status": "failed",
                "current_step": run.current_step,
                "failed_steps": failed_steps,
                "updated_at": completed_at.isoformat(),
            }
        )
        run.state_snapshot = state

    @staticmethod
    def _clear_claim(job: AgentJob) -> None:
        job.claimed_by = None
        job.claim_token = None
        job.claimed_at = None
        job.heartbeat_at = None
        job.lease_expires_at = None
