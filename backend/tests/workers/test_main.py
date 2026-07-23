import asyncio

from sqlalchemy import select

from app.ai.fake_provider import FakeStructuredModelProvider
from app.core.config import get_settings
from app.db.models.run import AgentJob, AgentRun
from app.db.session import SessionLocal
from app.workers.main import process_one_job
from tests.workflows.test_planning import _outputs, _started_run


def test_worker_claims_executes_and_completes_planning_job() -> None:
    run_id, _ = _started_run("worker-owner@example.com")
    processed = asyncio.run(
        process_one_job(
            FakeStructuredModelProvider(_outputs()),
            get_settings(),
            worker_id="test-worker",
        )
    )
    assert processed
    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        job = session.scalar(select(AgentJob).where(AgentJob.run_id == run_id))
        assert run is not None
        assert run.status == "completed"
        assert job is not None
        assert job.status == "completed"
        assert job.claim_token is None
