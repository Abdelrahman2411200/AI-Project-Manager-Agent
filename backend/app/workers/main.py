"""Database-backed planning worker entry point."""

from __future__ import annotations

import asyncio
import logging
import signal
import socket
import threading
from contextlib import suppress
from uuid import UUID

from app.ai.openai_provider import OpenAIResponsesProvider
from app.ai.provider import StructuredModelProvider
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.jobs import JobQueue, StaleJobClaimError
from app.workflows.engine import NodeFailure
from app.workflows.planning import PlanningWorkflow

logger = logging.getLogger(__name__)
shutdown_requested = threading.Event()


def _request_shutdown(signum: int, _frame: object) -> None:
    logger.info("worker_shutdown_requested", extra={"signal": signum})
    shutdown_requested.set()


async def _heartbeat(
    job_id: UUID,
    claim_token: UUID,
    settings: Settings,
    *,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.job_heartbeat_seconds)
            return
        except TimeoutError:
            pass
        with SessionLocal() as session:
            try:
                JobQueue(session).heartbeat(
                    job_id,
                    claim_token,
                    lease_seconds=settings.job_lease_seconds,
                )
                session.commit()
            except StaleJobClaimError:
                logger.warning("worker_heartbeat_stale", extra={"job_id": str(job_id)})
                return
            except Exception:
                session.rollback()
                logger.exception("worker_heartbeat_failed", extra={"job_id": str(job_id)})


async def process_one_job(
    provider: StructuredModelProvider,
    settings: Settings,
    *,
    worker_id: str,
) -> bool:
    """Claim and process one job, returning false when the queue is empty."""
    with SessionLocal() as claim_session:
        job = JobQueue(claim_session).claim_next(
            worker_id=worker_id,
            lease_seconds=settings.job_lease_seconds,
        )
        if job is None:
            return False
        job_id = job.id
        run_id = job.run_id
        claim_token = job.claim_token
        if claim_token is None:  # defensive: a claimed row always has a token
            raise RuntimeError("Claimed job is missing its lease token.")
        claim_session.commit()

    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat(job_id, claim_token, settings, stop=stop_heartbeat)
    )
    error_code: str | None = None
    try:
        with SessionLocal() as workflow_session:
            try:
                await PlanningWorkflow(
                    workflow_session,
                    provider,
                    settings,
                ).execute(run_id)
            except NodeFailure as error:
                error_code = error.code
                logger.warning(
                    "planning_run_terminal_failure",
                    extra={"run_id": str(run_id), "failure_code": error.code},
                )
    except Exception:
        error_code = "WORKER_PROCESSING_ERROR"
        logger.exception(
            "worker_job_processing_failed",
            extra={"job_id": str(job_id), "run_id": str(run_id)},
        )
    finally:
        stop_heartbeat.set()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    with SessionLocal() as finish_session:
        queue = JobQueue(finish_session)
        try:
            if error_code == "WORKER_PROCESSING_ERROR":
                queue.fail(
                    job_id,
                    claim_token,
                    error_code=error_code,
                    retryable=True,
                )
            else:
                queue.complete(job_id, claim_token)
            finish_session.commit()
        except StaleJobClaimError:
            finish_session.rollback()
            logger.warning(
                "worker_completion_stale",
                extra={"job_id": str(job_id), "run_id": str(run_id)},
            )
    return True


async def _run_loop(settings: Settings) -> None:
    if settings.openai_api_key is None:
        logger.error("worker_ai_unconfigured")
        return
    provider = OpenAIResponsesProvider(settings)
    worker_id = f"{socket.gethostname()}:{threading.get_native_id()}"
    logger.info(
        "worker_started",
        extra={"environment": settings.app_env, "worker_id": worker_id},
    )
    while not shutdown_requested.is_set():
        processed = await process_one_job(provider, settings, worker_id=worker_id)
        if not processed:
            await asyncio.sleep(settings.job_poll_seconds)
    logger.info("worker_stopped", extra={"worker_id": worker_id})


def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    asyncio.run(_run_loop(settings))


if __name__ == "__main__":
    run()
