"""State-hashed deterministic progress, schedule, detection, and health projections."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.hashing import canonical_hash
from app.db.models.execution import MonitoringSnapshot, TaskExecutionProjection
from app.db.models.plan import Milestone, PlanVersion, Task, TaskDependency
from app.db.models.project import Project
from app.domain.graph import (
    DependencyEdge,
    GraphTask,
    GraphValidationError,
    TaskStatus,
    validate_graph,
)
from app.domain.health import (
    CALCULATION_VERSION as HEALTH_VERSION,
)
from app.domain.health import HealthInputs, evaluate_health
from app.domain.monitoring import (
    CALCULATION_VERSION as MONITORING_VERSION,
)
from app.domain.monitoring import (
    MonitoringInputs,
    MonitoringMilestone,
    MonitoringTask,
    detect_conditions,
)
from app.domain.progress import (
    CALCULATION_VERSION as PROGRESS_VERSION,
)
from app.domain.progress import ProgressStatus, ProgressTask, calculate_weighted_progress
from app.domain.scheduler import (
    CALCULATION_VERSION as SCHEDULER_VERSION,
)
from app.domain.scheduler import ScheduleResult, ScheduleTask, schedule_tasks
from app.services.plan_quality import project_work_calendar


class MonitoringResourceNotFoundError(LookupError):
    pass


class MonitoringStaleStateError(RuntimeError):
    pass


class MonitoringService:
    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def active_plan(self, project_id: UUID) -> tuple[Project, PlanVersion]:
        project = self.session.scalar(
            select(Project)
            .options(
                selectinload(Project.calendars),
                selectinload(Project.requirements),
                selectinload(Project.constraints),
            )
            .where(
                Project.id == project_id,
                Project.owner_id == self.owner_id,
                Project.status == "active",
            )
        )
        if project is None:
            raise MonitoringResourceNotFoundError
        plan = self.session.scalar(
            select(PlanVersion).where(
                PlanVersion.project_id == project.id,
                PlanVersion.state == "active",
            )
        )
        if plan is None:
            raise MonitoringResourceNotFoundError
        return project, plan

    def current_state_hash(self, project: Project, plan: PlanVersion) -> str:
        projections = list(
            self.session.scalars(
                select(TaskExecutionProjection)
                .where(TaskExecutionProjection.version_id == plan.id)
                .order_by(TaskExecutionProjection.task_id)
            )
        )
        dependencies = [
            (predecessor_id, successor_id)
            for predecessor_id, successor_id in self.session.execute(
                select(
                    TaskDependency.predecessor_id,
                    TaskDependency.successor_id,
                )
                .where(TaskDependency.version_id == plan.id)
                .order_by(
                    TaskDependency.predecessor_id,
                    TaskDependency.successor_id,
                )
            )
        ]
        return canonical_hash(
            {
                "project_id": project.id,
                "project_row_version": project.row_version,
                "plan_id": plan.id,
                "plan_content_hash": plan.content_hash,
                "projections": [
                    {
                        "task_id": item.task_id,
                        "status": item.status,
                        "progress_fraction": item.progress_fraction,
                        "actual_effort_hours": item.actual_effort_hours,
                        "row_version": item.row_version,
                    }
                    for item in projections
                ],
                "dependencies": dependencies,
                "calendar": [
                    {
                        "weekday_hours": item.weekday_hours,
                        "holidays": item.holidays,
                        "effective_from": item.effective_from,
                        "effective_to": item.effective_to,
                        "parallel_limit": item.parallel_limit,
                        "updated_at": item.updated_at,
                    }
                    for item in project.calendars
                ],
                "deadline": project.deadline,
                "capacity_hours_per_week": project.capacity_hours_per_week,
                "team_size": project.team_size,
                "timezone": project.timezone,
            }
        )

    def ensure_current(self, project_id: UUID) -> MonitoringSnapshot:
        project, plan = self.active_plan(project_id)
        state_hash = self.current_state_hash(project, plan)
        existing = self.session.scalar(
            select(MonitoringSnapshot).where(
                MonitoringSnapshot.version_id == plan.id,
                MonitoringSnapshot.state_hash == state_hash,
            )
        )
        if existing is not None:
            return existing
        return self.recalculate(project, plan, expected_state_hash=state_hash)

    def recalculate(
        self,
        project: Project,
        plan: PlanVersion,
        *,
        expected_state_hash: str | None = None,
    ) -> MonitoringSnapshot:
        state_hash = self.current_state_hash(project, plan)
        if expected_state_hash is not None and state_hash != expected_state_hash:
            raise MonitoringStaleStateError(
                "Active execution changed before monitoring could begin."
            )
        existing = self.session.scalar(
            select(MonitoringSnapshot).where(
                MonitoringSnapshot.version_id == plan.id,
                MonitoringSnapshot.state_hash == state_hash,
            )
        )
        if existing is not None:
            return existing

        tasks = list(
            self.session.scalars(
                select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key)
            )
        )
        milestones = list(
            self.session.scalars(
                select(Milestone)
                .where(Milestone.version_id == plan.id)
                .order_by(Milestone.sequence, Milestone.stable_key)
            )
        )
        dependencies = list(
            self.session.scalars(select(TaskDependency).where(TaskDependency.version_id == plan.id))
        )
        projections = {
            item.task_id: item
            for item in self.session.scalars(
                select(TaskExecutionProjection).where(TaskExecutionProjection.version_id == plan.id)
            )
        }
        if set(projections) != {item.id for item in tasks}:
            raise MonitoringStaleStateError("Execution projections do not match the active plan.")

        as_of = datetime.now(ZoneInfo(project.timezone)).date()
        graph_tasks = tuple(
            GraphTask(
                id=task.id,
                stable_key=task.stable_key,
                version_id=plan.id,
                status=cast(TaskStatus, projections[task.id].status),
            )
            for task in tasks
        )
        graph_edges = tuple(
            DependencyEdge(
                predecessor_id=item.predecessor_id,
                successor_id=item.successor_id,
                version_id=plan.id,
            )
            for item in dependencies
        )
        graph_valid = True
        graph = None
        try:
            graph = validate_graph(graph_tasks, graph_edges, plan.id)
        except GraphValidationError:
            graph_valid = False

        progress = calculate_weighted_progress(
            tuple(
                ProgressTask(
                    id=task.id,
                    milestone_id=task.milestone_id,
                    parent_id=task.parent_id,
                    status=cast(ProgressStatus, projections[task.id].status),
                    likely_effort_hours=task.effort_likely_hours,
                    progress_fraction=projections[task.id].progress_fraction,
                )
                for task in tasks
            )
        )
        calendar = project_work_calendar(project)
        schedule = self._remaining_schedule(
            project,
            plan,
            tasks,
            graph_edges,
            projections,
            as_of,
            calendar,
        )
        parent_ids = {task.parent_id for task in tasks if task.parent_id is not None}
        leaves = [task for task in tasks if task.id not in parent_ids]
        active_leaves = [task for task in leaves if projections[task.id].status != "cancelled"]
        incomplete_leaves = [
            task for task in active_leaves if projections[task.id].status != "completed"
        ]
        remaining_effort = sum(
            (
                task.effort_likely_hours * (Decimal(1) - projections[task.id].progress_fraction)
                for task in incomplete_leaves
            ),
            start=Decimal(0),
        )
        blocked_effort = sum(
            (
                task.effort_likely_hours * (Decimal(1) - projections[task.id].progress_fraction)
                for task in incomplete_leaves
                if projections[task.id].status == "blocked"
            ),
            start=Decimal(0),
        )
        critical_milestone_ids = {
            task.milestone_id for task in tasks if task.priority_label == "Critical"
        }
        overdue_critical = tuple(
            item.stable_key
            for item in milestones
            if item.id in critical_milestone_ids
            and item.target_date is not None
            and item.target_date < as_of
            and any(
                task.milestone_id == item.id
                and projections[task.id].status not in {"completed", "cancelled"}
                for task in leaves
            )
        )
        delayed_milestones = self._delayed_milestones(
            milestones,
            tasks,
            projections,
            schedule,
        )
        blocked_critical = tuple(
            key
            for key in schedule.blocking_path
            if any(
                task.stable_key == key and projections[task.id].status == "blocked"
                for task in tasks
            )
        )
        remaining_duration = self._remaining_duration(calendar, as_of, schedule)
        remaining_buffer = self._remaining_buffer(
            calendar,
            project.deadline,
            schedule,
        )
        capacity_overload = (
            Decimal(schedule.shortfall_working_days) / Decimal(max(1, remaining_duration))
            if schedule.deadline_feasible is False
            else Decimal(0)
        )
        health = evaluate_health(
            HealthInputs(
                as_of=as_of,
                noncancelled_leaf_count=len(active_leaves),
                all_non_cancelled_complete=bool(active_leaves) and not incomplete_leaves,
                has_active_plan=True,
                deadline=project.deadline,
                has_calendar=bool(calendar.weekday_hours),
                graph_valid=graph_valid,
                progress_insufficient=progress.insufficient_data,
                forecast_finish=schedule.forecast_finish,
                overdue_critical_milestone_refs=overdue_critical,
                remaining_buffer_days=remaining_buffer,
                remaining_planned_duration_days=Decimal(remaining_duration),
                blocked_effort_hours=blocked_effort,
                remaining_effort_hours=remaining_effort,
                blocked_critical_path_refs=blocked_critical,
                delayed_milestone_refs=delayed_milestones,
                capacity_overload_ratio=capacity_overload,
            )
        )
        predecessor_map = (
            graph.predecessors if graph is not None else {task.id: frozenset() for task in tasks}
        )
        monitoring_tasks = tuple(
            MonitoringTask(
                id=task.id,
                stable_key=task.stable_key,
                milestone_id=task.milestone_id,
                status=cast(Any, projections[task.id].status),
                planned_finish=task.planned_finish,
                predecessor_ids=tuple(predecessor_map.get(task.id, ())),
            )
            for task in tasks
        )
        monitoring_milestones = tuple(
            MonitoringMilestone(
                id=item.id,
                stable_key=item.stable_key,
                target_date=item.target_date,
                incomplete_task_count=sum(
                    1
                    for task in leaves
                    if task.milestone_id == item.id
                    and projections[task.id].status not in {"completed", "cancelled"}
                ),
            )
            for item in milestones
        )
        detections = detect_conditions(
            MonitoringInputs(
                as_of=as_of,
                tasks=monitoring_tasks,
                milestones=monitoring_milestones,
                graph_valid=graph_valid,
                schedule_feasible=schedule.deadline_feasible,
                planned_finish=max(
                    (
                        task.planned_finish
                        for task in active_leaves
                        if task.planned_finish is not None
                    ),
                    default=None,
                ),
                forecast_finish=schedule.forecast_finish,
                remaining_buffer_days=remaining_buffer,
                remaining_planned_duration_days=Decimal(remaining_duration),
                capacity_overload_ratio=capacity_overload,
            )
        )

        if self.current_state_hash(project, plan) != state_hash:
            raise MonitoringStaleStateError(
                "Active execution changed while monitoring was calculated."
            )
        snapshot = MonitoringSnapshot(
            project_id=project.id,
            version_id=plan.id,
            state_hash=state_hash,
            as_of=as_of,
            progress_json={
                "project": _metric_json(progress.project),
                "milestones": [
                    {
                        "milestone_id": str(item.id),
                        "stable_key": item.stable_key,
                        "name": item.name,
                        **_metric_json(progress.milestones[item.id]),
                    }
                    for item in milestones
                ],
                "tasks": [
                    {
                        "task_id": str(task.id),
                        "stable_key": task.stable_key,
                        "fraction": str(progress.task_fractions.get(task.id, Decimal(0))),
                        "status": projections[task.id].status,
                    }
                    for task in leaves
                    if projections[task.id].status != "cancelled"
                ],
                "warning_codes": list(progress.warning_codes),
                "insufficient_data": progress.insufficient_data,
                "calculation_version": progress.calculation_version,
            },
            schedule_json=_schedule_json(schedule, project.deadline),
            health_label=health.label,
            health_json={
                "label": health.label,
                "rule_codes": list(health.rule_codes),
                "evidence": [
                    {
                        "rule_code": item.rule_code,
                        "values": item.values,
                        "references": list(item.references),
                    }
                    for item in health.evidence
                ],
                "calculation_version": health.calculation_version,
            },
            detections_json=[
                {
                    "code": item.code,
                    "severity": item.severity,
                    "references": list(item.references),
                    "values": item.values,
                    "calculation_version": item.calculation_version,
                }
                for item in detections
            ],
            calculation_versions={
                "progress": PROGRESS_VERSION,
                "scheduler": SCHEDULER_VERSION,
                "health": HEALTH_VERSION,
                "monitoring": MONITORING_VERSION,
            },
        )
        self.session.add(snapshot)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(MonitoringSnapshot).where(
                    MonitoringSnapshot.version_id == plan.id,
                    MonitoringSnapshot.state_hash == state_hash,
                )
            )
            if existing is None:
                raise
            return existing
        return snapshot

    @staticmethod
    def _remaining_schedule(
        project: Project,
        plan: PlanVersion,
        tasks: list[Task],
        edges: tuple[DependencyEdge, ...],
        projections: dict[UUID, TaskExecutionProjection],
        as_of: Any,
        calendar: Any,
    ) -> ScheduleResult:
        parent_ids = {task.parent_id for task in tasks if task.parent_id is not None}
        remaining = [
            task
            for task in tasks
            if task.id not in parent_ids
            and projections[task.id].status not in {"completed", "cancelled"}
        ]
        remaining_ids = {task.id for task in remaining}
        remaining_edges = tuple(
            edge
            for edge in edges
            if edge.predecessor_id in remaining_ids and edge.successor_id in remaining_ids
        )
        schedule_inputs = tuple(
            ScheduleTask(
                id=task.id,
                stable_key=task.stable_key,
                version_id=plan.id,
                likely_effort_hours=max(
                    Decimal("0.01"),
                    task.effort_likely_hours
                    * (Decimal(1) - projections[task.id].progress_fraction),
                ),
                priority_score=task.priority_score,
                workstreams=tuple(task.workstreams),
            )
            for task in remaining
        )
        return schedule_tasks(
            schedule_inputs,
            remaining_edges,
            version_id=plan.id,
            project_start=max(as_of, project.start_date or as_of),
            calendar=calendar,
            team_size=project.team_size,
            deadline=project.deadline,
        )

    @staticmethod
    def _delayed_milestones(
        milestones: list[Milestone],
        tasks: list[Task],
        projections: dict[UUID, TaskExecutionProjection],
        schedule: ScheduleResult,
    ) -> tuple[str, ...]:
        result: list[str] = []
        for milestone in milestones:
            if milestone.target_date is None:
                continue
            task_ids = [
                task.id
                for task in tasks
                if task.milestone_id == milestone.id
                and projections[task.id].status not in {"completed", "cancelled"}
            ]
            finishes = [
                schedule.tasks[task_id].finish_date
                for task_id in task_ids
                if task_id in schedule.tasks
            ]
            if finishes and max(finishes) > milestone.target_date:
                result.append(milestone.stable_key)
        return tuple(result)

    @staticmethod
    def _remaining_duration(calendar: Any, as_of: Any, schedule: ScheduleResult) -> int:
        if schedule.project_finish is None:
            return 0
        from app.domain.calendar import count_working_days

        return max(0, count_working_days(calendar, as_of, schedule.project_finish))

    @staticmethod
    def _remaining_buffer(
        calendar: Any,
        deadline: Any,
        schedule: ScheduleResult,
    ) -> Decimal | None:
        if deadline is None or schedule.project_finish is None:
            return None
        from app.domain.calendar import count_working_days

        return Decimal(
            max(
                0,
                count_working_days(
                    calendar,
                    schedule.project_finish,
                    deadline,
                    include_start=False,
                ),
            )
        )


def _metric_json(metric: Any) -> dict[str, Any]:
    return {
        "fraction": str(metric.fraction) if metric.fraction is not None else None,
        "weighted_completed_hours": str(metric.weighted_completed_hours),
        "estimated_hours": str(metric.estimated_hours),
        "active_leaf_count": metric.active_leaf_count,
        "unestimated_leaf_count": metric.unestimated_leaf_count,
    }


def _schedule_json(schedule: ScheduleResult, deadline: Any) -> dict[str, Any]:
    return {
        "project_finish": (
            schedule.project_finish.isoformat() if schedule.project_finish is not None else None
        ),
        "forecast_finish": (
            schedule.forecast_finish.isoformat() if schedule.forecast_finish is not None else None
        ),
        "deadline": deadline.isoformat() if deadline is not None else None,
        "deadline_feasible": schedule.deadline_feasible,
        "buffer_working_days": schedule.buffer_working_days,
        "shortfall_working_days": schedule.shortfall_working_days,
        "shortfall_hours": str(schedule.shortfall_hours),
        "blocking_path": list(schedule.blocking_path),
        "warnings": [
            {
                "code": item.code,
                "detail": item.detail,
                "task_keys": list(item.task_keys),
            }
            for item in schedule.warnings
        ],
        "tasks": {
            str(task_id): {
                "stable_key": item.stable_key,
                "start_date": item.start_date.isoformat(),
                "finish_date": item.finish_date.isoformat(),
            }
            for task_id, item in schedule.tasks.items()
        },
        "calculation_version": schedule.calculation_version,
    }
