"""Exact-hash review decisions and atomic plan activation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.auth.policies import PlanLifecycleConflictError, PlanLifecyclePolicy
from app.db.base import utc_now
from app.db.models.plan import PlanApproval, PlanVersion
from app.db.models.project import Project
from app.services.audit import AuditRecorder
from app.services.execution import initialize_active_plan
from app.services.plan_content import persisted_content_hash
from app.services.plan_validation import validate_persisted_plan
from app.services.plans import PlanGraph, PlanService


class ApprovalService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.policy = PlanLifecyclePolicy(session, owner_id)
        self.audit = AuditRecorder(session)

    def request_changes(
        self,
        version_id: UUID,
        expected_version: int,
        reason: str,
    ) -> PlanGraph:
        plan = self.policy.plan(version_id, lock=True)
        self.policy.require_version(plan, expected_version)
        self.policy.require_state(plan, "under_review")
        self._require_unchanged(plan, plan.content_hash)
        before = self._ref(plan)
        self.session.add(
            PlanApproval(
                project_id=plan.project_id,
                version_id=plan.id,
                actor_id=self.owner_id,
                decision="changes_requested",
                reason=reason,
                content_hash=plan.content_hash,
            )
        )
        plan.state = "draft"
        plan.updated_at = utc_now()
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=plan.project_id,
            action="PlanChangesRequested",
            entity_type="PlanVersion",
            entity_id=plan.id,
            request_id=self.request_id,
            before_ref=before,
            after_ref={**self._ref(plan), "reason_recorded": True},
        )
        self._commit()
        return PlanService(
            self.session,
            self.owner_id,
            self.request_id,
        ).graph(plan.id)

    def approve_and_activate(
        self,
        version_id: UUID,
        expected_version: int,
        content_hash: str,
        reason: str | None,
    ) -> PlanGraph:
        plan_unlocked = self.policy.plan(version_id)
        project = self.session.scalar(
            select(Project)
            .where(
                Project.id == plan_unlocked.project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
            .with_for_update()
        )
        if project is None:
            from app.auth.policies import PlanResourceNotFoundError

            raise PlanResourceNotFoundError
        plan = self.policy.plan(version_id, lock=True)
        self.policy.require_version(plan, expected_version)
        self.policy.require_state(plan, "under_review")
        self._require_unchanged(plan, content_hash)
        report = validate_persisted_plan(self.session, plan, apply_calculations=False)
        if not report.passed or plan.quality_status != "passed":
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Only a draft with a passed quality gate can be activated."
            )

        previous = self.session.scalar(
            select(PlanVersion)
            .where(
                PlanVersion.project_id == plan.project_id,
                PlanVersion.state == "active",
                PlanVersion.id != plan.id,
            )
            .with_for_update()
        )
        previous_ref = self._ref(previous) if previous is not None else None
        if previous is not None:
            previous.state = "superseded"
            previous.updated_at = utc_now()
            self.session.flush()

        approved_hash = plan.content_hash
        approval = PlanApproval(
            project_id=plan.project_id,
            version_id=plan.id,
            actor_id=self.owner_id,
            decision="approved",
            reason=reason,
            content_hash=approved_hash,
        )
        self.session.add(approval)
        self.session.flush()
        before = self._ref(plan)
        plan.state = "active"
        plan.updated_at = utc_now()
        initialize_active_plan(
            self.session,
            plan,
            owner_id=self.owner_id,
            request_id=self.request_id,
        )
        if previous is not None:
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=self.owner_id,
                project_id=plan.project_id,
                action="PlanSuperseded",
                entity_type="PlanVersion",
                entity_id=previous.id,
                request_id=self.request_id,
                before_ref=previous_ref,
                after_ref=self._ref(previous),
            )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=plan.project_id,
            action="PlanApproved",
            entity_type="PlanApproval",
            entity_id=approval.id,
            request_id=self.request_id,
            after_ref={
                "version_id": str(plan.id),
                "content_hash": approved_hash,
                "decision": "approved",
            },
        )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=plan.project_id,
            action="PlanActivated",
            entity_type="PlanVersion",
            entity_id=plan.id,
            request_id=self.request_id,
            before_ref=before,
            after_ref=self._ref(plan),
        )
        self._commit()
        return PlanService(
            self.session,
            self.owner_id,
            self.request_id,
        ).graph(plan.id)

    def _require_unchanged(self, plan: PlanVersion, supplied_hash: str) -> None:
        current_hash = persisted_content_hash(self.session, plan)
        if current_hash != plan.content_hash:
            raise PlanLifecycleConflictError(
                "Reviewed plan content changed after its hash was recorded."
            )
        if supplied_hash != current_hash:
            raise PlanLifecycleConflictError(
                "Approval content hash does not match the reviewed plan."
            )

    def _commit(self) -> None:
        try:
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise PlanLifecycleConflictError(
                "Plan approval conflicts with persisted lifecycle state."
            ) from error

    @staticmethod
    def _ref(plan: PlanVersion | None) -> dict[str, object]:
        if plan is None:
            return {}
        return {
            "number": plan.number,
            "state": plan.state,
            "row_version": plan.row_version,
            "content_hash": plan.content_hash,
        }
