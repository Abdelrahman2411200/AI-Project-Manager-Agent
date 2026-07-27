"""Immutable factual report aggregation, grounded narration, persistence, and export."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.prompts.persistence import (
    mark_prompt_used,
    record_provider_usage,
    sync_prompt_catalog,
)
from app.ai.prompts.registry import get_prompt
from app.ai.provider import (
    ModelUsage,
    StructuredModelError,
    StructuredModelProvider,
    StructuredModelRequest,
    make_safety_identifier,
)
from app.ai.schemas.outputs import WeeklyReportNarrative
from app.core.config import Settings
from app.core.hashing import canonical_hash
from app.db.models.execution import TaskExecutionProjection, TaskStatusEvent
from app.db.models.insight import Report
from app.db.models.plan import PlanVersion, Risk, Task
from app.db.models.project import Project
from app.db.models.run import AgentRun
from app.domain.grounding import validate_weekly_narrative
from app.reports.sanitize import render_markdown, safe_filename
from app.schemas.insight import (
    EvidenceFact,
    FactualReportData,
    ReportCreateRequest,
    ReportStartView,
    ReportSummaryView,
    ReportView,
)
from app.services.audit import AuditRecorder
from app.services.jobs import JobQueue
from app.services.monitoring import MonitoringService
from app.services.telemetry import TelemetryRecorder


class ReportNotFoundError(LookupError):
    pass


class ReportConflictError(RuntimeError):
    pass


class ReportGroundingError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Report narrative failed claim validation.")
        self.errors = errors


class ReportService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.audit = AuditRecorder(session)
        self.telemetry = TelemetryRecorder(session)

    def start(
        self,
        project_id: UUID,
        payload: ReportCreateRequest,
        *,
        idempotency_key: str,
    ) -> ReportStartView:
        project, plan = self._active_plan(project_id)
        self._validate_period(project, payload)
        request_hash = canonical_hash({"project_id": project_id, **payload.model_dump(mode="json")})
        existing_run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.initiator_id == self.owner_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if existing_run is not None:
            if existing_run.workflow != "reporting" or existing_run.input_hash != request_hash:
                raise ReportConflictError(
                    "Idempotency key was already used with another report request."
                )
            report_id = (
                UUID(str(existing_run.outcome["report_id"]))
                if existing_run.outcome and existing_run.outcome.get("report_id")
                else None
            )
            return ReportStartView(
                run_id=existing_run.id,
                status=cast(Any, existing_run.status),
                report_id=report_id,
                duplicate=True,
            )
        data = self.aggregate(project, plan, payload)
        run = AgentRun(
            project_id=project.id,
            initiator_id=self.owner_id,
            workflow="reporting",
            status="queued",
            idempotency_key=idempotency_key,
            input_hash=request_hash,
            token_budget=8_000,
            tokens_used=0,
            current_step="report.validate_period",
            state_snapshot={
                "schema_version": "1.0",
                "workflow": "reporting",
                "status": "queued",
                "current_step": "report.validate_period",
                "active_plan_version_id": str(plan.id),
                "report_type": payload.report_type,
                "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
                "event_cursor": data.event_cursor,
                "report_data_ref": None,
                "narrative_ref": None,
                "report_id": None,
                "export_format": "markdown",
                "claim_validation_errors": [],
                "completed_steps": [],
                "failed_steps": [],
            },
            candidate_data={
                "report_data": data.model_dump(mode="json"),
                "report_input_hash": canonical_hash(data.model_dump(mode="json")),
            },
        )
        self.session.add(run)
        self.session.flush()
        JobQueue(self.session).enqueue(
            run_id=run.id,
            job_type="reporting",
            idempotency_key=f"job:report:{self.owner_id}:{idempotency_key}",
            payload_ref={
                "project_id": str(project.id),
                "version_id": str(plan.id),
                "state_hash": data.state_hash,
            },
        )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=project.id,
            action="ReportStarted",
            entity_type="AgentRun",
            entity_id=run.id,
            request_id=self.request_id,
            after_ref={
                "report_type": payload.report_type,
                "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
                "state_hash": data.state_hash,
            },
        )
        self.telemetry.append(
            name="report.started",
            owner_id=self.owner_id,
            request_id=self.request_id,
            project_id=project.id,
            run_id=run.id,
            attributes={
                "report_type": payload.report_type,
                "period_days": (payload.period_end - payload.period_start).days + 1,
            },
        )
        self.session.commit()
        return ReportStartView(run_id=run.id, status="queued")

    def aggregate(
        self,
        project: Project,
        plan: PlanVersion,
        payload: ReportCreateRequest,
    ) -> FactualReportData:
        snapshot = MonitoringService(self.session, self.owner_id).ensure_current(project.id)
        zone = ZoneInfo(project.timezone)
        start_utc = datetime.combine(payload.period_start, time.min, zone).astimezone(UTC)
        end_utc = datetime.combine(
            payload.period_end + timedelta(days=1), time.min, zone
        ).astimezone(UTC)
        events = list(
            self.session.scalars(
                select(TaskStatusEvent)
                .where(
                    TaskStatusEvent.version_id == plan.id,
                    TaskStatusEvent.occurred_at >= start_utc,
                    TaskStatusEvent.occurred_at < end_utc,
                )
                .order_by(TaskStatusEvent.occurred_at, TaskStatusEvent.id)
            )
        )
        tasks = {
            task.id: (task, projection)
            for task, projection in self.session.execute(
                select(Task, TaskExecutionProjection)
                .join(
                    TaskExecutionProjection,
                    TaskExecutionProjection.task_id == Task.id,
                )
                .where(Task.version_id == plan.id)
            )
        }
        evidence: dict[str, EvidenceFact] = {
            "PERIOD-CURRENT": EvidenceFact(
                entity_type="period",
                entity_ref="PERIOD-CURRENT",
                fact_key="inclusive_period",
                value={
                    "period_start": payload.period_start.isoformat(),
                    "period_end": payload.period_end.isoformat(),
                    "timezone": project.timezone,
                },
            ),
            "METRIC-PROGRESS": EvidenceFact(
                entity_type="metric",
                entity_ref="METRIC-PROGRESS",
                fact_key="weighted_progress",
                value={
                    **snapshot.progress_json["project"],
                    "display_percent": _percent_display(
                        snapshot.progress_json["project"]["fraction"]
                    ),
                },
            ),
            "HEALTH-CURRENT": EvidenceFact(
                entity_type="metric",
                entity_ref="HEALTH-CURRENT",
                fact_key="project_health",
                value={
                    "label": snapshot.health_label,
                    "rule_codes": snapshot.health_json["rule_codes"],
                },
            ),
            "FORECAST-CURRENT": EvidenceFact(
                entity_type="forecast",
                entity_ref="FORECAST-CURRENT",
                fact_key="remaining_work_schedule",
                value=snapshot.schedule_json,
            ),
        }
        completed_refs: list[str] = []
        for item in events:
            task = tasks.get(item.task_id)
            if task is None:
                continue
            task_model, _projection = task
            reference = f"EVENT-{str(item.id).upper()}"
            evidence[reference] = EvidenceFact(
                entity_type="event",
                entity_ref=reference,
                fact_key="task_status_event",
                value={
                    "task_ref": task_model.stable_key,
                    "from_status": item.from_status,
                    "to_status": item.to_status,
                    "occurred_at": item.occurred_at.isoformat(),
                },
            )
            if item.to_status == "completed":
                completed_refs.append(reference)
        blocker_refs: list[str] = []
        next_action_refs: list[str] = []
        for task, projection in tasks.values():
            if projection.status == "blocked":
                blocker_refs.append(task.stable_key)
                evidence[task.stable_key] = EvidenceFact(
                    entity_type="task",
                    entity_ref=task.stable_key,
                    fact_key="blocker",
                    value={
                        "title": task.title,
                        "status": projection.status,
                        "reason": projection.blocked_reason,
                    },
                )
            elif projection.status == "ready":
                next_action_refs.append(task.stable_key)
                evidence[task.stable_key] = EvidenceFact(
                    entity_type="task",
                    entity_ref=task.stable_key,
                    fact_key="ready_work",
                    value={
                        "title": task.title,
                        "status": projection.status,
                        "priority_label": task.priority_label,
                    },
                )
        risk_refs: list[str] = []
        for risk in self.session.scalars(
            select(Risk)
            .where(Risk.version_id == plan.id, Risk.status == "open")
            .order_by(Risk.severity.desc(), Risk.stable_key)
        ):
            risk_refs.append(risk.stable_key)
            evidence[risk.stable_key] = EvidenceFact(
                entity_type="risk",
                entity_ref=risk.stable_key,
                fact_key="open_risk",
                value={
                    "description": risk.description,
                    "probability": risk.probability,
                    "impact": risk.impact,
                    "severity": risk.severity,
                    "trigger": risk.trigger,
                },
            )
        for detection in snapshot.detections_json:
            reference = f"DETECTION-{detection['code']}"
            evidence[reference] = EvidenceFact(
                entity_type="detection",
                entity_ref=reference,
                fact_key="monitoring_condition",
                value=detection,
            )
        event_cursor = f"{events[-1].occurred_at.isoformat()}:{events[-1].id}" if events else None
        progress = snapshot.progress_json["project"]
        return FactualReportData(
            project_id=project.id,
            project_name=project.name,
            version_id=plan.id,
            version_number=plan.number,
            report_type=payload.report_type,
            period_start=payload.period_start,
            period_end=payload.period_end,
            state_hash=snapshot.state_hash,
            event_cursor=event_cursor,
            evidence=evidence,
            metrics={
                "weighted_progress_fraction": progress["fraction"],
                "weighted_progress_display": _percent_display(progress["fraction"]),
                "weighted_completed_hours": progress["weighted_completed_hours"],
                "estimated_hours": progress["estimated_hours"],
                "completed_event_count": len(completed_refs),
                "blocked_task_count": len(blocker_refs),
                "ready_task_count": len(next_action_refs),
                "open_risk_count": len(risk_refs),
            },
            completed_refs=completed_refs,
            blocker_refs=sorted(blocker_refs),
            risk_refs=risk_refs,
            next_action_refs=sorted(next_action_refs),
            health_label=snapshot.health_label,
            health_rule_codes=list(snapshot.health_json["rule_codes"]),
            calculation_versions=dict(snapshot.calculation_versions),
        )

    async def generate_narrative(
        self,
        data: FactualReportData,
        provider: StructuredModelProvider,
        settings: Settings,
        *,
        run_id: UUID,
    ) -> tuple[WeeklyReportNarrative, ModelUsage]:
        prompt = get_prompt("weekly_report.v2")
        sync_prompt_catalog(self.session)
        prompt_record = mark_prompt_used(
            self.session,
            key=prompt.key,
            version=prompt.version,
            expected_hash=prompt.template_hash,
        )
        instructions, input_text = prompt.render(data.model_dump(mode="json"))
        try:
            result = await provider.generate(
                StructuredModelRequest(
                    prompt_key=prompt.key,
                    prompt_version=prompt.version,
                    instructions=instructions,
                    input_text=input_text,
                    output_type=WeeklyReportNarrative,
                    token_budget=prompt.output_token_budget,
                    safety_identifier=make_safety_identifier(
                        self.owner_id,
                        settings.session_hash_secret.get_secret_value(),
                    ),
                    reasoning_effort=prompt.reasoning_effort,
                    metadata={"run_id": str(run_id), "workflow": "reporting"},
                )
            )
        except StructuredModelError as error:
            record_provider_usage(
                self.session,
                request_id=self.request_id,
                prompt_version_id=prompt_record.id,
                provider="openai",
                model=settings.openai_model,
                response_id=error.response_id,
                usage=ModelUsage(),
                duration_ms=0,
                outcome=(
                    error.code.value if error.code.value in {"refused", "truncated"} else "failed"
                ),
                error_code=error.code.value,
            )
            raise
        errors = validate_weekly_narrative(result.output, data.evidence)
        if errors:
            record_provider_usage(
                self.session,
                request_id=self.request_id,
                prompt_version_id=prompt_record.id,
                provider=result.provider,
                model=result.model,
                response_id=result.response_id,
                usage=result.usage,
                duration_ms=result.duration_ms,
                outcome="failed",
                error_code="UNSUPPORTED_CLAIMS",
            )
            raise ReportGroundingError(errors)
        record_provider_usage(
            self.session,
            request_id=self.request_id,
            prompt_version_id=prompt_record.id,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            usage=result.usage,
            duration_ms=result.duration_ms,
            outcome="completed",
        )
        return result.output, result.usage

    def persist(
        self,
        run: AgentRun,
        data: FactualReportData,
        *,
        narrative: WeeklyReportNarrative | None,
        failure_code: str | None,
    ) -> Report:
        input_hash = canonical_hash(data.model_dump(mode="json"))
        existing = self.session.scalar(
            select(Report).where(
                Report.project_id == data.project_id,
                Report.input_hash == input_hash,
            )
        )
        if existing is not None:
            return existing
        markdown = render_markdown(data, narrative)
        status = "completed" if narrative is not None else "partial"
        content_hash = canonical_hash(
            {
                "data": data.model_dump(mode="json"),
                "narrative": (narrative.model_dump(mode="json") if narrative is not None else None),
                "markdown": markdown,
            }
        )
        report = Report(
            project_id=data.project_id,
            version_id=data.version_id,
            run_id=run.id,
            report_type=data.report_type,
            period_start=data.period_start,
            period_end=data.period_end,
            data_json=data.model_dump(mode="json"),
            narrative_json=(narrative.model_dump(mode="json") if narrative is not None else None),
            markdown=markdown,
            content_hash=content_hash,
            input_hash=input_hash,
            state_hash=data.state_hash,
            status=status,
            narrative_failure_code=failure_code,
        )
        self.session.add(report)
        self.session.flush()
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=None,
            actor_type="system",
            project_id=data.project_id,
            action="ReportCreated",
            entity_type="Report",
            entity_id=report.id,
            request_id=self.request_id,
            after_ref={
                "report_type": data.report_type,
                "period_start": data.period_start.isoformat(),
                "period_end": data.period_end.isoformat(),
                "status": status,
                "content_hash": content_hash,
                "state_hash": data.state_hash,
            },
        )
        self.telemetry.append(
            name=f"report.{status}",
            owner_id=self.owner_id,
            request_id=self.request_id,
            project_id=data.project_id,
            run_id=run.id,
            attributes={
                "report_type": data.report_type,
                "evidence_count": len(data.evidence),
                "has_narrative": narrative is not None,
                "failure_code": failure_code,
            },
        )
        self.session.flush()
        return report

    def list(self, project_id: UUID) -> list[ReportSummaryView]:
        self._owned_project(project_id)
        return [
            self._summary(item)
            for item in self.session.scalars(
                select(Report)
                .where(Report.project_id == project_id)
                .order_by(Report.created_at.desc(), Report.id.desc())
            )
        ]

    def get(self, report_id: UUID) -> ReportView:
        report = self._owned_report(report_id)
        return self._view(report)

    def export_markdown(self, report_id: UUID) -> tuple[str, str]:
        report = self._owned_report(report_id)
        project = self._owned_project(report.project_id)
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=report.project_id,
            action="ReportExported",
            entity_type="Report",
            entity_id=report.id,
            request_id=self.request_id,
            after_ref={"format": "markdown", "content_hash": report.content_hash},
        )
        self.telemetry.append(
            name="report.exported",
            owner_id=self.owner_id,
            request_id=self.request_id,
            project_id=report.project_id,
            run_id=report.run_id,
            attributes={"format": "markdown", "report_type": report.report_type},
        )
        self.session.commit()
        return (
            report.markdown,
            safe_filename(project.name, report.report_type, report.period_end.isoformat()),
        )

    def _active_plan(self, project_id: UUID) -> tuple[Project, PlanVersion]:
        project = self.session.scalar(
            select(Project)
            .options(selectinload(Project.calendars))
            .where(
                Project.id == project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if project is None:
            raise ReportNotFoundError
        plan = self.session.scalar(
            select(PlanVersion).where(
                PlanVersion.project_id == project.id,
                PlanVersion.state == "active",
            )
        )
        if plan is None:
            raise ReportNotFoundError
        return project, plan

    def _owned_project(self, project_id: UUID) -> Project:
        project = self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if project is None:
            raise ReportNotFoundError
        return project

    def _owned_report(self, report_id: UUID) -> Report:
        report = self.session.scalar(
            select(Report)
            .join(Project, Project.id == Report.project_id)
            .where(
                Report.id == report_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if report is None:
            raise ReportNotFoundError
        return report

    def _validate_period(self, project: Project, payload: ReportCreateRequest) -> None:
        today = datetime.now(ZoneInfo(project.timezone)).date()
        if payload.period_end > today:
            raise ReportConflictError("Report period cannot end in the future.")

    @staticmethod
    def _summary(report: Report) -> ReportSummaryView:
        return ReportSummaryView(
            id=report.id,
            project_id=report.project_id,
            version_id=report.version_id,
            run_id=report.run_id,
            report_type=cast(Any, report.report_type),
            period_start=report.period_start,
            period_end=report.period_end,
            status=cast(Any, report.status),
            narrative_failure_code=report.narrative_failure_code,
            content_hash=report.content_hash,
            created_at=report.created_at,
        )

    @classmethod
    def _view(cls, report: Report) -> ReportView:
        summary = cls._summary(report)
        return ReportView(
            **summary.model_dump(),
            data=FactualReportData.model_validate(report.data_json),
            narrative=report.narrative_json,
            markdown=report.markdown,
        )


def _percent_display(fraction: str | None) -> str:
    if fraction is None:
        return "Not available"
    value = (Decimal(fraction) * Decimal(100)).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )
    formatted = format(value.normalize(), "f")
    return f"{formatted}%"
