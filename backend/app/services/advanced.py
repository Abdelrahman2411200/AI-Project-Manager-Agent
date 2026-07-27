"""Owner-scoped full-version intelligence with virtual and approval boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.auth.policies import (
    PlanLifecycleConflictError,
    PlanLifecyclePolicy,
    PlanResourceNotFoundError,
)
from app.core.hashing import canonical_hash, canonical_json
from app.db.base import utc_now
from app.db.models.advanced import RegenerationProposal, RiskRelation, Scenario
from app.db.models.plan import Milestone, PlanVersion, Risk, Task, TaskDependency
from app.db.models.project import Project, ProjectRequirement, WorkCalendar
from app.domain.advanced_schedule import (
    AdvancedScheduleTask,
    capacity_forecast,
    schedule_capacity_ranges,
)
from app.domain.change_impact import summarize_comparison
from app.domain.critical_path import CriticalPathTask, calculate_critical_path
from app.domain.graph import DependencyEdge
from app.schemas.advanced import RegenerationCreate, RiskCreate, RiskUpdate, ScenarioCreate
from app.services.audit import AuditRecorder
from app.services.plan_content import persisted_content_hash, plan_content_snapshot

TASK_FIELDS = frozenset(
    {
        "title",
        "description",
        "deliverable",
        "acceptance_criteria",
        "definition_of_done",
        "effort_min_hours",
        "effort_likely_hours",
        "effort_max_hours",
        "complexity",
        "workstreams",
        "skill_tags",
        "requirement_refs",
        "assumption_refs",
    }
)
MILESTONE_FIELDS = frozenset(
    {
        "name",
        "description",
        "objective",
        "deliverable",
        "target_date",
        "planned_effort_hours",
        "acceptance_criteria",
    }
)
DECIMAL_FIELDS = frozenset(
    {
        "effort_min_hours",
        "effort_likely_hours",
        "effort_max_hours",
        "planned_effort_hours",
    }
)
DATE_FIELDS = frozenset({"target_date"})
CALCULATION_VERSION = "advanced-intelligence-v1"


class AdvancedIntelligenceService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.policy = PlanLifecyclePolicy(session, owner_id)
        self.audit = AuditRecorder(session)

    def compare(self, from_id: UUID, to_id: UUID) -> dict[str, Any]:
        before = self.policy.plan(from_id)
        after = self.policy.plan(to_id)
        if before.project_id != after.project_id:
            raise PlanResourceNotFoundError
        return summarize_comparison(
            plan_content_snapshot(self.session, before),
            plan_content_snapshot(self.session, after),
        )

    def list_risks(self, version_id: UUID) -> list[tuple[Risk, list[RiskRelation]]]:
        plan = self.policy.plan(version_id)
        risks = list(
            self.session.scalars(
                select(Risk).where(Risk.version_id == plan.id).order_by(Risk.stable_key)
            )
        )
        relations = list(
            self.session.scalars(
                select(RiskRelation)
                .where(RiskRelation.version_id == plan.id)
                .order_by(RiskRelation.entity_type, RiskRelation.entity_ref)
            )
        )
        by_risk: dict[UUID, list[RiskRelation]] = {risk.id: [] for risk in risks}
        for relation in relations:
            by_risk.setdefault(relation.risk_id, []).append(relation)
        return [(risk, by_risk[risk.id]) for risk in risks]

    def create_risk(
        self,
        version_id: UUID,
        payload: RiskCreate,
        expected_version: int,
    ) -> tuple[Risk, list[RiskRelation], PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        self._validate_risk_relations(plan, payload.relations)
        stable_key = self._next_risk_key(plan.id)
        relation_refs = [item.entity_ref for item in payload.relations]
        risk = Risk(
            version_id=plan.id,
            stable_key=stable_key,
            category=payload.category,
            description=payload.description,
            probability=payload.probability,
            impact=payload.impact,
            severity=self._severity(payload.probability, payload.impact),
            trigger=payload.trigger,
            mitigation=payload.mitigation,
            contingency=payload.contingency,
            related_refs=relation_refs,
            source_fact_refs=payload.source_fact_refs,
            status="open",
        )
        self.session.add(risk)
        self.session.flush()
        relations = [
            RiskRelation(
                risk_id=risk.id,
                version_id=plan.id,
                entity_type=item.entity_type,
                entity_ref=item.entity_ref,
            )
            for item in payload.relations
        ]
        self.session.add_all(relations)
        self._invalidate_plan(plan)
        self._commit_risk(plan, risk, "RiskChanged", None)
        return risk, relations, self.policy.plan(plan.id)

    def update_risk(
        self,
        version_id: UUID,
        risk_id: UUID,
        payload: RiskUpdate,
        expected_version: int,
    ) -> tuple[Risk, list[RiskRelation], PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        risk = self.session.scalar(
            select(Risk).where(Risk.id == risk_id, Risk.version_id == plan.id)
        )
        if risk is None:
            raise PlanResourceNotFoundError
        before = {
            "stable_key": risk.stable_key,
            "severity": risk.severity,
            "status": risk.status,
        }
        values = payload.model_dump(exclude_unset=True)
        relation_inputs = values.pop("relations", None)
        for field, value in values.items():
            setattr(risk, field, value)
        risk.severity = self._severity(risk.probability, risk.impact)
        if relation_inputs is not None:
            from app.schemas.advanced import RiskRelationInput

            parsed_relations = [RiskRelationInput.model_validate(item) for item in relation_inputs]
            self._validate_risk_relations(plan, parsed_relations)
            existing = list(
                self.session.scalars(select(RiskRelation).where(RiskRelation.risk_id == risk.id))
            )
            for relation in existing:
                self.session.delete(relation)
            self.session.flush()
            risk.related_refs = [item.entity_ref for item in parsed_relations]
            self.session.add_all(
                [
                    RiskRelation(
                        risk_id=risk.id,
                        version_id=plan.id,
                        entity_type=item.entity_type,
                        entity_ref=item.entity_ref,
                    )
                    for item in parsed_relations
                ]
            )
        self._invalidate_plan(plan)
        self._commit_risk(plan, risk, "RiskChanged", before)
        relations = list(
            self.session.scalars(
                select(RiskRelation)
                .where(RiskRelation.risk_id == risk.id)
                .order_by(RiskRelation.entity_type, RiskRelation.entity_ref)
            )
        )
        return risk, relations, self.policy.plan(plan.id)

    def create_scenario(
        self,
        project_id: UUID,
        payload: ScenarioCreate,
        idempotency_key: str,
    ) -> Scenario:
        project = self._project(project_id)
        existing = self.session.scalar(
            select(Scenario).where(
                Scenario.owner_id == self.owner_id,
                Scenario.idempotency_key == idempotency_key,
            )
        )
        input_hash = canonical_hash(payload.model_dump(mode="json"))
        if existing is not None:
            if existing.input_hash != input_hash or existing.project_id != project_id:
                raise PlanLifecycleConflictError(
                    "Idempotency key was already used for different scenario input."
                )
            return existing
        baseline = (
            self.policy.plan(payload.baseline_version_id)
            if payload.baseline_version_id is not None
            else self._active_plan(project_id)
        )
        if baseline.project_id != project_id:
            raise PlanResourceNotFoundError
        self.policy.require_state(baseline, "active")
        snapshot = plan_content_snapshot(self.session, baseline)
        result = self._scenario_result(project, baseline, payload, snapshot)
        scenario = Scenario(
            project_id=project_id,
            baseline_version_id=baseline.id,
            owner_id=self.owner_id,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            baseline_content_hash=baseline.content_hash,
            name=payload.name,
            overrides_json=payload.overrides.model_dump(mode="json"),
            result_json=result,
            explanation_json=self._deterministic_explanation(result),
            status="completed",
            calculation_version=CALCULATION_VERSION,
        )
        self.session.add(scenario)
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=project_id,
                action="ScenarioCreated",
                entity_type="Scenario",
                entity_id=scenario.id,
                request_id=self.request_id,
                after_ref={
                    "baseline_version_id": str(baseline.id),
                    "baseline_content_hash": baseline.content_hash,
                },
            )
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise PlanLifecycleConflictError("Scenario conflicts with persisted state.") from error
        return self.get_scenario(scenario.id)

    def get_scenario(self, scenario_id: UUID) -> Scenario:
        scenario = self.session.scalar(
            select(Scenario).where(
                Scenario.id == scenario_id,
                Scenario.owner_id == self.owner_id,
            )
        )
        if scenario is None:
            raise PlanResourceNotFoundError
        return scenario

    def propose_regeneration(
        self,
        version_id: UUID,
        payload: RegenerationCreate,
        idempotency_key: str,
    ) -> RegenerationProposal:
        plan = self.policy.plan(version_id)
        self.policy.require_state(plan, {"draft"})
        existing = self.session.scalar(
            select(RegenerationProposal).where(
                RegenerationProposal.owner_id == self.owner_id,
                RegenerationProposal.idempotency_key == idempotency_key,
            )
        )
        input_hash = canonical_hash(payload.model_dump(mode="json"))
        if existing is not None:
            if existing.input_hash != input_hash or existing.version_id != version_id:
                raise PlanLifecycleConflictError(
                    "Idempotency key was already used for different regeneration input."
                )
            return existing
        baseline = plan_content_snapshot(self.session, plan)
        candidate = deepcopy(baseline)
        self._apply_virtual_replacements(candidate, payload)
        self._validate_candidate(candidate)
        impact = summarize_comparison(baseline, candidate)
        proposal = RegenerationProposal(
            project_id=plan.project_id,
            version_id=plan.id,
            owner_id=self.owner_id,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            baseline_content_hash=plan.content_hash,
            selection_json=[item.model_dump(mode="json") for item in payload.targets],
            replacements_json=[item.model_dump(mode="json") for item in payload.replacements],
            diff_json=self._json_safe(impact["changes"]),
            impact_json=self._json_safe(
                {key: value for key, value in impact.items() if key != "changes"}
            ),
            status="pending",
        )
        self.session.add(proposal)
        self._commit_proposal(proposal, "RegenerationProposed")
        return self.get_regeneration(proposal.id)

    def get_regeneration(self, proposal_id: UUID) -> RegenerationProposal:
        proposal = self.session.scalar(
            select(RegenerationProposal).where(
                RegenerationProposal.id == proposal_id,
                RegenerationProposal.owner_id == self.owner_id,
            )
        )
        if proposal is None:
            raise PlanResourceNotFoundError
        return proposal

    def decide_regeneration(
        self,
        proposal_id: UUID,
        *,
        approve: bool,
        expected_version: int,
        reason: str | None,
    ) -> RegenerationProposal:
        proposal = self.get_regeneration(proposal_id)
        if proposal.row_version != expected_version or proposal.status != "pending":
            raise PlanLifecycleConflictError("Regeneration proposal is stale or already decided.")
        plan = self.policy.plan(proposal.version_id, lock=True)
        self.policy.require_state(plan, "draft")
        if not approve:
            proposal.status = "rejected"
            self._commit_proposal(proposal, "RegenerationRejected", reason=reason)
            return self.get_regeneration(proposal.id)
        if plan.content_hash != proposal.baseline_content_hash:
            proposal.status = "stale"
            self._commit_proposal(proposal, "RegenerationStale")
            raise PlanLifecycleConflictError(
                "Draft changed after proposal creation; create a new regeneration proposal."
            )
        self._apply_persisted_replacements(plan, proposal.replacements_json)
        plan.quality_status = "failed"
        plan.quality_report = {
            "passed": False,
            "issues": [
                {
                    "severity": "must",
                    "code": "VALIDATION_REQUIRED",
                    "path": "$",
                    "message": "Regenerated draft content must be validated.",
                    "references": [],
                }
            ],
            "warning_codes": [],
            "calculation_versions": {"quality": "persisted-quality-v1"},
        }
        self.session.flush()
        plan.content_hash = persisted_content_hash(self.session, plan)
        plan.updated_at = utc_now()
        proposal.status = "approved"
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=plan.project_id,
                action="RegenerationApproved",
                entity_type="RegenerationProposal",
                entity_id=proposal.id,
                request_id=self.request_id,
                before_ref={"baseline_content_hash": proposal.baseline_content_hash},
                after_ref={
                    "draft_content_hash": plan.content_hash,
                    "reason": reason,
                },
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Regeneration approval conflicts with persisted state."
            ) from error
        return self.get_regeneration(proposal.id)

    def _scenario_result(
        self,
        project: Project,
        plan: PlanVersion,
        payload: ScenarioCreate,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        tasks = list(self.session.scalars(select(Task).where(Task.version_id == plan.id)))
        edges = list(
            self.session.scalars(select(TaskDependency).where(TaskDependency.version_id == plan.id))
        )
        task_by_key = {task.stable_key: task for task in tasks}
        unknown = set(payload.overrides.task_effort_hours) - task_by_key.keys()
        if unknown:
            raise PlanLifecycleConflictError(
                f"Scenario references unknown tasks: {', '.join(sorted(unknown))}."
            )
        durations = {
            task.stable_key: payload.overrides.task_effort_hours.get(
                task.stable_key, task.effort_likely_hours
            )
            for task in tasks
        }
        graph_edges = [
            DependencyEdge(
                predecessor_id=edge.predecessor_id,
                successor_id=edge.successor_id,
                version_id=plan.id,
            )
            for edge in edges
        ]
        critical = calculate_critical_path(
            [
                CriticalPathTask(
                    id=task.id,
                    stable_key=task.stable_key,
                    version_id=plan.id,
                    duration_hours=durations[task.stable_key],
                )
                for task in tasks
            ],
            graph_edges,
            plan.id,
        )
        baseline_critical = calculate_critical_path(
            [
                CriticalPathTask(
                    id=task.id,
                    stable_key=task.stable_key,
                    version_id=plan.id,
                    duration_hours=task.effort_likely_hours,
                )
                for task in tasks
            ],
            graph_edges,
            plan.id,
        )
        start = project.start_date or plan.created_at.date()
        baseline_forecast = capacity_forecast(
            total_effort_hours=sum((task.effort_likely_hours for task in tasks), start=Decimal(0)),
            capacity_hours_per_week=project.capacity_hours_per_week,
            start_date=start,
            deadline=project.deadline,
        )
        scenario_forecast = capacity_forecast(
            total_effort_hours=sum(durations.values(), start=Decimal(0)),
            capacity_hours_per_week=(
                payload.overrides.capacity_hours_per_week or project.capacity_hours_per_week
            ),
            start_date=start,
            deadline=payload.overrides.deadline or project.deadline,
        )
        baseline_payload = self._forecast_payload(baseline_forecast, baseline_critical)
        scenario_payload = self._forecast_payload(scenario_forecast, critical)
        baseline_payload["capacity_ranges"] = self._capacity_ranges(
            project,
            plan,
            tasks,
            graph_edges,
            project.capacity_hours_per_week,
            {},
        )
        scenario_payload["capacity_ranges"] = self._capacity_ranges(
            project,
            plan,
            tasks,
            graph_edges,
            scenario_forecast.capacity_hours_per_week,
            payload.overrides.task_effort_hours,
        )
        return {
            "baseline": baseline_payload,
            "scenario": scenario_payload,
            "delta": {
                "effort_hours": str(
                    scenario_forecast.total_effort_hours - baseline_forecast.total_effort_hours
                ),
                "forecast_finish_days": (
                    scenario_forecast.forecast_finish - baseline_forecast.forecast_finish
                ).days,
                "critical_path_hours": str(
                    critical.duration_hours - baseline_critical.duration_hours
                ),
                "critical_tasks_added": sorted(
                    set(critical.critical_keys) - set(baseline_critical.critical_keys)
                ),
                "critical_tasks_removed": sorted(
                    set(baseline_critical.critical_keys) - set(critical.critical_keys)
                ),
            },
            "sources": {
                "baseline_version_id": str(plan.id),
                "baseline_content_hash": plan.content_hash,
                "task_count": len(snapshot["tasks"]),
            },
        }

    def _validate_risk_relations(self, plan: PlanVersion, relations: list[Any]) -> None:
        task_keys = set(
            self.session.scalars(select(Task.stable_key).where(Task.version_id == plan.id))
        )
        milestone_keys = set(
            self.session.scalars(
                select(Milestone.stable_key).where(Milestone.version_id == plan.id)
            )
        )
        task_key_by_id = {
            task_id: key
            for task_id, key in self.session.execute(
                select(Task.id, Task.stable_key).where(Task.version_id == plan.id)
            ).tuples()
        }
        dependency_refs = {
            f"{predecessor_key}->{successor_key}"
            for predecessor_id, successor_id in self.session.execute(
                select(
                    TaskDependency.predecessor_id,
                    TaskDependency.successor_id,
                ).where(TaskDependency.version_id == plan.id)
            ).tuples()
            if (predecessor_key := task_key_by_id.get(predecessor_id))
            and (successor_key := task_key_by_id.get(successor_id))
        }
        requirement_ids = {
            str(item)
            for item in self.session.scalars(
                select(ProjectRequirement.id).where(
                    ProjectRequirement.project_id == plan.project_id
                )
            )
        }
        allowed = {
            "task": task_keys,
            "milestone": milestone_keys,
            "dependency": dependency_refs,
            "requirement": requirement_ids,
        }
        unknown = [
            f"{item.entity_type}:{item.entity_ref}"
            for item in relations
            if item.entity_ref not in allowed[item.entity_type]
        ]
        if unknown:
            raise PlanLifecycleConflictError(
                "Risk relations reference entities outside this plan: " + ", ".join(sorted(unknown))
            )

    def _next_risk_key(self, version_id: UUID) -> str:
        keys = list(
            self.session.scalars(select(Risk.stable_key).where(Risk.version_id == version_id))
        )
        highest = max(
            (
                int(key.split("-", 1)[1])
                for key in keys
                if key.startswith("RISK-") and key.split("-", 1)[1].isdigit()
            ),
            default=0,
        )
        return f"RISK-{highest + 1:03d}"

    @staticmethod
    def _severity(probability: str, impact: str) -> int:
        return {"unlikely": 1, "possible": 2, "likely": 3}[probability] * {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }[impact]

    def _invalidate_plan(self, plan: PlanVersion) -> None:
        self.session.flush()
        plan.quality_status = "failed"
        plan.quality_report = {
            "passed": False,
            "issues": [
                {
                    "severity": "must",
                    "code": "VALIDATION_REQUIRED",
                    "path": "$",
                    "message": "Risk content changed and must be validated.",
                    "references": [],
                }
            ],
            "warning_codes": [],
            "calculation_versions": {"quality": "persisted-quality-v1"},
        }
        plan.content_hash = persisted_content_hash(self.session, plan)
        plan.updated_at = utc_now()

    def _commit_risk(
        self,
        plan: PlanVersion,
        risk: Risk,
        action: str,
        before: dict[str, Any] | None,
    ) -> None:
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=plan.project_id,
                action=action,
                entity_type="Risk",
                entity_id=risk.id,
                request_id=self.request_id,
                before_ref=before,
                after_ref={
                    "stable_key": risk.stable_key,
                    "severity": risk.severity,
                    "status": risk.status,
                    "content_hash": plan.content_hash,
                },
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Risk change conflicts with persisted state."
            ) from error

    @staticmethod
    def _forecast_payload(forecast: Any, critical: Any) -> dict[str, Any]:
        payload = asdict(forecast)
        payload["forecast_finish"] = forecast.forecast_finish.isoformat()
        payload["total_effort_hours"] = str(forecast.total_effort_hours)
        payload["capacity_hours_per_week"] = str(forecast.capacity_hours_per_week)
        payload["forecast_weeks"] = str(forecast.forecast_weeks)
        payload["critical_path_hours"] = str(critical.duration_hours)
        payload["critical_tasks"] = list(critical.critical_keys)
        return payload

    def _capacity_ranges(
        self,
        project: Project,
        plan: PlanVersion,
        tasks: list[Task],
        edges: list[DependencyEdge],
        total_capacity: Decimal,
        likely_overrides: dict[str, Decimal],
    ) -> dict[str, Any]:
        names = sorted({name for task in tasks for name in task.workstreams})
        if not names:
            return {}
        capacity = total_capacity / Decimal(len(names))
        calendar = self.session.scalar(
            select(WorkCalendar)
            .where(WorkCalendar.project_id == project.id)
            .order_by(WorkCalendar.created_at.desc())
        )
        parallel_limit = calendar.parallel_limit if calendar is not None else 1
        ranges = schedule_capacity_ranges(
            [
                AdvancedScheduleTask(
                    id=task.id,
                    stable_key=task.stable_key,
                    version_id=plan.id,
                    effort_min_hours=min(
                        task.effort_min_hours,
                        likely_overrides.get(task.stable_key, task.effort_likely_hours),
                    ),
                    effort_likely_hours=likely_overrides.get(
                        task.stable_key, task.effort_likely_hours
                    ),
                    effort_max_hours=max(
                        task.effort_max_hours,
                        likely_overrides.get(task.stable_key, task.effort_likely_hours),
                    ),
                    workstreams=tuple(task.workstreams),
                )
                for task in tasks
            ],
            edges,
            version_id=plan.id,
            workstream_capacity_hours_per_week={name: capacity for name in names},
            workstream_parallel_limit={name: parallel_limit for name in names},
        )
        return {
            name: {
                "finish_week": str(result.finish_week),
                "tasks": {
                    result.tasks[task_id].stable_key: {
                        "start_week": str(result.tasks[task_id].start_week),
                        "finish_week": str(result.tasks[task_id].finish_week),
                        "duration_weeks": str(result.tasks[task_id].duration_weeks),
                        "workstreams": list(result.tasks[task_id].workstreams),
                    }
                    for task_id in result.tasks
                },
                "calculation_version": result.calculation_version,
            }
            for name, result in ranges.items()
        }

    @staticmethod
    def _deterministic_explanation(result: dict[str, Any]) -> dict[str, Any]:
        delta = result["delta"]
        return {
            "summary": (
                f"Forecast changes by {delta['forecast_finish_days']} day(s); "
                f"effort changes by {delta['effort_hours']} hour(s)."
            ),
            "tradeoffs": [
                {
                    "metric": "critical_path_hours",
                    "delta": delta["critical_path_hours"],
                    "evidence_ref": "result.delta.critical_path_hours",
                }
            ],
            "source": "deterministic",
        }

    def _apply_virtual_replacements(
        self,
        candidate: dict[str, Any],
        payload: RegenerationCreate,
    ) -> None:
        indexes = {
            entity: {item["stable_key"]: item for item in candidate[f"{entity}s"]}
            for entity in ("task", "milestone")
        }
        for replacement in payload.replacements:
            item = indexes[replacement.entity_type].get(replacement.stable_key)
            if item is None:
                raise PlanLifecycleConflictError(
                    f"Regeneration target {replacement.stable_key} does not exist."
                )
            self._require_regenerable(item, replacement.entity_type, set(replacement.values))
            item.update(self._normalize_values(replacement.values))

    def _apply_persisted_replacements(
        self,
        plan: PlanVersion,
        replacements: list[dict[str, Any]],
    ) -> None:
        task_by_key = {
            item.stable_key: item
            for item in self.session.scalars(select(Task).where(Task.version_id == plan.id))
        }
        milestone_by_key = {
            item.stable_key: item
            for item in self.session.scalars(
                select(Milestone).where(Milestone.version_id == plan.id)
            )
        }
        for replacement in replacements:
            entity_type = replacement["entity_type"]
            collection = task_by_key if entity_type == "task" else milestone_by_key
            item = collection.get(replacement["stable_key"])
            if item is None:
                raise PlanLifecycleConflictError("Regeneration target no longer exists.")
            self._require_regenerable(
                {
                    "locked": item.locked,
                    "protected": item.protected,
                    "source": item.source,
                },
                entity_type,
                set(replacement["values"]),
            )
            for field, value in self._normalize_values(replacement["values"]).items():
                setattr(item, field, value)

    @staticmethod
    def _require_regenerable(
        item: dict[str, Any],
        entity_type: str,
        fields: set[str],
    ) -> None:
        allowed = TASK_FIELDS if entity_type == "task" else MILESTONE_FIELDS
        unsupported = fields - allowed
        if unsupported:
            raise PlanLifecycleConflictError(
                f"Fields cannot be regenerated: {', '.join(sorted(unsupported))}."
            )
        if item["locked"] or item["protected"] or item["source"] == "user":
            raise PlanLifecycleConflictError(
                "Locked, protected, or user-edited items cannot be regenerated."
            )

    @staticmethod
    def _normalize_values(values: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        for field in DECIMAL_FIELDS & normalized.keys():
            normalized[field] = Decimal(str(normalized[field]))
        for field in DATE_FIELDS & normalized.keys():
            value = normalized[field]
            normalized[field] = (
                value if isinstance(value, date) or value is None else date.fromisoformat(value)
            )
        return normalized

    @staticmethod
    def _validate_candidate(candidate: dict[str, Any]) -> None:
        for task in candidate["tasks"]:
            minimum = Decimal(str(task["effort_min_hours"]))
            likely = Decimal(str(task["effort_likely_hours"]))
            maximum = Decimal(str(task["effort_max_hours"]))
            if minimum <= 0 or not minimum <= likely <= maximum:
                raise PlanLifecycleConflictError(
                    f"Regeneration produced invalid effort for {task['stable_key']}."
                )
            for field in ("title", "description", "deliverable"):
                if not str(task[field]).strip():
                    raise PlanLifecycleConflictError(
                        f"Regeneration produced empty {field} for {task['stable_key']}."
                    )
        for milestone in candidate["milestones"]:
            if Decimal(str(milestone["planned_effort_hours"])) <= 0:
                raise PlanLifecycleConflictError(
                    f"Regeneration produced invalid effort for {milestone['stable_key']}."
                )

    def _project(self, project_id: UUID) -> Project:
        project = self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if project is None:
            raise PlanResourceNotFoundError
        return project

    def _active_plan(self, project_id: UUID) -> PlanVersion:
        plan = self.session.scalar(
            self.policy._plans().where(
                PlanVersion.project_id == project_id,
                PlanVersion.state == "active",
            )
        )
        if plan is None:
            raise PlanLifecycleConflictError("Project has no active plan for a scenario baseline.")
        return plan

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(canonical_json(value))

    def _commit_proposal(
        self,
        proposal: RegenerationProposal,
        action: str,
        *,
        reason: str | None = None,
    ) -> None:
        try:
            self.session.flush()
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=proposal.project_id,
                action=action,
                entity_type="RegenerationProposal",
                entity_id=proposal.id,
                request_id=self.request_id,
                after_ref={
                    "status": proposal.status,
                    "baseline_content_hash": proposal.baseline_content_hash,
                    "reason": reason,
                },
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Regeneration proposal conflicts with persisted state."
            ) from error
