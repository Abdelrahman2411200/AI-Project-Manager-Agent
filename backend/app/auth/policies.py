"""Central owner and lifecycle policies for plan-version resources."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models.plan import Milestone, PlanVersion, Task, TaskDependency
from app.db.models.project import Project


class PlanResourceNotFoundError(LookupError):
    pass


class PlanLifecycleConflictError(RuntimeError):
    pass


class PlanLifecyclePolicy:
    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def _plans(self) -> Select[tuple[PlanVersion]]:
        return select(PlanVersion).join(
            Project,
            (Project.id == PlanVersion.project_id)
            & (Project.owner_id == self.owner_id)
            & (Project.status == "active"),
        )

    def plan(self, version_id: UUID, *, lock: bool = False) -> PlanVersion:
        query = self._plans().where(PlanVersion.id == version_id)
        if lock:
            query = query.with_for_update()
        plan = self.session.scalar(query)
        if plan is None:
            raise PlanResourceNotFoundError
        return plan

    def project_plan(
        self,
        project_id: UUID,
        version_id: UUID,
        *,
        lock: bool = False,
    ) -> PlanVersion:
        plan = self.plan(version_id, lock=lock)
        if plan.project_id != project_id:
            raise PlanResourceNotFoundError
        return plan

    @staticmethod
    def require_version(plan: PlanVersion, expected_version: int) -> None:
        if plan.row_version != expected_version:
            raise PlanLifecycleConflictError(
                f"Plan version conflict: expected {expected_version}, current {plan.row_version}."
            )

    @staticmethod
    def require_state(plan: PlanVersion, allowed: str | Iterable[str]) -> None:
        states = {allowed} if isinstance(allowed, str) else set(allowed)
        if plan.state not in states:
            expected = ", ".join(sorted(states))
            raise PlanLifecycleConflictError(
                f"Plan state conflict: expected {expected}, current {plan.state}."
            )

    def mutable_draft(self, version_id: UUID, expected_version: int) -> PlanVersion:
        plan = self.plan(version_id, lock=True)
        self.require_version(plan, expected_version)
        self.require_state(plan, "draft")
        return plan

    def milestone(self, plan: PlanVersion, milestone_id: UUID) -> Milestone:
        milestone = self.session.scalar(
            select(Milestone).where(
                Milestone.id == milestone_id,
                Milestone.version_id == plan.id,
            )
        )
        if milestone is None:
            raise PlanResourceNotFoundError
        return milestone

    def task(self, plan: PlanVersion, task_id: UUID) -> Task:
        task = self.session.scalar(
            select(Task).where(Task.id == task_id, Task.version_id == plan.id)
        )
        if task is None:
            raise PlanResourceNotFoundError
        return task

    def dependency(self, plan: PlanVersion, dependency_id: UUID) -> TaskDependency:
        dependency = self.session.scalar(
            select(TaskDependency).where(
                TaskDependency.id == dependency_id,
                TaskDependency.version_id == plan.id,
            )
        )
        if dependency is None:
            raise PlanResourceNotFoundError
        return dependency
