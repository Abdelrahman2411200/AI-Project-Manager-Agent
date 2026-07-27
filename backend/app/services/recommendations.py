"""Evidence-first recommendation generation, validation, decisions, and views."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

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
from app.ai.schemas.outputs import RecommendationDraft, RecommendationDraftBatch
from app.core.config import Settings
from app.core.hashing import canonical_hash
from app.db.models.execution import MonitoringSnapshot, TaskExecutionProjection
from app.db.models.insight import (
    Recommendation,
    RecommendationDecision,
    RecommendationEvidence,
)
from app.db.models.plan import PlanVersion, Task
from app.db.models.project import Project
from app.domain.grounding import validate_recommendation_draft
from app.schemas.insight import (
    EvidenceFact,
    RecommendationDecisionRequest,
    RecommendationDecisionView,
    RecommendationEvidenceView,
    RecommendationView,
)
from app.services.audit import AuditRecorder
from app.services.telemetry import TelemetryRecorder


class RecommendationNotFoundError(LookupError):
    pass


class RecommendationConflictError(RuntimeError):
    pass


class RecommendationGroundingError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Recommendation narrative failed grounding validation.")
        self.errors = errors


RECOMMENDATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "INCONSISTENT_STATE": {
        "type": "dependency_warning",
        "urgency": "immediate",
        "why": "The active execution graph contains inconsistent persisted facts.",
        "action": (
            "Repair the recorded dependency or execution-state inconsistency "
            "before updates continue."
        ),
        "impact": "Restores a deterministic and auditable execution projection.",
        "risk": "Continuing could present incorrect readiness or schedule information.",
        "verify": "Recalculate monitoring and confirm the inconsistency detection is absent.",
    },
    "BLOCKED_TASKS": {
        "type": "dependency_warning",
        "urgency": "high",
        "why": "Recorded blocked work can prevent dependent tasks from becoming ready.",
        "action": "Resolve the cited blocker or propose a separately approved scope change.",
        "impact": "Allows dependency readiness and the remaining-work forecast to be recalculated.",
        "risk": "Unresolved blocking work can delay dependent delivery.",
        "verify": "Confirm the cited task is no longer blocked and monitoring has recalculated.",
    },
    "OVERDUE_TASKS": {
        "type": "schedule_warning",
        "urgency": "high",
        "why": "Incomplete work has passed a persisted planned finish date.",
        "action": (
            "Review the cited overdue work and record a factual status or approved plan revision."
        ),
        "impact": "Makes the execution forecast reflect current recorded work.",
        "risk": "Ignoring overdue work can hide schedule pressure.",
        "verify": (
            "Recalculate monitoring and confirm each cited task has a current status and forecast."
        ),
    },
    "UNMET_DEPENDENCY": {
        "type": "dependency_warning",
        "urgency": "immediate",
        "why": "A task state conflicts with its recorded finish-to-start prerequisites.",
        "action": "Repair the inconsistent task state before allowing downstream execution.",
        "impact": "Restores truthful readiness based on the approved dependency graph.",
        "risk": "Dependent work could proceed without its required predecessor.",
        "verify": "Confirm all cited predecessors are complete before the successor is ready.",
    },
    "DELAYED_MILESTONE": {
        "type": "schedule_warning",
        "urgency": "high",
        "why": "The current remaining-work schedule extends beyond a recorded milestone target.",
        "action": (
            "Review the cited milestone work and prepare an approval-gated "
            "plan adjustment if needed."
        ),
        "impact": "Surfaces the milestone effect without silently changing the active plan.",
        "risk": "The milestone deliverable may be later than its approved target.",
        "verify": (
            "Confirm the milestone forecast after task status and capacity facts are updated."
        ),
    },
    "SCHEDULE_SLIPPAGE": {
        "type": "schedule_warning",
        "urgency": "high",
        "why": "The deterministic forecast is later than the persisted planned finish.",
        "action": "Review remaining work and create a new draft if scope or dates must change.",
        "impact": "Keeps schedule decisions explicit and approval gated.",
        "risk": "Delivery can miss the approved plan if the variance is not addressed.",
        "verify": "Recalculate and compare the forecast with the persisted planned finish.",
    },
    "SCHEDULE_INFEASIBLE": {
        "type": "schedule_warning",
        "urgency": "immediate",
        "why": "The deterministic remaining-work schedule cannot meet the recorded deadline.",
        "action": "Prepare an approval-gated change to scope, capacity, sequencing, or deadline.",
        "impact": "Makes the infeasible constraint visible without compressing estimates.",
        "risk": "The current deadline cannot be represented as achievable from persisted facts.",
        "verify": (
            "Confirm a recalculated schedule reports a feasible result after an approved change."
        ),
    },
    "LOW_BUFFER": {
        "type": "schedule_warning",
        "urgency": "high",
        "why": "The remaining schedule buffer is small relative to remaining planned duration.",
        "action": "Protect the blocking path and review avoidable noncritical work.",
        "impact": "Preserves attention on schedule-sensitive work.",
        "risk": "A small execution variance can consume the remaining buffer.",
        "verify": "Recalculate monitoring after the next factual progress update.",
    },
    "CAPACITY_OVERLOAD": {
        "type": "schedule_warning",
        "urgency": "high",
        "why": "Persisted remaining work exceeds the configured capacity window.",
        "action": "Review capacity facts or prepare an approval-gated scope and schedule change.",
        "impact": "Aligns the forecast with explicit capacity rather than invented productivity.",
        "risk": "Overloaded capacity can produce a delayed or infeasible delivery.",
        "verify": "Confirm the overload detection clears after approved inputs change.",
    },
    "SCOPE_CHANGED": {
        "type": "scope_warning",
        "urgency": "medium",
        "why": "Monitoring detected a persisted scope change that affects the active baseline.",
        "action": "Review the cited change and ensure it belongs to an approved plan version.",
        "impact": "Preserves the active-plan approval boundary.",
        "risk": "Unreviewed scope can invalidate schedule and progress expectations.",
        "verify": "Confirm the active version and its content hash match the approved scope.",
    },
    "READY_WORK_AVAILABLE": {
        "type": "next_action",
        "urgency": "low",
        "why": "Recorded prerequisites are complete for the cited ready work.",
        "action": "Select a cited ready task when execution capacity is available.",
        "impact": "Advances approved work using deterministic readiness.",
        "risk": "Starting unrelated work may delay higher-priority ready tasks.",
        "verify": "Confirm the selected task remains ready immediately before starting it.",
    },
}


class RecommendationService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.audit = AuditRecorder(session)
        self.telemetry = TelemetryRecorder(session)

    def sync_for_snapshot(self, snapshot: MonitoringSnapshot) -> list[Recommendation]:
        project, plan = self._owned_snapshot(snapshot)
        result: list[Recommendation] = []
        for detection in snapshot.detections_json:
            code = str(detection["code"])
            template = RECOMMENDATION_TEMPLATES.get(code)
            if template is None:
                continue
            evidence = self._evidence_catalog(snapshot, detection)
            input_hash = canonical_hash(
                {
                    "snapshot_state_hash": snapshot.state_hash,
                    "detection": detection,
                    "evidence": {
                        key: value.model_dump(mode="json")
                        for key, value in sorted(evidence.items())
                    },
                }
            )
            existing = self.session.scalar(
                select(Recommendation).where(
                    Recommendation.project_id == project.id,
                    Recommendation.recommendation_type == template["type"],
                    Recommendation.input_hash == input_hash,
                )
            )
            if existing is not None:
                result.append(existing)
                continue
            recommendation = Recommendation(
                project_id=project.id,
                version_id=plan.id,
                snapshot_id=snapshot.id,
                recommendation_type=template["type"],
                detection_code=code,
                why_it_matters=template["why"],
                suggested_action=template["action"],
                expected_impact=template["impact"],
                urgency=template["urgency"],
                risk=template["risk"],
                approval_required=template["type"] != "next_action",
                verification_step=template["verify"],
                alternatives=[
                    "Continue current work and review the condition at the next monitoring cycle."
                ],
                state="open",
                input_hash=input_hash,
                explanation_source="deterministic",
            )
            self.session.add(recommendation)
            self.session.flush()
            for reference, fact in evidence.items():
                self.session.add(
                    RecommendationEvidence(
                        recommendation_id=recommendation.id,
                        entity_type=(
                            fact.entity_type if fact.entity_type != "period" else "project"
                        ),
                        entity_ref=reference,
                        fact_key=fact.fact_key,
                        fact_value=fact.value,
                    )
                )
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=None,
                actor_type="system",
                project_id=project.id,
                action="RecommendationCreated",
                entity_type="Recommendation",
                entity_id=recommendation.id,
                request_id=self.request_id,
                after_ref={
                    "detection_code": code,
                    "urgency": recommendation.urgency,
                    "evidence_refs": sorted(evidence),
                    "input_hash": input_hash,
                },
            )
            self.telemetry.append(
                name="recommendation.created",
                owner_id=self.owner_id,
                request_id=self.request_id,
                project_id=project.id,
                attributes={
                    "detection_code": code,
                    "urgency": recommendation.urgency,
                    "evidence_count": len(evidence),
                },
            )
            result.append(recommendation)
        self.session.flush()
        return result

    async def enrich_with_ai(
        self,
        snapshot: MonitoringSnapshot,
        recommendations: list[Recommendation],
        provider: StructuredModelProvider,
        settings: Settings,
        *,
        run_id: UUID,
    ) -> tuple[list[Recommendation], ModelUsage]:
        if not recommendations:
            return recommendations, ModelUsage()
        prompt = get_prompt("recommendations.v2")
        sync_prompt_catalog(self.session)
        prompt_record = mark_prompt_used(
            self.session,
            key=prompt.key,
            version=prompt.version,
            expected_hash=prompt.template_hash,
        )
        contexts: list[dict[str, Any]] = []
        evidence_by_code: dict[str, dict[str, EvidenceFact]] = {}
        candidate_by_code = {item.detection_code: item for item in recommendations}
        for recommendation in recommendations:
            evidence = self._stored_evidence(recommendation.id)
            evidence_by_code[recommendation.detection_code] = evidence
            contexts.append(
                {
                    "detection_code": recommendation.detection_code,
                    "deterministic_candidate": {
                        "type": recommendation.recommendation_type,
                        "urgency": recommendation.urgency,
                        "approval_required": recommendation.approval_required,
                    },
                    "evidence": {
                        key: value.model_dump(mode="json")
                        for key, value in sorted(evidence.items())
                    },
                }
            )
        instructions, input_text = prompt.render(
            {
                "active_state_hash": snapshot.state_hash,
                "candidates": contexts,
            }
        )
        try:
            generated = await provider.generate(
                StructuredModelRequest(
                    prompt_key=prompt.key,
                    prompt_version=prompt.version,
                    instructions=instructions,
                    input_text=input_text,
                    output_type=RecommendationDraftBatch,
                    token_budget=prompt.output_token_budget,
                    safety_identifier=make_safety_identifier(
                        self.owner_id,
                        settings.session_hash_secret.get_secret_value(),
                    ),
                    reasoning_effort=prompt.reasoning_effort,
                    metadata={"run_id": str(run_id), "workflow": "monitoring"},
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
        by_code: dict[str, RecommendationDraft] = {}
        errors: list[str] = []
        for draft in generated.output.items:
            if draft.detection_code in by_code:
                errors.append(f"Duplicate detection narrative: {draft.detection_code}")
                continue
            draft_evidence = evidence_by_code.get(draft.detection_code)
            if draft_evidence is None:
                errors.append(f"Unknown detection narrative: {draft.detection_code}")
                continue
            errors.extend(
                validate_recommendation_draft(
                    draft,
                    draft_evidence,
                    expected_detection_code=draft.detection_code,
                )
            )
            candidate = candidate_by_code[draft.detection_code]
            if draft.type != candidate.recommendation_type:
                errors.append(f"Recommendation type changed for {draft.detection_code}.")
            if draft.urgency != candidate.urgency:
                errors.append(f"Recommendation urgency changed for {draft.detection_code}.")
            if draft.approval_required != candidate.approval_required:
                errors.append(f"Approval policy changed for {draft.detection_code}.")
            by_code[draft.detection_code] = draft
        if errors:
            record_provider_usage(
                self.session,
                request_id=self.request_id,
                prompt_version_id=prompt_record.id,
                provider=generated.provider,
                model=generated.model,
                response_id=generated.response_id,
                usage=generated.usage,
                duration_ms=generated.duration_ms,
                outcome="failed",
                error_code="UNSUPPORTED_CLAIMS",
            )
            raise RecommendationGroundingError(errors)
        for recommendation in recommendations:
            generated_draft = by_code.get(recommendation.detection_code)
            if generated_draft is None or recommendation.state not in {"open", "deferred"}:
                continue
            recommendation.why_it_matters = generated_draft.why_it_matters
            recommendation.suggested_action = generated_draft.suggested_action
            recommendation.expected_impact = generated_draft.expected_impact
            recommendation.risk = generated_draft.risk
            recommendation.verification_step = generated_draft.verification_step
            recommendation.alternatives = generated_draft.alternatives
            recommendation.explanation_source = "ai"
        record_provider_usage(
            self.session,
            request_id=self.request_id,
            prompt_version_id=prompt_record.id,
            provider=generated.provider,
            model=generated.model,
            response_id=generated.response_id,
            usage=generated.usage,
            duration_ms=generated.duration_ms,
            outcome="completed",
        )
        self.session.flush()
        return recommendations, generated.usage

    def list(
        self,
        project_id: UUID,
        *,
        state: str | None = None,
    ) -> list[RecommendationView]:
        self._owned_project(project_id)
        query = (
            select(Recommendation)
            .where(Recommendation.project_id == project_id)
            .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
        )
        if state is not None:
            query = query.where(Recommendation.state == state)
        return [self.view(item) for item in self.session.scalars(query)]

    def get(self, recommendation_id: UUID) -> RecommendationView:
        recommendation = self._owned_recommendation(recommendation_id)
        return self.view(recommendation)

    def decide(
        self,
        recommendation_id: UUID,
        decision: str,
        payload: RecommendationDecisionRequest,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> RecommendationView:
        if decision not in {"accept", "dismiss", "defer"}:
            raise RecommendationConflictError("Unsupported recommendation decision.")
        if decision == "defer":
            if payload.defer_until is None:
                raise RecommendationConflictError("A defer-until date is required.")
            today = date.today()
            if payload.defer_until < today or payload.defer_until > today + timedelta(days=366):
                raise RecommendationConflictError(
                    "Defer-until must be between today and one year from today."
                )
        elif payload.defer_until is not None:
            raise RecommendationConflictError(
                "Only a deferred recommendation may include defer-until."
            )
        event_key = f"recommendation:{self.owner_id}:{idempotency_key}"
        request_hash = canonical_hash(
            {
                "recommendation_id": recommendation_id,
                "decision": decision,
                **payload.model_dump(mode="json"),
            }
        )
        duplicate = self.session.scalar(
            select(RecommendationDecision).where(RecommendationDecision.event_key == event_key)
        )
        if duplicate is not None:
            if (
                duplicate.recommendation_id != recommendation_id
                or duplicate.request_hash != request_hash
            ):
                raise RecommendationConflictError(
                    "Idempotency key was already used with another decision."
                )
            return self.get(recommendation_id)
        recommendation = self._owned_recommendation(recommendation_id, lock=True)
        if recommendation.row_version != expected_version:
            raise RecommendationConflictError(
                f"Recommendation conflict: expected {expected_version}, "
                f"current {recommendation.row_version}."
            )
        if recommendation.state not in {"open", "deferred"}:
            raise RecommendationConflictError(
                "Only an open or deferred recommendation can be decided."
            )
        before = recommendation.state
        recommendation.state = {
            "accept": "accepted",
            "dismiss": "dismissed",
            "defer": "deferred",
        }[decision]
        record = RecommendationDecision(
            recommendation_id=recommendation.id,
            actor_id=self.owner_id,
            decision=decision,
            reason=payload.reason,
            defer_until=payload.defer_until,
            event_key=event_key,
            request_hash=request_hash,
        )
        self.session.add(record)
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=recommendation.project_id,
            action="RecommendationDecision",
            entity_type="Recommendation",
            entity_id=recommendation.id,
            request_id=self.request_id,
            before_ref={"state": before},
            after_ref={
                "state": recommendation.state,
                "decision": decision,
                "defer_until": (payload.defer_until.isoformat() if payload.defer_until else None),
                "active_plan_mutated": False,
            },
        )
        self.telemetry.append(
            name="recommendation.decision",
            owner_id=self.owner_id,
            request_id=self.request_id,
            project_id=recommendation.project_id,
            attributes={
                "decision": decision,
                "urgency": recommendation.urgency,
                "approval_required": recommendation.approval_required,
            },
        )
        try:
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise RecommendationConflictError(
                "Recommendation changed concurrently; load the latest state."
            ) from error
        return self.get(recommendation.id)

    def view(self, recommendation: Recommendation) -> RecommendationView:
        evidence = list(
            self.session.scalars(
                select(RecommendationEvidence)
                .where(RecommendationEvidence.recommendation_id == recommendation.id)
                .order_by(
                    RecommendationEvidence.entity_type,
                    RecommendationEvidence.entity_ref,
                    RecommendationEvidence.fact_key,
                )
            )
        )
        decision = self.session.scalar(
            select(RecommendationDecision)
            .where(RecommendationDecision.recommendation_id == recommendation.id)
            .order_by(
                RecommendationDecision.occurred_at.desc(),
                RecommendationDecision.id.desc(),
            )
            .limit(1)
        )
        return RecommendationView(
            id=recommendation.id,
            project_id=recommendation.project_id,
            version_id=recommendation.version_id,
            snapshot_id=recommendation.snapshot_id,
            recommendation_type=recommendation.recommendation_type,
            detection_code=recommendation.detection_code,
            why_it_matters=recommendation.why_it_matters,
            suggested_action=recommendation.suggested_action,
            expected_impact=recommendation.expected_impact,
            urgency=recommendation.urgency,
            risk=recommendation.risk,
            approval_required=recommendation.approval_required,
            verification_step=recommendation.verification_step,
            alternatives=list(recommendation.alternatives),
            state=cast(Any, recommendation.state),
            explanation_source=cast(Any, recommendation.explanation_source),
            evidence=[RecommendationEvidenceView.model_validate(item) for item in evidence],
            latest_decision=(
                RecommendationDecisionView.model_validate(decision)
                if decision is not None
                else None
            ),
            row_version=recommendation.row_version,
            created_at=recommendation.created_at,
            updated_at=recommendation.updated_at,
        )

    def _evidence_catalog(
        self,
        snapshot: MonitoringSnapshot,
        detection: dict[str, Any],
    ) -> dict[str, EvidenceFact]:
        code = str(detection["code"])
        catalog: dict[str, EvidenceFact] = {}
        detection_ref = f"DETECTION-{code}"
        catalog[detection_ref] = EvidenceFact(
            entity_type="detection",
            entity_ref=detection_ref,
            fact_key="condition",
            value={
                "code": code,
                "severity": detection["severity"],
                "values": detection["values"],
                "state_hash": snapshot.state_hash,
            },
        )
        task_rows = {
            task.stable_key: (task, projection)
            for task, projection in self.session.execute(
                select(Task, TaskExecutionProjection)
                .join(
                    TaskExecutionProjection,
                    TaskExecutionProjection.task_id == Task.id,
                )
                .where(Task.version_id == snapshot.version_id)
            )
        }
        for reference in detection.get("references", []):
            if reference in task_rows:
                task, projection = task_rows[reference]
                catalog[reference] = EvidenceFact(
                    entity_type="task",
                    entity_ref=reference,
                    fact_key="execution_state",
                    value={
                        "title": task.title,
                        "status": projection.status,
                        "blocked_reason": projection.blocked_reason,
                        "planned_finish": (
                            task.planned_finish.isoformat() if task.planned_finish else None
                        ),
                        "progress_fraction": str(projection.progress_fraction),
                    },
                )
            else:
                entity_type = "milestone" if str(reference).startswith("MS-") else "project"
                catalog[str(reference)] = EvidenceFact(
                    entity_type=cast(Any, entity_type),
                    entity_ref=str(reference),
                    fact_key="detected_reference",
                    value={"detection_code": code},
                )
        catalog["METRIC-PROGRESS"] = EvidenceFact(
            entity_type="metric",
            entity_ref="METRIC-PROGRESS",
            fact_key="weighted_progress",
            value=snapshot.progress_json["project"],
        )
        if code in {
            "DELAYED_MILESTONE",
            "SCHEDULE_SLIPPAGE",
            "SCHEDULE_INFEASIBLE",
            "LOW_BUFFER",
            "CAPACITY_OVERLOAD",
        }:
            catalog["FORECAST-CURRENT"] = EvidenceFact(
                entity_type="forecast",
                entity_ref="FORECAST-CURRENT",
                fact_key="remaining_work_schedule",
                value=snapshot.schedule_json,
            )
        return catalog

    def _stored_evidence(
        self,
        recommendation_id: UUID,
    ) -> dict[str, EvidenceFact]:
        return {
            item.entity_ref: EvidenceFact(
                entity_type=cast(Any, item.entity_type),
                entity_ref=item.entity_ref,
                fact_key=item.fact_key,
                value=item.fact_value,
            )
            for item in self.session.scalars(
                select(RecommendationEvidence).where(
                    RecommendationEvidence.recommendation_id == recommendation_id
                )
            )
        }

    def _owned_snapshot(
        self,
        snapshot: MonitoringSnapshot,
    ) -> tuple[Project, PlanVersion]:
        row = self.session.execute(
            select(Project, PlanVersion)
            .join(PlanVersion, PlanVersion.project_id == Project.id)
            .where(
                Project.id == snapshot.project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
                PlanVersion.id == snapshot.version_id,
                PlanVersion.state == "active",
            )
        ).one_or_none()
        if row is None:
            raise RecommendationNotFoundError
        return row[0], row[1]

    def _owned_project(self, project_id: UUID) -> Project:
        project = self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if project is None:
            raise RecommendationNotFoundError
        return project

    def _owned_recommendation(
        self,
        recommendation_id: UUID,
        *,
        lock: bool = False,
    ) -> Recommendation:
        query = (
            select(Recommendation)
            .join(Project, Project.id == Recommendation.project_id)
            .where(
                Recommendation.id == recommendation_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if lock:
            query = query.with_for_update()
        recommendation = self.session.scalar(query)
        if recommendation is None:
            raise RecommendationNotFoundError
        return recommendation
