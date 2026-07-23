"""Owner-scoped draft CRUD, validation, lifecycle, and comparison services."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
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
from app.core.hashing import canonical_hash
from app.db.base import utc_now
from app.db.models.plan import (
    Milestone,
    PlanApproval,
    PlanVersion,
    ProjectAnalysis,
    Risk,
    Task,
    TaskDependency,
)
from app.domain.graph import (
    DependencyEdge,
    GraphTask,
    GraphValidationError,
    TaskStatus,
    validate_graph,
)
from app.schemas.plan import (
    DependencyCreate,
    MilestoneCreate,
    MilestoneUpdate,
    PlanMetadataUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.services.audit import AuditRecorder
from app.services.plan_content import (
    compare_plan_content,
    persisted_content_hash,
    plan_content_snapshot,
)
from app.services.plan_quality import QualityReport
from app.services.plan_validation import validate_persisted_plan


@dataclass(frozen=True, slots=True)
class PlanGraph:
    plan: PlanVersion
    analysis: ProjectAnalysis | None
    milestones: list[Milestone]
    tasks: list[Task]
    dependencies: list[TaskDependency]
    risks: list[Risk]
    approvals: list[PlanApproval]


class PlanService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.policy = PlanLifecyclePolicy(session, owner_id)
        self.audit = AuditRecorder(session)

    def list_versions(self, project_id: UUID) -> list[PlanVersion]:
        project_plan = self.session.scalar(
            self.policy._plans().where(PlanVersion.project_id == project_id).limit(1)
        )
        if project_plan is None:
            # Avoid exposing whether another owner's project or versions exist.
            from app.db.models.project import Project

            owned_project = self.session.scalar(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.owner_id == self.owner_id,
                    Project.status == "active",
                )
            )
            if owned_project is None:
                raise PlanResourceNotFoundError
        return list(
            self.session.scalars(
                self.policy._plans()
                .where(PlanVersion.project_id == project_id)
                .order_by(PlanVersion.number.desc())
            )
        )

    def graph(self, version_id: UUID) -> PlanGraph:
        plan = self.policy.plan(version_id)
        return self._graph(plan)

    def update_plan(
        self,
        version_id: UUID,
        payload: PlanMetadataUpdate,
        expected_version: int,
    ) -> PlanGraph:
        plan = self.policy.mutable_draft(version_id, expected_version)
        analysis = self.session.scalar(
            select(ProjectAnalysis).where(ProjectAnalysis.version_id == plan.id)
        )
        if analysis is None:
            raise PlanLifecycleConflictError("Draft analysis is missing.")
        values = payload.model_dump(exclude_unset=True)
        before = self._plan_ref(plan)
        if "reason" in values:
            plan.reason = values.pop("reason")
        for api_field, model_field in (
            ("analysis_summary", "summary"),
            ("mvp_boundary", "mvp_boundary"),
            ("excluded_scope", "excluded_scope"),
            ("assumptions", "assumptions"),
        ):
            if api_field in values:
                setattr(analysis, model_field, values[api_field])
        self._invalidate(plan)
        self._commit_change(plan, "DraftEdited", "PlanVersion", plan.id, before)
        return self.graph(plan.id)

    def list_milestones(self, version_id: UUID) -> list[Milestone]:
        plan = self.policy.plan(version_id)
        return list(
            self.session.scalars(
                select(Milestone)
                .where(Milestone.version_id == plan.id)
                .order_by(Milestone.sequence, Milestone.stable_key)
            )
        )

    def create_milestone(
        self,
        version_id: UUID,
        payload: MilestoneCreate,
        expected_version: int,
    ) -> tuple[Milestone, PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        sequence_conflict = self.session.scalar(
            select(Milestone.id).where(
                Milestone.version_id == plan.id,
                Milestone.sequence == payload.sequence,
            )
        )
        if sequence_conflict is not None:
            raise PlanLifecycleConflictError("Milestone sequence is already in use.")
        milestone = Milestone(
            version_id=plan.id,
            stable_key=self._next_key(Milestone, plan.id, "MS"),
            module_refs=payload.module_refs,
            name=payload.name,
            description=payload.description,
            objective=payload.objective,
            deliverable=payload.deliverable,
            sequence=payload.sequence,
            target_date=payload.target_date,
            planned_effort_hours=payload.planned_effort_hours,
            acceptance_criteria=payload.acceptance_criteria,
            planned_start=None,
            planned_finish=None,
            status="pending",
            source="user",
            protected=True,
            locked=payload.locked,
        )
        self.session.add(milestone)
        self.session.flush()
        self._invalidate(plan)
        self._commit_change(
            plan,
            "DraftMilestoneChanged",
            "Milestone",
            milestone.id,
            None,
        )
        return self.policy.milestone(self.policy.plan(plan.id), milestone.id), self.policy.plan(
            plan.id
        )

    def update_milestone(
        self,
        version_id: UUID,
        milestone_id: UUID,
        payload: MilestoneUpdate,
        expected_version: int,
    ) -> tuple[Milestone, PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        milestone = self.policy.milestone(plan, milestone_id)
        values = payload.model_dump(exclude_unset=True)
        self._require_human_edit_allowed(milestone.locked, values)
        before = self._item_ref(milestone)
        for field, value in values.items():
            setattr(milestone, field, value)
        milestone.source = "user"
        milestone.protected = True
        self._invalidate(plan)
        self._commit_change(
            plan,
            "DraftMilestoneChanged",
            "Milestone",
            milestone.id,
            before,
        )
        return self.policy.milestone(self.policy.plan(plan.id), milestone.id), self.policy.plan(
            plan.id
        )

    def delete_milestone(
        self,
        version_id: UUID,
        milestone_id: UUID,
        expected_version: int,
    ) -> PlanVersion:
        plan = self.policy.mutable_draft(version_id, expected_version)
        milestone = self.policy.milestone(plan, milestone_id)
        if milestone.locked:
            raise PlanLifecycleConflictError("Unlock the milestone before deleting it.")
        before = self._item_ref(milestone)
        self.session.delete(milestone)
        self.session.flush()
        self._invalidate(plan)
        self._commit_change(
            plan,
            "DraftMilestoneChanged",
            "Milestone",
            milestone_id,
            before,
        )
        return self.policy.plan(plan.id)

    def list_tasks(self, version_id: UUID) -> list[Task]:
        plan = self.policy.plan(version_id)
        return list(
            self.session.scalars(
                select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key)
            )
        )

    def create_task(
        self,
        version_id: UUID,
        payload: TaskCreate,
        expected_version: int,
    ) -> tuple[Task, PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        self.policy.milestone(plan, payload.milestone_id)
        if payload.parent_id is not None:
            self.policy.task(plan, payload.parent_id)
        task = Task(
            version_id=plan.id,
            milestone_id=payload.milestone_id,
            parent_id=payload.parent_id,
            stable_key=self._next_key(Task, plan.id, "TASK"),
            title=payload.title,
            description=payload.description,
            deliverable=payload.deliverable,
            acceptance_criteria=payload.acceptance_criteria,
            definition_of_done=payload.definition_of_done,
            effort_min_hours=payload.effort_min_hours,
            effort_likely_hours=payload.effort_likely_hours,
            effort_max_hours=payload.effort_max_hours,
            complexity=payload.complexity,
            workstreams=payload.workstreams,
            skill_tags=payload.skill_tags,
            source="user",
            requirement_refs=payload.requirement_refs,
            assumption_refs=payload.assumption_refs,
            locked=payload.locked,
            protected=True,
            priority_score=Decimal(0),
            priority_label="Low",
            priority_breakdown=payload.priority_factors.model_dump(mode="json"),
            planned_start=None,
            planned_finish=None,
            status="pending",
        )
        self.session.add(task)
        self.session.flush()
        self._ensure_graph(plan.id)
        self._invalidate(plan)
        self._commit_change(plan, "DraftTaskChanged", "Task", task.id, None)
        return self.policy.task(self.policy.plan(plan.id), task.id), self.policy.plan(plan.id)

    def update_task(
        self,
        version_id: UUID,
        task_id: UUID,
        payload: TaskUpdate,
        expected_version: int,
    ) -> tuple[Task, PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        task = self.policy.task(plan, task_id)
        values = payload.model_dump(exclude_unset=True)
        self._require_human_edit_allowed(task.locked, values)
        if "milestone_id" in values:
            self.policy.milestone(plan, values["milestone_id"])
        if "parent_id" in values and values["parent_id"] is not None:
            if values["parent_id"] == task.id:
                raise PlanLifecycleConflictError("A task cannot be its own parent.")
            self.policy.task(plan, values["parent_id"])
        before = self._item_ref(task)
        factors = values.pop("priority_factors", None)
        for field, value in values.items():
            setattr(task, field, value)
        if not task.effort_min_hours <= task.effort_likely_hours <= task.effort_max_hours:
            raise PlanLifecycleConflictError("Task effort must satisfy min <= likely <= max.")
        if factors is not None:
            task.priority_breakdown = factors
        task.source = "user"
        task.protected = True
        self.session.flush()
        self._ensure_graph(plan.id)
        self._invalidate(plan)
        self._commit_change(plan, "DraftTaskChanged", "Task", task.id, before)
        return self.policy.task(self.policy.plan(plan.id), task.id), self.policy.plan(plan.id)

    def delete_task(
        self,
        version_id: UUID,
        task_id: UUID,
        expected_version: int,
    ) -> PlanVersion:
        plan = self.policy.mutable_draft(version_id, expected_version)
        task = self.policy.task(plan, task_id)
        if task.locked:
            raise PlanLifecycleConflictError("Unlock the task before deleting it.")
        before = self._item_ref(task)
        self.session.delete(task)
        self.session.flush()
        self._ensure_graph(plan.id)
        self._invalidate(plan)
        self._commit_change(plan, "DraftTaskChanged", "Task", task_id, before)
        return self.policy.plan(plan.id)

    def list_dependencies(self, version_id: UUID) -> list[TaskDependency]:
        plan = self.policy.plan(version_id)
        return list(
            self.session.scalars(
                select(TaskDependency)
                .where(TaskDependency.version_id == plan.id)
                .order_by(TaskDependency.predecessor_id, TaskDependency.successor_id)
            )
        )

    def create_dependency(
        self,
        version_id: UUID,
        payload: DependencyCreate,
        expected_version: int,
    ) -> tuple[TaskDependency, PlanVersion]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        self.policy.task(plan, payload.predecessor_id)
        self.policy.task(plan, payload.successor_id)
        dependency = TaskDependency(
            version_id=plan.id,
            predecessor_id=payload.predecessor_id,
            successor_id=payload.successor_id,
            dependency_type="finish_to_start",
            reason=payload.reason,
            evidence_refs=payload.evidence_refs,
            confidence_label=payload.confidence_label,
            source="user",
            protected=True,
        )
        self.session.add(dependency)
        try:
            self.session.flush()
            self._ensure_graph(plan.id)
        except (IntegrityError, GraphValidationError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(str(error)) from error
        self._invalidate(plan)
        self._commit_change(
            plan,
            "DependencyChanged",
            "TaskDependency",
            dependency.id,
            None,
        )
        return self.policy.dependency(self.policy.plan(plan.id), dependency.id), self.policy.plan(
            plan.id
        )

    def delete_dependency(
        self,
        version_id: UUID,
        dependency_id: UUID,
        expected_version: int,
    ) -> PlanVersion:
        plan = self.policy.mutable_draft(version_id, expected_version)
        dependency = self.policy.dependency(plan, dependency_id)
        before = {
            "predecessor_id": str(dependency.predecessor_id),
            "successor_id": str(dependency.successor_id),
        }
        self.session.delete(dependency)
        self.session.flush()
        self._invalidate(plan)
        self._commit_change(
            plan,
            "DependencyChanged",
            "TaskDependency",
            dependency_id,
            before,
        )
        return self.policy.plan(plan.id)

    def validate(
        self,
        version_id: UUID,
        expected_version: int,
    ) -> tuple[PlanVersion, QualityReport]:
        plan = self.policy.mutable_draft(version_id, expected_version)
        before = self._plan_ref(plan)
        report = validate_persisted_plan(self.session, plan, apply_calculations=True)
        self._commit_change(
            plan,
            "PlanValidated",
            "PlanVersion",
            plan.id,
            before,
            after_extra={"passed": report.passed},
        )
        return self.policy.plan(plan.id), report

    def submit_review(self, version_id: UUID, expected_version: int) -> PlanGraph:
        plan = self.policy.mutable_draft(version_id, expected_version)
        before = self._plan_ref(plan)
        report = validate_persisted_plan(self.session, plan, apply_calculations=True)
        if not report.passed:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Draft cannot enter review until all required validation issues are resolved."
            )
        plan.state = "under_review"
        plan.updated_at = utc_now()
        self._commit_change(
            plan,
            "PlanReviewStarted",
            "PlanVersion",
            plan.id,
            before,
        )
        return self.graph(plan.id)

    def archive(self, version_id: UUID, expected_version: int) -> PlanGraph:
        plan = self.policy.plan(version_id, lock=True)
        self.policy.require_version(plan, expected_version)
        self.policy.require_state(plan, {"draft", "superseded"})
        before = self._plan_ref(plan)
        plan.state = "archived"
        plan.updated_at = utc_now()
        self._commit_change(plan, "PlanArchived", "PlanVersion", plan.id, before)
        return self.graph(plan.id)

    def compare(self, from_id: UUID, to_id: UUID) -> list[dict[str, Any]]:
        before = self.policy.plan(from_id)
        after = self.policy.plan(to_id)
        if before.project_id != after.project_id:
            raise PlanResourceNotFoundError
        return compare_plan_content(
            plan_content_snapshot(self.session, before),
            plan_content_snapshot(self.session, after),
        )

    def _graph(self, plan: PlanVersion) -> PlanGraph:
        return PlanGraph(
            plan=plan,
            analysis=self.session.scalar(
                select(ProjectAnalysis).where(ProjectAnalysis.version_id == plan.id)
            ),
            milestones=list(
                self.session.scalars(
                    select(Milestone)
                    .where(Milestone.version_id == plan.id)
                    .order_by(Milestone.sequence, Milestone.stable_key)
                )
            ),
            tasks=list(
                self.session.scalars(
                    select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key)
                )
            ),
            dependencies=list(
                self.session.scalars(
                    select(TaskDependency)
                    .where(TaskDependency.version_id == plan.id)
                    .order_by(TaskDependency.predecessor_id, TaskDependency.successor_id)
                )
            ),
            risks=list(
                self.session.scalars(
                    select(Risk).where(Risk.version_id == plan.id).order_by(Risk.stable_key)
                )
            ),
            approvals=list(
                self.session.scalars(
                    select(PlanApproval)
                    .where(PlanApproval.version_id == plan.id)
                    .order_by(PlanApproval.created_at, PlanApproval.id)
                )
            ),
        )

    def _invalidate(self, plan: PlanVersion) -> None:
        self.session.flush()
        plan.quality_status = "failed"
        plan.quality_report = {
            "passed": False,
            "issues": [
                {
                    "severity": "must",
                    "code": "VALIDATION_REQUIRED",
                    "path": "$",
                    "message": "Draft content changed and must be validated again.",
                    "references": [],
                }
            ],
            "warning_codes": [],
            "calculation_versions": {"quality": "persisted-quality-v1"},
        }
        plan.content_hash = persisted_content_hash(self.session, plan)
        plan.updated_at = utc_now()

    def _commit_change(
        self,
        plan: PlanVersion,
        action: str,
        entity_type: str,
        entity_id: UUID,
        before: dict[str, Any] | None,
        *,
        after_extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.session.flush()
            after = self._plan_ref(plan)
            if after_extra:
                after.update(after_extra)
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=plan.project_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=self.request_id,
                before_ref=before,
                after_ref=after,
            )
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Plan change conflicts with persisted state."
            ) from error

    def _ensure_graph(self, version_id: UUID) -> None:
        tasks = list(self.session.scalars(select(Task).where(Task.version_id == version_id)))
        self._ensure_parent_tree(tasks)
        dependencies = list(
            self.session.scalars(
                select(TaskDependency).where(TaskDependency.version_id == version_id)
            )
        )
        validate_graph(
            [
                GraphTask(
                    id=item.id,
                    stable_key=item.stable_key,
                    version_id=version_id,
                    status=cast(TaskStatus, item.status),
                )
                for item in tasks
            ],
            [
                DependencyEdge(
                    predecessor_id=item.predecessor_id,
                    successor_id=item.successor_id,
                    version_id=version_id,
                )
                for item in dependencies
            ],
            version_id,
        )

    @staticmethod
    def _ensure_parent_tree(tasks: list[Task]) -> None:
        parent_by_id = {item.id: item.parent_id for item in tasks}
        key_by_id = {item.id: item.stable_key for item in tasks}
        for task in tasks:
            path: set[UUID] = set()
            current: UUID | None = task.id
            while current is not None:
                if current in path:
                    raise PlanLifecycleConflictError(
                        f"Task parent cycle detected at {key_by_id.get(current, current)}."
                    )
                path.add(current)
                current = parent_by_id.get(current)

    def _next_key(self, model: type[Milestone] | type[Task], version_id: UUID, prefix: str) -> str:
        keys = list(
            self.session.scalars(select(model.stable_key).where(model.version_id == version_id))
        )
        highest = max(
            (
                int(key.split("-", 1)[1])
                for key in keys
                if key.startswith(f"{prefix}-") and key.split("-", 1)[1].isdigit()
            ),
            default=0,
        )
        return f"{prefix}-{highest + 1:03d}"

    @staticmethod
    def _require_human_edit_allowed(locked: bool, values: dict[str, Any]) -> None:
        if locked and not (set(values) == {"locked"} and values["locked"] is False):
            raise PlanLifecycleConflictError(
                "Unlock this protected item before changing its content."
            )

    @staticmethod
    def _plan_ref(plan: PlanVersion) -> dict[str, Any]:
        return {
            "number": plan.number,
            "state": plan.state,
            "row_version": plan.row_version,
            "content_hash": plan.content_hash,
            "quality_status": plan.quality_status,
        }

    @staticmethod
    def _item_ref(item: Milestone | Task) -> dict[str, Any]:
        return {
            "stable_key": item.stable_key,
            "row_version": item.row_version,
            "locked": item.locked,
            "source": item.source,
            "protected": item.protected,
            "fingerprint": canonical_hash(
                {
                    "stable_key": item.stable_key,
                    "updated_at": item.updated_at,
                    "row_version": item.row_version,
                }
            ),
        }
