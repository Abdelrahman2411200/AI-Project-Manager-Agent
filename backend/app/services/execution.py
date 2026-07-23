"""Atomic active-task transitions, immutable history, and monitoring enqueue."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.core.hashing import canonical_hash
from app.db.base import utc_now
from app.db.models.execution import (
    MonitoringSnapshot,
    ProgressUpdate,
    TaskExecutionProjection,
    TaskStatusEvent,
)
from app.db.models.plan import Milestone, PlanVersion, Task, TaskDependency
from app.db.models.project import Project
from app.db.models.run import AgentJob, AgentRun, AgentRunStep
from app.domain.graph import (
    DependencyEdge,
    GraphTask,
    ReadinessProjection,
    TaskStatus,
    project_readiness,
)
from app.schemas.execution import (
    ExecutionBoardView,
    ProjectHealthView,
    ProjectProgressView,
    TaskExecutionView,
    TaskProgressMutationView,
    TaskProgressUpdateRequest,
    TaskProgressView,
    TaskStatusEventView,
    TaskStatusMutationView,
    TaskStatusTransitionRequest,
)
from app.services.audit import AuditRecorder
from app.services.jobs import JobQueue
from app.services.monitoring import (
    MonitoringService,
)

LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"in_progress", "blocked", "cancelled"}),
    "in_progress": frozenset({"blocked", "completed", "cancelled"}),
    "blocked": frozenset({"ready", "in_progress", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


class ExecutionResourceNotFoundError(LookupError):
    pass


class ExecutionConflictError(RuntimeError):
    pass


def initialize_active_plan(
    session: Session,
    plan: PlanVersion,
    *,
    owner_id: UUID,
    request_id: str,
) -> list[TaskExecutionProjection]:
    """Create one execution projection and initial event per newly active task."""
    existing = list(
        session.scalars(
            select(TaskExecutionProjection).where(TaskExecutionProjection.version_id == plan.id)
        )
    )
    if existing:
        return existing
    tasks = list(
        session.scalars(select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key))
    )
    dependencies = list(
        session.scalars(select(TaskDependency).where(TaskDependency.version_id == plan.id))
    )
    graph_tasks = tuple(
        GraphTask(
            id=item.id,
            stable_key=item.stable_key,
            version_id=plan.id,
            status=cast(TaskStatus, item.status),
        )
        for item in tasks
    )
    graph_edges = tuple(
        DependencyEdge(
            predecessor_id=item.predecessor_id,
            successor_id=item.successor_id,
            version_id=plan.id,
        )
        for item in dependencies
    )
    readiness = project_readiness(graph_tasks, graph_edges, plan.id)
    now = utc_now()
    result: list[TaskExecutionProjection] = []
    for task in tasks:
        status = readiness[task.id].projected_status
        projection = TaskExecutionProjection(
            id=task.id,
            project_id=plan.project_id,
            version_id=plan.id,
            task_id=task.id,
            status=status,
            progress_fraction=Decimal(1) if status == "completed" else Decimal(0),
            actual_effort_hours=Decimal(0),
            status_changed_at=now,
        )
        session.add(projection)
        session.add(
            TaskStatusEvent(
                project_id=plan.project_id,
                version_id=plan.id,
                task_id=task.id,
                actor_id=None,
                actor_type="system",
                from_status=None,
                to_status=status,
                reason="Execution projection initialized when the approved plan became active.",
                progress_fraction=projection.progress_fraction,
                correlation_id=request_id,
                event_key=f"activation:{plan.id}:{task.id}",
                request_hash=canonical_hash(
                    {"plan_id": plan.id, "task_id": task.id, "status": status}
                ),
                occurred_at=now,
            )
        )
        result.append(projection)
    session.flush()
    AuditRecorder(session).append(
        owner_id=owner_id,
        actor_id=owner_id,
        project_id=plan.project_id,
        action="ExecutionInitialized",
        entity_type="PlanVersion",
        entity_id=plan.id,
        request_id=request_id,
        after_ref={
            "task_count": len(result),
            "ready_count": sum(1 for item in result if item.status == "ready"),
        },
    )
    return result


class ExecutionService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.audit = AuditRecorder(session)

    def board(self, project_id: UUID) -> ExecutionBoardView:
        project, plan = self._active_plan(project_id)
        self._ensure_initialized(plan)
        snapshot = MonitoringService(self.session, self.owner_id).ensure_current(project_id)
        self.session.commit()
        tasks = self._tasks(plan.id)
        projections = self._projections(plan.id)
        readiness = self._readiness(plan.id, tasks, projections)
        milestones = self._milestones(plan.id)
        recent = list(
            self.session.scalars(
                select(TaskStatusEvent)
                .where(TaskStatusEvent.version_id == plan.id)
                .order_by(TaskStatusEvent.occurred_at.desc(), TaskStatusEvent.id.desc())
                .limit(30)
            )
        )
        return ExecutionBoardView(
            project_id=project.id,
            version_id=plan.id,
            version_number=plan.number,
            tasks=[
                self._task_view(
                    task,
                    projections[task.id],
                    readiness[task.id],
                    milestones[task.milestone_id],
                    tasks,
                )
                for task in tasks
            ],
            recent_events=[TaskStatusEventView.model_validate(item) for item in recent],
            progress=progress_view(snapshot),
            health=health_view(snapshot),
        )

    def status_history(self, task_id: UUID) -> list[TaskStatusEvent]:
        task, plan, _project, _projection = self._owned_active_task(task_id)
        return list(
            self.session.scalars(
                select(TaskStatusEvent)
                .where(
                    TaskStatusEvent.task_id == task.id,
                    TaskStatusEvent.version_id == plan.id,
                )
                .order_by(TaskStatusEvent.occurred_at, TaskStatusEvent.id)
            )
        )

    def transition(
        self,
        task_id: UUID,
        payload: TaskStatusTransitionRequest,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TaskStatusMutationView:
        event_key = f"status:{self.owner_id}:{idempotency_key}"
        request_hash = canonical_hash({"task_id": task_id, **payload.model_dump(mode="json")})
        duplicate = self.session.scalar(
            select(TaskStatusEvent).where(TaskStatusEvent.event_key == event_key)
        )
        if duplicate is not None:
            if duplicate.task_id != task_id or duplicate.request_hash != request_hash:
                raise ExecutionConflictError(
                    "Idempotency key was already used with another status request."
                )
            return self._status_result(duplicate, [])

        task, plan, project, projection = self._owned_active_task(task_id, lock=True)
        if projection.row_version != expected_version:
            raise ExecutionConflictError(
                f"Task execution conflict: expected {expected_version}, "
                f"current {projection.row_version}."
            )
        from_status = projection.status
        if payload.to_status not in LEGAL_TRANSITIONS[from_status]:
            raise ExecutionConflictError(
                f"Illegal task transition: {from_status} -> {payload.to_status}."
            )
        tasks = self._tasks(plan.id)
        projections = self._projections(plan.id)
        readiness = self._readiness(plan.id, tasks, projections)
        if (
            payload.to_status in {"ready", "in_progress"}
            and not readiness[task.id].prerequisites_satisfied
        ):
            refs = self._task_refs(
                tasks,
                readiness[task.id].incomplete_predecessor_ids,
            )
            raise ExecutionConflictError(
                "Task prerequisites are incomplete: " + ", ".join(refs) + "."
            )

        now = utc_now()
        projection.status = payload.to_status
        projection.status_changed_at = now
        projection.blocked_reason = (
            payload.reason.strip()
            if payload.to_status == "blocked" and payload.reason is not None
            else None
        )
        if payload.to_status == "completed":
            projection.progress_fraction = Decimal(1)
        event = TaskStatusEvent(
            project_id=project.id,
            version_id=plan.id,
            task_id=task.id,
            actor_id=self.owner_id,
            actor_type="user",
            from_status=from_status,
            to_status=payload.to_status,
            reason=payload.reason or _default_transition_reason(payload.to_status),
            progress_fraction=projection.progress_fraction,
            correlation_id=self.request_id,
            event_key=event_key,
            request_hash=request_hash,
            occurred_at=now,
        )
        self.session.add(event)
        if payload.to_status == "completed":
            self._append_system_progress(
                task,
                plan,
                project,
                projection,
                event_key=f"{event_key}:progress",
                note="Completion set progress to 100%.",
            )
        self.session.flush()
        readiness_events = self._propagate_readiness(
            plan,
            project,
            tasks,
            event_key,
        )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=project.id,
            action="TaskStatusChanged",
            entity_type="Task",
            entity_id=task.id,
            request_id=self.request_id,
            before_ref={
                "stable_key": task.stable_key,
                "status": from_status,
                "row_version": expected_version,
            },
            after_ref={
                "stable_key": task.stable_key,
                "status": payload.to_status,
                "progress_fraction": str(projection.progress_fraction),
            },
        )
        run, job = self._enqueue_monitoring(project, plan)
        self._commit()
        self._monitor_inline(run.id, job.id, project.id)
        return self._status_result(event, readiness_events)

    def update_progress(
        self,
        task_id: UUID,
        payload: TaskProgressUpdateRequest,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TaskProgressMutationView:
        event_key = f"progress:{self.owner_id}:{idempotency_key}"
        request_hash = canonical_hash({"task_id": task_id, **payload.model_dump(mode="json")})
        duplicate = self.session.scalar(
            select(ProgressUpdate).where(ProgressUpdate.event_key == event_key)
        )
        if duplicate is not None:
            if duplicate.task_id != task_id or duplicate.request_hash != request_hash:
                raise ExecutionConflictError(
                    "Idempotency key was already used with another progress request."
                )
            return self._progress_result(duplicate)

        task, plan, project, projection = self._owned_active_task(task_id, lock=True)
        if projection.row_version != expected_version:
            raise ExecutionConflictError(
                f"Task execution conflict: expected {expected_version}, "
                f"current {projection.row_version}."
            )
        if projection.status not in {"in_progress", "blocked"}:
            raise ExecutionConflictError(
                "Progress can be recorded only for in-progress or blocked tasks."
            )
        if payload.fraction < projection.progress_fraction:
            raise ExecutionConflictError("Progress cannot move backwards.")
        if payload.fraction >= 1:
            raise ExecutionConflictError(
                "Use the completed status transition to record 100% progress."
            )
        if payload.actual_effort_hours < projection.actual_effort_hours:
            raise ExecutionConflictError("Actual effort cannot move backwards.")

        projection.progress_fraction = payload.fraction
        projection.actual_effort_hours = payload.actual_effort_hours
        update = ProgressUpdate(
            project_id=project.id,
            version_id=plan.id,
            task_id=task.id,
            actor_id=self.owner_id,
            fraction=payload.fraction,
            actual_effort_hours=payload.actual_effort_hours,
            note=payload.note,
            source="user",
            correlation_id=self.request_id,
            event_key=event_key,
            request_hash=request_hash,
        )
        self.session.add(update)
        self.session.flush()
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=project.id,
            action="TaskProgressUpdated",
            entity_type="Task",
            entity_id=task.id,
            request_id=self.request_id,
            after_ref={
                "stable_key": task.stable_key,
                "fraction": str(payload.fraction),
                "actual_effort_hours": str(payload.actual_effort_hours),
            },
        )
        run, job = self._enqueue_monitoring(project, plan)
        self._commit()
        self._monitor_inline(run.id, job.id, project.id)
        return self._progress_result(update)

    def _status_result(
        self,
        event: TaskStatusEvent,
        readiness_events: list[TaskStatusEvent],
    ) -> TaskStatusMutationView:
        task, plan, project, projection = self._owned_active_task(event.task_id)
        tasks = self._tasks(plan.id)
        projections = self._projections(plan.id)
        readiness = self._readiness(plan.id, tasks, projections)
        milestones = self._milestones(plan.id)
        snapshot = MonitoringService(self.session, self.owner_id).ensure_current(project.id)
        self.session.commit()
        return TaskStatusMutationView(
            task=self._task_view(
                task,
                projection,
                readiness[task.id],
                milestones[task.milestone_id],
                tasks,
            ),
            event=TaskStatusEventView.model_validate(event),
            readiness_changes=[
                TaskStatusEventView.model_validate(item) for item in readiness_events
            ],
            progress=progress_view(snapshot),
            health=health_view(snapshot),
        )

    def _progress_result(self, update: ProgressUpdate) -> TaskProgressMutationView:
        task, plan, project, projection = self._owned_active_task(update.task_id)
        tasks = self._tasks(plan.id)
        projections = self._projections(plan.id)
        readiness = self._readiness(plan.id, tasks, projections)
        milestones = self._milestones(plan.id)
        snapshot = MonitoringService(self.session, self.owner_id).ensure_current(project.id)
        self.session.commit()
        return TaskProgressMutationView(
            task=self._task_view(
                task,
                projection,
                readiness[task.id],
                milestones[task.milestone_id],
                tasks,
            ),
            update=update,
            progress=progress_view(snapshot),
            health=health_view(snapshot),
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
            raise ExecutionResourceNotFoundError
        plan = self.session.scalar(
            select(PlanVersion).where(
                PlanVersion.project_id == project.id,
                PlanVersion.state == "active",
            )
        )
        if plan is None:
            raise ExecutionResourceNotFoundError
        return project, plan

    def _owned_active_task(
        self,
        task_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[Task, PlanVersion, Project, TaskExecutionProjection]:
        query = (
            select(Task, PlanVersion, Project)
            .join(PlanVersion, PlanVersion.id == Task.version_id)
            .join(
                Project,
                (Project.id == PlanVersion.project_id)
                & (Project.owner_id == self.owner_id)
                & (Project.status == "active"),
            )
            .where(Task.id == task_id, PlanVersion.state == "active")
        )
        if lock:
            query = query.with_for_update()
        row = self.session.execute(query).one_or_none()
        if row is None:
            raise ExecutionResourceNotFoundError
        task, plan, project = row
        self._ensure_initialized(plan)
        projection_query = select(TaskExecutionProjection).where(
            TaskExecutionProjection.task_id == task.id,
            TaskExecutionProjection.version_id == plan.id,
        )
        if lock:
            projection_query = projection_query.with_for_update()
        projection = self.session.scalar(projection_query)
        if projection is None:
            raise ExecutionResourceNotFoundError
        return task, plan, project, projection

    def _ensure_initialized(self, plan: PlanVersion) -> None:
        count = len(
            list(
                self.session.scalars(
                    select(TaskExecutionProjection.id).where(
                        TaskExecutionProjection.version_id == plan.id
                    )
                )
            )
        )
        task_count = len(
            list(self.session.scalars(select(Task.id).where(Task.version_id == plan.id)))
        )
        if count == task_count:
            return
        if count:
            raise ExecutionConflictError("Active plan has incomplete execution projections.")
        initialize_active_plan(
            self.session,
            plan,
            owner_id=self.owner_id,
            request_id=self.request_id,
        )

    def _tasks(self, version_id: UUID) -> list[Task]:
        return list(
            self.session.scalars(
                select(Task)
                .where(Task.version_id == version_id)
                .order_by(Task.priority_score.desc(), Task.stable_key)
            )
        )

    def _milestones(self, version_id: UUID) -> dict[UUID, Milestone]:
        return {
            item.id: item
            for item in self.session.scalars(
                select(Milestone).where(Milestone.version_id == version_id)
            )
        }

    def _projections(self, version_id: UUID) -> dict[UUID, TaskExecutionProjection]:
        return {
            item.task_id: item
            for item in self.session.scalars(
                select(TaskExecutionProjection).where(
                    TaskExecutionProjection.version_id == version_id
                )
            )
        }

    def _readiness(
        self,
        version_id: UUID,
        tasks: list[Task],
        projections: dict[UUID, TaskExecutionProjection],
    ) -> dict[UUID, ReadinessProjection]:
        dependencies = list(
            self.session.scalars(
                select(TaskDependency).where(TaskDependency.version_id == version_id)
            )
        )
        return project_readiness(
            tuple(
                GraphTask(
                    id=task.id,
                    stable_key=task.stable_key,
                    version_id=version_id,
                    status=cast(TaskStatus, projections[task.id].status),
                )
                for task in tasks
            ),
            tuple(
                DependencyEdge(
                    predecessor_id=item.predecessor_id,
                    successor_id=item.successor_id,
                    version_id=version_id,
                )
                for item in dependencies
            ),
            version_id,
        )

    def _propagate_readiness(
        self,
        plan: PlanVersion,
        project: Project,
        tasks: list[Task],
        cause_key: str,
    ) -> list[TaskStatusEvent]:
        projections = self._projections(plan.id)
        readiness = self._readiness(plan.id, tasks, projections)
        now = utc_now()
        events: list[TaskStatusEvent] = []
        for task in tasks:
            projection = projections[task.id]
            projected = readiness[task.id].projected_status
            if projected == projection.status:
                continue
            from_status = projection.status
            projection.status = projected
            projection.status_changed_at = now
            event = TaskStatusEvent(
                project_id=project.id,
                version_id=plan.id,
                task_id=task.id,
                actor_id=None,
                actor_type="system",
                from_status=from_status,
                to_status=projected,
                reason="Readiness recalculated from active finish-to-start dependencies.",
                progress_fraction=projection.progress_fraction,
                correlation_id=self.request_id,
                event_key=f"{cause_key}:readiness:{task.id}:{projected}",
                request_hash=canonical_hash(
                    {
                        "cause": cause_key,
                        "task_id": task.id,
                        "from_status": from_status,
                        "to_status": projected,
                    }
                ),
                occurred_at=now,
            )
            self.session.add(event)
            self.audit.append(
                owner_id=self.owner_id,
                actor_id=None,
                actor_type="system",
                project_id=project.id,
                action="TaskReadinessChanged",
                entity_type="Task",
                entity_id=task.id,
                request_id=self.request_id,
                before_ref={"status": from_status},
                after_ref={"status": projected},
            )
            events.append(event)
        self.session.flush()
        return events

    def _append_system_progress(
        self,
        task: Task,
        plan: PlanVersion,
        project: Project,
        projection: TaskExecutionProjection,
        *,
        event_key: str,
        note: str,
    ) -> None:
        self.session.add(
            ProgressUpdate(
                project_id=project.id,
                version_id=plan.id,
                task_id=task.id,
                actor_id=None,
                fraction=projection.progress_fraction,
                actual_effort_hours=projection.actual_effort_hours,
                note=note,
                source="system",
                correlation_id=self.request_id,
                event_key=event_key,
                request_hash=canonical_hash(
                    {
                        "task_id": task.id,
                        "fraction": projection.progress_fraction,
                        "note": note,
                    }
                ),
            )
        )

    def _enqueue_monitoring(
        self,
        project: Project,
        plan: PlanVersion,
    ) -> tuple[AgentRun, AgentJob]:
        state_hash = MonitoringService(self.session, self.owner_id).current_state_hash(
            project, plan
        )
        idempotency_key = f"monitor:{plan.id}:{state_hash.removeprefix('sha256:')[:40]}"
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.initiator_id == self.owner_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if run is None:
            run = AgentRun(
                project_id=project.id,
                initiator_id=self.owner_id,
                workflow="monitoring",
                status="queued",
                idempotency_key=idempotency_key,
                input_hash=state_hash,
                token_budget=1,
                tokens_used=0,
                current_step="monitor.recalculate",
                state_snapshot={
                    "schema_version": "1.0",
                    "workflow": "monitoring",
                    "status": "queued",
                    "active_plan_version_id": str(plan.id),
                    "state_hash": state_hash,
                    "completed_steps": [],
                    "failed_steps": [],
                },
                candidate_data={
                    "active_plan_version_id": str(plan.id),
                    "state_hash": state_hash,
                },
            )
            self.session.add(run)
            self.session.flush()
        job = JobQueue(self.session).enqueue(
            run_id=run.id,
            job_type="monitoring",
            idempotency_key=f"job:{idempotency_key}",
            payload_ref={
                "project_id": str(project.id),
                "version_id": str(plan.id),
                "state_hash": state_hash,
            },
        )
        return run, job

    def _monitor_inline(self, run_id: UUID, job_id: UUID, project_id: UUID) -> None:
        try:
            run = self.session.get(AgentRun, run_id)
            job = self.session.get(AgentJob, job_id)
            if run is None or job is None or run.status == "completed":
                return
            snapshot = MonitoringService(self.session, self.owner_id).ensure_current(project_id)
            run.status = "completed"
            run.started_at = run.started_at or utc_now()
            run.completed_at = utc_now()
            run.current_step = "monitor.persist"
            run.outcome = {
                "snapshot_id": str(snapshot.id),
                "state_hash": snapshot.state_hash,
                "health_label": snapshot.health_label,
            }
            run.state_snapshot = {
                **run.state_snapshot,
                "status": "completed",
                "current_step": "monitor.persist",
                "completed_steps": [
                    "monitor.readiness",
                    "monitor.progress",
                    "monitor.detect",
                    "monitor.reschedule",
                    "monitor.health",
                    "monitor.persist",
                ],
                "updated_at": utc_now().isoformat(),
            }
            if not self.session.scalar(
                select(AgentRunStep.id).where(
                    AgentRunStep.run_id == run.id,
                    AgentRunStep.name == "monitor.persist",
                    AgentRunStep.status == "completed",
                )
            ):
                self.session.add(
                    AgentRunStep(
                        run_id=run.id,
                        name="monitor.persist",
                        mode="deterministic",
                        purpose=(
                            "Recalculate readiness, progress, schedule, detections, "
                            "and evidence-rich health for one exact active-state hash."
                        ),
                        attempt=1,
                        status="completed",
                        input_hash=run.input_hash,
                        idempotency_key=f"{run.id}:monitor.persist:1",
                        input_refs=[
                            {
                                "entity_type": "PlanVersion",
                                "entity_id": str(snapshot.version_id),
                                "content_hash": snapshot.state_hash,
                            }
                        ],
                        output_refs=[
                            {
                                "entity_type": "MonitoringSnapshot",
                                "entity_id": str(snapshot.id),
                                "content_hash": snapshot.state_hash,
                            }
                        ],
                        validation=[],
                        usage={"input_tokens": 0, "output_tokens": 0, "cost_usd": "0"},
                        completed_at=utc_now(),
                        duration_ms=0,
                    )
                )
            if job.status == "queued":
                job.status = "completed"
            self.session.commit()
        except Exception:
            self.session.rollback()

    def _task_view(
        self,
        task: Task,
        projection: TaskExecutionProjection,
        readiness: ReadinessProjection,
        milestone: Milestone,
        tasks: list[Task],
    ) -> TaskExecutionView:
        return TaskExecutionView(
            id=projection.id,
            task_id=task.id,
            project_id=projection.project_id,
            version_id=projection.version_id,
            milestone_id=task.milestone_id,
            milestone_key=milestone.stable_key,
            milestone_name=milestone.name,
            parent_id=task.parent_id,
            stable_key=task.stable_key,
            title=task.title,
            deliverable=task.deliverable,
            priority_score=task.priority_score,
            priority_label=task.priority_label,
            planned_start=task.planned_start,
            planned_finish=task.planned_finish,
            effort_likely_hours=task.effort_likely_hours,
            workstreams=task.workstreams,
            status=cast(Any, projection.status),
            progress_fraction=projection.progress_fraction,
            actual_effort_hours=projection.actual_effort_hours,
            blocked_reason=projection.blocked_reason,
            prerequisites_satisfied=readiness.prerequisites_satisfied,
            ready_to_start=readiness.ready_to_start,
            incomplete_predecessor_refs=self._task_refs(
                tasks,
                readiness.incomplete_predecessor_ids,
            ),
            row_version=projection.row_version,
            status_changed_at=projection.status_changed_at,
        )

    @staticmethod
    def _task_refs(tasks: list[Task], task_ids: tuple[UUID, ...]) -> list[str]:
        keys = {item.id: item.stable_key for item in tasks}
        return [keys.get(item, str(item)) for item in task_ids]

    def _commit(self) -> None:
        try:
            self.session.commit()
        except (IntegrityError, StaleDataError) as error:
            self.session.rollback()
            raise ExecutionConflictError(
                "Task execution changed concurrently; load the latest state."
            ) from error


def progress_view(snapshot: MonitoringSnapshot) -> ProjectProgressView:
    data = snapshot.progress_json
    return ProjectProgressView(
        project_id=snapshot.project_id,
        version_id=snapshot.version_id,
        state_hash=snapshot.state_hash,
        as_of=snapshot.as_of,
        calculated_at=snapshot.calculated_at,
        calculation_version=str(data["calculation_version"]),
        project=data["project"],
        milestones=data["milestones"],
        tasks=[TaskProgressView.model_validate(item) for item in data["tasks"]],
        warning_codes=list(data["warning_codes"]),
        insufficient_data=bool(data["insufficient_data"]),
    )


def health_view(snapshot: MonitoringSnapshot) -> ProjectHealthView:
    health = snapshot.health_json
    schedule = snapshot.schedule_json
    return ProjectHealthView(
        project_id=snapshot.project_id,
        version_id=snapshot.version_id,
        state_hash=snapshot.state_hash,
        as_of=snapshot.as_of,
        calculated_at=snapshot.calculated_at,
        label=snapshot.health_label,
        rule_codes=list(health["rule_codes"]),
        evidence=list(health["evidence"]),
        detections=list(snapshot.detections_json),
        forecast_finish=schedule["forecast_finish"],
        project_finish=schedule["project_finish"],
        deadline=schedule["deadline"],
        deadline_feasible=schedule["deadline_feasible"],
        blocking_path=list(schedule["blocking_path"]),
        schedule_warnings=list(schedule["warnings"]),
        calculation_versions=snapshot.calculation_versions,
    )


def _default_transition_reason(status: str) -> str:
    return {
        "ready": "Task prerequisites are complete.",
        "in_progress": "Owner started task execution.",
        "completed": "Owner completed the task.",
    }.get(status, f"Task moved to {status}.")
