from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models.run import AgentJob, AgentRun
from app.db.session import SessionLocal
from app.schemas.run import PlanningRunRequest
from app.services.jobs import JobQueue, StaleJobClaimError
from app.services.runs import PlanningRunService
from tests.api.test_projects import (
    create_user_and_client,
    project_payload,
    write_headers,
)


def _queued_job() -> AgentJob:
    user, client, csrf = create_user_and_client(f"jobs-{uuid4()}@example.com")
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(csrf),
        ).json()
    with SessionLocal() as session:
        run = PlanningRunService(session, user.id, "job-test").start(
            UUID(project["id"]),
            f"job-run-{uuid4()}",
            PlanningRunRequest(),
        )
        job = session.query(AgentJob).filter(AgentJob.run_id == run.id).one()
        session.expunge(job)
        return job


def test_claim_heartbeat_complete_and_stale_token_protection() -> None:
    queued = _queued_job()
    now = queued.available_at + timedelta(seconds=1)
    with SessionLocal() as session:
        queue = JobQueue(session)
        claimed = queue.claim_next(worker_id="worker-a", lease_seconds=90, now=now)
        assert claimed is not None
        assert claimed.id == queued.id
        assert claimed.attempts == 1
        token = claimed.claim_token
        assert token is not None
        queue.heartbeat(
            claimed.id,
            token,
            lease_seconds=90,
            now=now + timedelta(seconds=15),
        )
        assert claimed.lease_expires_at.replace(tzinfo=None) == now + timedelta(seconds=105)
        queue.complete(claimed.id, token)
        session.commit()
        assert claimed.status == "completed"
        with pytest.raises(StaleJobClaimError):
            queue.complete(claimed.id, token)


def test_expired_lease_is_reclaimed_and_old_worker_cannot_commit() -> None:
    queued = _queued_job()
    now = queued.available_at + timedelta(seconds=1)
    with SessionLocal() as session:
        queue = JobQueue(session)
        first = queue.claim_next(worker_id="worker-a", lease_seconds=30, now=now)
        assert first is not None
        first_token = first.claim_token
        assert first_token is not None
        session.commit()

        reclaimed = queue.claim_next(
            worker_id="worker-b",
            lease_seconds=30,
            now=now + timedelta(seconds=31),
        )
        assert reclaimed is not None
        assert reclaimed.id == first.id
        assert reclaimed.claim_token != first_token
        assert reclaimed.attempts == 2
        with pytest.raises(StaleJobClaimError):
            queue.complete(reclaimed.id, first_token)


def test_job_retry_backoff_and_idempotent_enqueue() -> None:
    queued = _queued_job()
    now = queued.available_at + timedelta(seconds=1)
    with SessionLocal() as session:
        queue = JobQueue(session)
        claimed = queue.claim_next(worker_id="worker-a", lease_seconds=30, now=now)
        assert claimed is not None
        token = claimed.claim_token
        assert token is not None
        queue.fail(
            claimed.id,
            token,
            error_code="TEMPORARY",
            retryable=True,
            now=now,
        )
        assert claimed.status == "queued"
        assert claimed.available_at.replace(tzinfo=None) == now + timedelta(seconds=1)

        run = session.get(AgentRun, queued.run_id)
        assert run is not None
        duplicate = queue.enqueue(
            run_id=run.id,
            idempotency_key="test-idempotent-job",
            payload_ref={"run_id": str(run.id)},
        )
        same = queue.enqueue(
            run_id=run.id,
            idempotency_key="test-idempotent-job",
            payload_ref={"run_id": str(run.id)},
        )
        assert same.id == duplicate.id
        with pytest.raises(ValueError):
            queue.enqueue(
                run_id=run.id,
                idempotency_key="test-idempotent-job",
                payload_ref={"run_id": str(uuid4())},
            )
