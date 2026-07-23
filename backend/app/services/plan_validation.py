"""Deterministic validation and recalculation for persisted draft graphs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.plan import Milestone, PlanVersion, ProjectAnalysis, Task, TaskDependency
from app.db.models.project import Project
from app.domain.graph import (
    DependencyEdge,
    GraphTask,
    GraphValidationError,
    TaskStatus,
    validate_graph,
)
from app.domain.priority import PriorityFactors, score_priorities
from app.domain.scheduler import ScheduleTask, schedule_tasks
from app.services.plan_content import persisted_content_hash
from app.services.plan_quality import QualityIssue, QualityReport, project_work_calendar


def validate_persisted_plan(
    session: Session,
    plan: PlanVersion,
    *,
    apply_calculations: bool,
) -> QualityReport:
    project = session.scalar(
        select(Project)
        .where(Project.id == plan.project_id)
        .options(
            selectinload(Project.requirements),
            selectinload(Project.constraints),
            selectinload(Project.calendars),
        )
    )
    if project is None:
        raise LookupError("Plan project not found.")
    analysis = session.scalar(select(ProjectAnalysis).where(ProjectAnalysis.version_id == plan.id))
    milestones = list(
        session.scalars(
            select(Milestone)
            .where(Milestone.version_id == plan.id)
            .order_by(Milestone.sequence, Milestone.stable_key)
        )
    )
    tasks = list(
        session.scalars(select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key))
    )
    dependencies = list(
        session.scalars(select(TaskDependency).where(TaskDependency.version_id == plan.id))
    )
    issues = _structural_issues(project, analysis, milestones, tasks)
    graph = None
    try:
        graph = validate_graph(
            [
                GraphTask(
                    id=item.id,
                    stable_key=item.stable_key,
                    version_id=plan.id,
                    status=cast(TaskStatus, item.status),
                )
                for item in tasks
            ],
            [
                DependencyEdge(
                    predecessor_id=item.predecessor_id,
                    successor_id=item.successor_id,
                    version_id=plan.id,
                )
                for item in dependencies
            ],
            plan.id,
        )
    except GraphValidationError as error:
        issues.append(
            QualityIssue(
                severity="must",
                code=error.code,
                path="$.dependencies",
                message=error.detail,
                references=list(error.references),
            )
        )

    schedule_warnings: list[str] = []
    if graph is not None and tasks:
        try:
            priority_batch = score_priorities(
                {item.id: PriorityFactors(**_priority_inputs(item)) for item in tasks},
                graph,
            )
            priority_by_id = {item.task_id: item for item in priority_batch.results}
            schedule = schedule_tasks(
                [
                    ScheduleTask(
                        id=item.id,
                        stable_key=item.stable_key,
                        version_id=plan.id,
                        likely_effort_hours=item.effort_likely_hours,
                        priority_score=priority_by_id[item.id].score,
                        workstreams=tuple(item.workstreams),
                    )
                    for item in tasks
                ],
                [
                    DependencyEdge(
                        predecessor_id=item.predecessor_id,
                        successor_id=item.successor_id,
                        version_id=plan.id,
                    )
                    for item in dependencies
                ],
                version_id=plan.id,
                project_start=project.start_date
                or (
                    plan.created_at.astimezone(UTC).date()
                    if plan.created_at.tzinfo
                    else plan.created_at.date()
                )
                or datetime.now(UTC).date(),
                calendar=project_work_calendar(project),
                team_size=project.team_size,
                deadline=project.deadline,
            )
            for warning in schedule.warnings:
                severity = "must" if warning.code == "NO_WORKING_CAPACITY" else "should"
                issues.append(
                    QualityIssue(
                        severity=severity,
                        code=warning.code,
                        path="$.schedule",
                        message=warning.detail,
                        references=list(warning.task_keys),
                    )
                )
                schedule_warnings.append(warning.code)
            if apply_calculations and schedule.tasks:
                for task in tasks:
                    priority = priority_by_id[task.id]
                    scheduled = schedule.tasks[task.id]
                    task.priority_score = priority.score
                    task.priority_label = priority.label
                    task.priority_breakdown = {
                        key: str(value) for key, value in asdict(priority.breakdown).items()
                    }
                    task.planned_start = scheduled.start_date
                    task.planned_finish = scheduled.finish_date
                for milestone in milestones:
                    children = [item for item in tasks if item.milestone_id == milestone.id]
                    milestone.planned_effort_hours = sum(
                        (item.effort_likely_hours for item in children),
                        start=Decimal(0),
                    )
                    milestone.planned_start = min(
                        (item.planned_start for item in children if item.planned_start),
                        default=None,
                    )
                    milestone.planned_finish = max(
                        (item.planned_finish for item in children if item.planned_finish),
                        default=None,
                    )
        except ValueError as error:
            issues.append(
                QualityIssue(
                    severity="must",
                    code="DETERMINISTIC_CALCULATION_FAILED",
                    path="$.tasks",
                    message=str(error),
                )
            )

    report = QualityReport(
        passed=not any(item.severity == "must" for item in issues),
        issues=issues,
        warning_codes=list(
            dict.fromkeys(
                [
                    *schedule_warnings,
                    *(item.code for item in issues if item.severity == "should"),
                ]
            )
        ),
        calculation_versions={
            "graph": "graph-v1",
            "priority": "priority-v1",
            "scheduler": "scheduler-v1",
            "quality": "persisted-quality-v1",
        },
    )
    session.flush()
    plan.quality_status = "passed" if report.passed else "failed"
    plan.quality_report = report.model_dump(mode="json")
    plan.content_hash = persisted_content_hash(session, plan)
    session.flush()
    return report


def _structural_issues(
    project: Project,
    analysis: ProjectAnalysis | None,
    milestones: list[Milestone],
    tasks: list[Task],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if analysis is None:
        issues.append(
            QualityIssue(
                severity="must",
                code="MISSING_ANALYSIS",
                path="$.analysis",
                message="A plan must contain a persisted project analysis.",
            )
        )
    if not milestones:
        issues.append(
            QualityIssue(
                severity="must",
                code="MISSING_MILESTONES",
                path="$.milestones",
                message="A plan must contain at least one milestone.",
            )
        )
    if not tasks:
        issues.append(
            QualityIssue(
                severity="must",
                code="MISSING_TASKS",
                path="$.tasks",
                message="A plan must contain actionable tasks.",
            )
        )
    milestone_ids = {item.id for item in milestones}
    empty_milestones = [
        item.stable_key
        for item in milestones
        if not any(task.milestone_id == item.id for task in tasks)
    ]
    if empty_milestones:
        issues.append(
            QualityIssue(
                severity="must",
                code="MILESTONE_WITHOUT_TASK",
                path="$.milestones",
                message="Every milestone must contain at least one task.",
                references=empty_milestones,
            )
        )
    orphan_tasks = [item.stable_key for item in tasks if item.milestone_id not in milestone_ids]
    if orphan_tasks:
        issues.append(
            QualityIssue(
                severity="must",
                code="TASK_WITHOUT_MILESTONE",
                path="$.tasks",
                message="Every task must reference a milestone in the same version.",
                references=orphan_tasks,
            )
        )
    task_ids = {item.id for item in tasks}
    parent_ids = {item.parent_id for item in tasks if item.parent_id is not None}
    leaf_oversized = [
        item.stable_key
        for item in tasks
        if item.id not in parent_ids
        and (item.effort_likely_hours < Decimal(4) or item.effort_likely_hours > Decimal(24))
    ]
    if leaf_oversized:
        issues.append(
            QualityIssue(
                severity="must",
                code="LEAF_TASK_TOO_LARGE",
                path="$.tasks",
                message="Leaf tasks must be between 4 and 24 likely hours.",
                references=leaf_oversized,
            )
        )
    invalid_parents = [
        item.stable_key
        for item in tasks
        if item.parent_id is not None and item.parent_id not in task_ids
    ]
    if invalid_parents:
        issues.append(
            QualityIssue(
                severity="must",
                code="INVALID_PARENT_REFERENCE",
                path="$.tasks",
                message="Task parents must belong to the same version.",
                references=invalid_parents,
            )
        )
    parent_by_id = {item.id: item.parent_id for item in tasks}
    key_by_id = {item.id: item.stable_key for item in tasks}
    parent_cycle_refs: set[str] = set()
    for task in tasks:
        path: set[UUID] = set()
        current: UUID | None = task.id
        while current is not None:
            if current in path:
                parent_cycle_refs.add(key_by_id.get(current, str(current)))
                break
            path.add(current)
            current = parent_by_id.get(current)
    if parent_cycle_refs:
        issues.append(
            QualityIssue(
                severity="must",
                code="TASK_PARENT_CYCLE",
                path="$.tasks",
                message="Task parent relationships must be acyclic.",
                references=sorted(parent_cycle_refs),
            )
        )
    generic_titles = [
        item.stable_key
        for item in tasks
        if " ".join(item.title.casefold().split())
        in {"complete task", "do work", "implement feature", "tbd", "todo"}
    ]
    if generic_titles:
        issues.append(
            QualityIssue(
                severity="must",
                code="TASK_NOT_ACTIONABLE",
                path="$.tasks",
                message="Every task must name a concrete, reviewable action.",
                references=generic_titles,
            )
        )

    ordered_requirements = sorted(
        project.requirements,
        key=lambda item: (item.created_at, str(item.id)),
    )
    required_refs = {
        f"REQ-{index:03d}"
        for index, item in enumerate(ordered_requirements, start=1)
        if item.kind != "excluded" and item.status != "rejected"
    }
    excluded_refs = {
        f"REQ-{index:03d}"
        for index, item in enumerate(ordered_requirements, start=1)
        if item.kind == "excluded" or item.status == "rejected"
    }
    module_refs = {
        ref
        for module in (analysis.modules if analysis is not None else [])
        for ref in module.get("requirement_refs", [])
    }
    task_requirement_refs = {ref for task in tasks for ref in task.requirement_refs}
    missing = sorted(required_refs - module_refs - task_requirement_refs)
    if missing:
        issues.append(
            QualityIssue(
                severity="must",
                code="REQUIREMENT_COVERAGE_GAP",
                path="$.analysis.modules",
                message="Every in-scope requirement must be covered.",
                references=missing,
            )
        )
    excluded_used = sorted((module_refs | task_requirement_refs) & excluded_refs)
    if excluded_used:
        issues.append(
            QualityIssue(
                severity="must",
                code="EXCLUDED_SCOPE_REFERENCED",
                path="$.tasks",
                message="The plan references explicitly excluded scope.",
                references=excluded_used,
            )
        )
    if analysis is not None:
        inside = {" ".join(item.casefold().split()) for item in analysis.mvp_boundary}
        outside = {" ".join(item.casefold().split()) for item in analysis.excluded_scope}
        overlap = sorted(inside & outside)
        if overlap:
            issues.append(
                QualityIssue(
                    severity="must",
                    code="CONTRADICTORY_SCOPE_BOUNDARY",
                    path="$.analysis",
                    message="An item cannot be both in and out of MVP scope.",
                    references=overlap,
                )
            )
    return issues


def _priority_inputs(task: Task) -> dict[str, Decimal]:
    values = task.priority_breakdown
    return {
        key: Decimal(str(values.get(key, 50)))
        for key in (
            "mvp_necessity",
            "deadline_urgency",
            "user_value",
            "risk_reduction",
            "user_preference",
        )
    }
