import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.ai.fake_provider import FakeStructuredModelProvider
from app.core.config import get_settings
from app.db.models.insight import Report
from app.db.models.run import AgentJob, AgentRun
from app.db.session import SessionLocal
from app.schemas.insight import ReportCreateRequest
from app.services.reports import ReportService
from app.workers.main import process_one_job
from tests.api.test_execution import _active_fixture
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


def test_worker_executes_reporting_without_ai_as_factual_partial_result() -> None:
    user, _, _, project_id, _ = _active_fixture("report-worker@example.com")
    today = date.today()
    with SessionLocal() as session:
        started = ReportService(session, user.id, "worker-report").start(
            project_id,
            ReportCreateRequest(
                report_type="weekly",
                period_start=today - timedelta(days=6),
                period_end=today,
            ),
            idempotency_key="worker-weekly-report",
        )
        for queued in session.scalars(
            select(AgentJob).where(
                AgentJob.run_id != started.run_id,
                AgentJob.status == "queued",
            )
        ):
            queued.status = "completed"
        session.commit()

    assert asyncio.run(process_one_job(None, get_settings(), worker_id="report-worker"))
    with SessionLocal() as session:
        run = session.get(AgentRun, started.run_id)
        job = session.scalar(select(AgentJob).where(AgentJob.run_id == started.run_id))
        report = session.scalar(select(Report).where(Report.run_id == started.run_id))
        assert run is not None and run.status == "partial"
        assert run.outcome is not None
        assert run.outcome["narrative_failure_code"] == "AI_UNCONFIGURED"
        assert job is not None and job.status == "completed"
        assert report is not None and report.status == "partial"
