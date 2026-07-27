"""Persistent reporting workflow with deterministic factual fallback."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import StructuredModelError, StructuredModelProvider
from app.core.config import Settings
from app.db.base import utc_now
from app.db.models.run import AgentRun, AgentRunStep
from app.schemas.insight import FactualReportData
from app.services.reports import ReportGroundingError, ReportService
from app.services.telemetry import TelemetryRecorder


class ReportingWorkflow:
    def __init__(
        self,
        session: Session,
        provider: StructuredModelProvider | None,
        settings: Settings,
    ) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings

    async def execute(self, run_id: UUID) -> AgentRun:
        run = self.session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None or run.workflow != "reporting":
            raise ValueError("Reporting run not found.")
        if run.status in {"completed", "partial"} and run.outcome is not None:
            return run
        request_id = f"run:{run.id}"
        service = ReportService(self.session, run.initiator_id, request_id)
        data = FactualReportData.model_validate(run.candidate_data["report_data"])
        run.status = "running"
        run.started_at = run.started_at or utc_now()
        run.current_step = "report.aggregate"
        self._step(
            run,
            name="report.aggregate",
            mode="deterministic",
            status="completed",
            purpose="Validate the immutable factual ReportData captured at report start.",
            input_hash=run.candidate_data["report_input_hash"],
            output_refs=[
                {
                    "entity_type": "ReportData",
                    "entity_id": str(run.id),
                    "content_hash": run.candidate_data["report_input_hash"],
                }
            ],
        )
        narrative = None
        failure_code: str | None = None
        claim_errors: list[str] = []
        usage_total = 0
        if self.provider is None:
            failure_code = "AI_UNCONFIGURED"
            self._step(
                run,
                name="report.narrate",
                mode="llm",
                status="skipped",
                purpose="Create schema-constrained prose using ReportData only.",
                input_hash=run.candidate_data["report_input_hash"],
                failure_code=failure_code,
            )
            TelemetryRecorder(self.session).append(
                name="narrative.provider_failed",
                owner_id=run.initiator_id,
                request_id=request_id,
                project_id=run.project_id,
                run_id=run.id,
                attributes={"workflow": "reporting", "error_code": failure_code},
            )
        else:
            run.current_step = "report.narrate"
            try:
                narrative, usage = await service.generate_narrative(
                    data,
                    self.provider,
                    self.settings,
                    run_id=run.id,
                )
                usage_total = usage.total_tokens
                self._step(
                    run,
                    name="report.narrate",
                    mode="llm",
                    status="completed",
                    purpose="Create schema-constrained prose using ReportData only.",
                    input_hash=run.candidate_data["report_input_hash"],
                    usage={
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "reasoning_tokens": usage.reasoning_tokens,
                        "total_tokens": usage.total_tokens,
                    },
                )
                self._step(
                    run,
                    name="report.validate_claims",
                    mode="deterministic",
                    status="completed",
                    purpose="Require every narrative fact to match cited ReportData evidence.",
                    input_hash=run.candidate_data["report_input_hash"],
                )
            except ReportGroundingError as error:
                failure_code = "UNSUPPORTED_CLAIMS"
                claim_errors = error.errors
                self._step(
                    run,
                    name="report.validate_claims",
                    mode="deterministic",
                    status="failed",
                    purpose="Require every narrative fact to match cited ReportData evidence.",
                    input_hash=run.candidate_data["report_input_hash"],
                    failure_code=failure_code,
                    validation=[
                        {"code": "UNSUPPORTED_CLAIM", "detail": item} for item in claim_errors
                    ],
                )
                TelemetryRecorder(self.session).append(
                    name="narrative.validation_failed",
                    owner_id=run.initiator_id,
                    request_id=request_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    attributes={
                        "workflow": "reporting",
                        "error_count": len(claim_errors),
                    },
                )
            except StructuredModelError as error:
                failure_code = error.code.value.upper()
                self._step(
                    run,
                    name="report.narrate",
                    mode="llm",
                    status="failed",
                    purpose="Create schema-constrained prose using ReportData only.",
                    input_hash=run.candidate_data["report_input_hash"],
                    failure_code=failure_code,
                    retryable=error.retryable,
                )
                TelemetryRecorder(self.session).append(
                    name="narrative.provider_failed",
                    owner_id=run.initiator_id,
                    request_id=request_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    attributes={
                        "workflow": "reporting",
                        "error_code": failure_code,
                        "retryable": error.retryable,
                    },
                )
        run.tokens_used = usage_total
        run.current_step = "report.persist"
        report = service.persist(
            run,
            data,
            narrative=narrative,
            failure_code=failure_code,
        )
        self._step(
            run,
            name="report.persist",
            mode="transactional",
            status="completed",
            purpose="Persist immutable factual JSON and sanitized Markdown.",
            input_hash=run.candidate_data["report_input_hash"],
            output_refs=[
                {
                    "entity_type": "Report",
                    "entity_id": str(report.id),
                    "content_hash": report.content_hash,
                }
            ],
        )
        run.status = report.status
        run.completed_at = utc_now()
        run.outcome = {
            "report_id": str(report.id),
            "content_hash": report.content_hash,
            "status": report.status,
            "narrative_failure_code": failure_code,
        }
        completed_steps = ["report.aggregate", "report.persist"]
        if narrative is not None:
            completed_steps.extend(["report.narrate", "report.validate_claims"])
        failed_steps = []
        if failure_code and failure_code != "AI_UNCONFIGURED":
            failed_steps.append(
                "report.validate_claims"
                if failure_code == "UNSUPPORTED_CLAIMS"
                else "report.narrate"
            )
        run.state_snapshot = {
            **run.state_snapshot,
            "status": run.status,
            "current_step": "report.persist",
            "report_data_ref": run.candidate_data["report_input_hash"],
            "narrative_ref": (report.content_hash if narrative is not None else None),
            "report_id": str(report.id),
            "claim_validation_errors": claim_errors,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "updated_at": utc_now().isoformat(),
        }
        self.session.commit()
        return run

    def _step(
        self,
        run: AgentRun,
        *,
        name: str,
        mode: str,
        status: str,
        purpose: str,
        input_hash: str,
        output_refs: list[dict[str, Any]] | None = None,
        validation: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        failure_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        existing = self.session.scalar(
            select(AgentRunStep).where(
                AgentRunStep.run_id == run.id,
                AgentRunStep.name == name,
                AgentRunStep.attempt == 1,
            )
        )
        if existing is not None:
            return
        self.session.add(
            AgentRunStep(
                run_id=run.id,
                name=name,
                mode=mode,
                purpose=purpose,
                attempt=1,
                status=status,
                input_hash=input_hash,
                idempotency_key=f"{run.id}:{name}:1",
                input_refs=[
                    {
                        "entity_type": "ReportData",
                        "entity_id": str(run.id),
                        "content_hash": input_hash,
                    }
                ],
                output_refs=output_refs or [],
                validation=validation or [],
                usage=usage or {},
                failure_code=failure_code,
                retryable=retryable,
                completed_at=utc_now(),
                duration_ms=0,
            )
        )
