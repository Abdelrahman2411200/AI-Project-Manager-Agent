"""Deterministic planning calculations and must/should quality gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.ai.schemas.outputs import (
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    RiskDraftBatch,
    TaskDraftBatch,
)
from app.db.models.project import Project
from app.domain.calendar import WorkCalendar as DomainWorkCalendar
from app.domain.graph import DependencyEdge, GraphTask, GraphValidationError, validate_graph
from app.domain.priority import PriorityFactors, score_priorities
from app.domain.scheduler import ScheduleTask, schedule_tasks
from app.services.planning_context import PlanningFacts


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["must", "should"]
    code: str
    path: str
    message: str
    references: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[QualityIssue]
    warning_codes: list[str]
    calculation_versions: dict[str, str]


class PlanningCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: ProjectAnalysisOutput
    modules: ModuleDraftBatch
    milestones: MilestoneDraftBatch
    tasks: TaskDraftBatch
    dependencies: DependencySuggestionBatch
    risks: RiskDraftBatch


@dataclass(frozen=True, slots=True)
class PlanningCalculations:
    candidate_version_id: UUID
    task_ids: dict[str, UUID]
    graph_order: tuple[str, ...]
    priorities: dict[str, dict[str, Any]]
    task_schedule: dict[str, dict[str, Any]]
    milestone_schedule: dict[str, dict[str, Any]]
    schedule_summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _json_safe(
                {
                    "candidate_version_id": str(self.candidate_version_id),
                    "task_ids": {key: str(value) for key, value in self.task_ids.items()},
                    "graph_order": list(self.graph_order),
                    "priorities": self.priorities,
                    "task_schedule": self.task_schedule,
                    "milestone_schedule": self.milestone_schedule,
                    "schedule_summary": self.schedule_summary,
                }
            ),
        )


def calculate_plan(
    *,
    project: Project,
    run_id: UUID,
    facts: PlanningFacts,
    candidates: PlanningCandidates,
    fallback_start: date,
) -> tuple[QualityReport, PlanningCalculations | None]:
    issues = _structural_issues(facts, candidates)
    candidate_version_id = uuid5(project.id, f"{run_id}:candidate-version")
    task_ids = {
        task.temp_id: uuid5(project.id, f"{run_id}:{task.temp_id}")
        for task in candidates.tasks.items
    }
    graph_tasks = [
        GraphTask(
            id=task_ids[item.temp_id],
            stable_key=item.temp_id,
            version_id=candidate_version_id,
        )
        for item in candidates.tasks.items
    ]
    graph_edges = [
        DependencyEdge(
            predecessor_id=task_ids[item.predecessor_ref],
            successor_id=task_ids[item.successor_ref],
            version_id=candidate_version_id,
        )
        for item in candidates.dependencies.items
        if item.predecessor_ref in task_ids and item.successor_ref in task_ids
    ]
    try:
        graph = validate_graph(graph_tasks, graph_edges, candidate_version_id)
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
        return _report(issues), None

    factors = {
        task_ids[item.temp_id]: PriorityFactors(
            mvp_necessity=Decimal(item.mvp_necessity),
            deadline_urgency=Decimal(item.deadline_urgency),
            user_value=Decimal(item.user_value),
            risk_reduction=Decimal(item.risk_reduction),
            user_preference=Decimal(item.user_preference),
        )
        for item in candidates.tasks.items
    }
    priority_batch = score_priorities(factors, graph)
    priority_by_id = {result.task_id: result for result in priority_batch.results}
    priorities = {
        item.temp_id: {
            "score": str(priority_by_id[task_ids[item.temp_id]].score),
            "label": priority_by_id[task_ids[item.temp_id]].label,
            "breakdown": {
                key: str(value)
                for key, value in asdict(priority_by_id[task_ids[item.temp_id]].breakdown).items()
            },
        }
        for item in candidates.tasks.items
    }
    calendar = _calendar(project)
    schedule = schedule_tasks(
        [
            ScheduleTask(
                id=task_ids[item.temp_id],
                stable_key=item.temp_id,
                version_id=candidate_version_id,
                likely_effort_hours=Decimal(str(item.effort_likely_hours)),
                priority_score=priority_by_id[task_ids[item.temp_id]].score,
                workstreams=tuple(item.workstreams),
            )
            for item in candidates.tasks.items
        ],
        graph_edges,
        version_id=candidate_version_id,
        project_start=project.start_date or fallback_start,
        calendar=calendar,
        team_size=project.team_size,
        deadline=project.deadline,
    )
    if not schedule.tasks:
        issues.extend(
            QualityIssue(
                severity="must",
                code=warning.code,
                path="$.schedule",
                message=warning.detail,
                references=list(warning.task_keys),
            )
            for warning in schedule.warnings
            if warning.code == "NO_WORKING_CAPACITY"
        )
        return _report(issues, priority_batch.warning_codes), None
    task_schedule = {
        item.stable_key: {
            "planned_start": item.start_date,
            "planned_finish": item.finish_date,
            "allocations": [
                {"day": allocation.day, "hours": str(allocation.hours)}
                for allocation in item.allocations
            ],
        }
        for item in schedule.tasks.values()
    }
    milestone_schedule: dict[str, dict[str, Any]] = {}
    for milestone in candidates.milestones.items:
        children = [
            task for task in candidates.tasks.items if task.milestone_ref == milestone.temp_id
        ]
        starts = [cast(date, task_schedule[item.temp_id]["planned_start"]) for item in children]
        finishes = [cast(date, task_schedule[item.temp_id]["planned_finish"]) for item in children]
        milestone_schedule[milestone.temp_id] = {
            "planned_start": min(starts) if starts else None,
            "planned_finish": max(finishes) if finishes else None,
            "planned_effort_hours": str(
                sum(
                    (Decimal(str(item.effort_likely_hours)) for item in children),
                    start=Decimal(0),
                )
            ),
        }
    calculations = PlanningCalculations(
        candidate_version_id=candidate_version_id,
        task_ids=task_ids,
        graph_order=tuple(
            next(key for key, value in task_ids.items() if value == task_id)
            for task_id in graph.topological_order
        ),
        priorities=priorities,
        task_schedule=task_schedule,
        milestone_schedule=milestone_schedule,
        schedule_summary={
            "project_finish": schedule.project_finish,
            "forecast_finish": schedule.forecast_finish,
            "deadline_feasible": schedule.deadline_feasible,
            "shortfall_working_days": schedule.shortfall_working_days,
            "blocking_path": list(schedule.blocking_path),
            "warnings": [
                {
                    "code": item.code,
                    "detail": item.detail,
                    "task_keys": list(item.task_keys),
                }
                for item in schedule.warnings
            ],
        },
    )
    return _report(issues, priority_batch.warning_codes), calculations


def _structural_issues(facts: PlanningFacts, candidates: PlanningCandidates) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    required_refs = {
        item["fact_ref"]
        for item in facts.requirements
        if item["fact_ref"] not in facts.excluded_refs
    }
    covered = {
        *(ref for module in candidates.modules.items for ref in module.requirement_refs),
        *(ref for task in candidates.tasks.items for ref in task.requirement_refs),
    }
    missing = sorted(required_refs - covered)
    if missing:
        issues.append(
            QualityIssue(
                severity="must",
                code="REQUIREMENT_COVERAGE_GAP",
                path="$.modules",
                message="Every in-scope requirement must be covered by a module or task.",
                references=missing,
            )
        )
    milestone_modules = {ref for item in candidates.milestones.items for ref in item.module_refs}
    uncovered_modules = sorted(
        item.temp_id for item in candidates.modules.items if item.temp_id not in milestone_modules
    )
    if uncovered_modules:
        issues.append(
            QualityIssue(
                severity="must",
                code="MODULE_WITHOUT_MILESTONE",
                path="$.milestones",
                message="Every module must be represented by a milestone.",
                references=uncovered_modules,
            )
        )
    task_milestones = {item.milestone_ref for item in candidates.tasks.items}
    empty_milestones = sorted(
        item.temp_id for item in candidates.milestones.items if item.temp_id not in task_milestones
    )
    if empty_milestones:
        issues.append(
            QualityIssue(
                severity="must",
                code="MILESTONE_WITHOUT_TASK",
                path="$.tasks",
                message="Every milestone must contain actionable work.",
                references=empty_milestones,
            )
        )
    titles: dict[str, list[str]] = {}
    for task in candidates.tasks.items:
        titles.setdefault(" ".join(task.title.casefold().split()), []).append(task.temp_id)
    duplicate_titles = sorted(
        reference
        for references in titles.values()
        if len(references) > 1
        for reference in references
    )
    if duplicate_titles:
        issues.append(
            QualityIssue(
                severity="must",
                code="DUPLICATE_TASK_TITLE",
                path="$.tasks",
                message="Task titles must be distinct after normalization.",
                references=duplicate_titles,
            )
        )
    generic_task_titles = sorted(
        task.temp_id
        for task in candidates.tasks.items
        if " ".join(task.title.casefold().split())
        in {"complete task", "do work", "implement feature", "tbd", "todo"}
    )
    if generic_task_titles:
        issues.append(
            QualityIssue(
                severity="must",
                code="TASK_NOT_ACTIONABLE",
                path="$.tasks",
                message="Every task must name a concrete, reviewable action.",
                references=generic_task_titles,
            )
        )
    in_scope = {" ".join(item.casefold().split()) for item in candidates.analysis.mvp_boundary}
    out_of_scope = {
        " ".join(item.casefold().split()) for item in candidates.analysis.excluded_scope
    }
    scope_overlap = sorted(in_scope & out_of_scope)
    if scope_overlap:
        issues.append(
            QualityIssue(
                severity="must",
                code="CONTRADICTORY_SCOPE_BOUNDARY",
                path="$.analysis",
                message="An item cannot be both inside and outside the MVP boundary.",
                references=scope_overlap,
            )
        )
    excluded_references = sorted(
        {
            ref
            for module in candidates.modules.items
            for ref in module.requirement_refs
            if ref in facts.excluded_refs
        }
        | {
            ref
            for task in candidates.tasks.items
            for ref in [*task.requirement_refs, *task.assumption_refs]
            if ref in facts.excluded_refs
        }
    )
    if excluded_references:
        issues.append(
            QualityIssue(
                severity="must",
                code="EXCLUDED_SCOPE_REFERENCED",
                path="$.tasks",
                message="The proposed plan references facts explicitly excluded from scope.",
                references=excluded_references,
            )
        )
    ungrounded_assumptions = [
        f"assumption-{index}"
        for index, assumption in enumerate(candidates.analysis.assumptions, start=1)
        if not assumption.source_fact_refs
    ]
    if ungrounded_assumptions:
        issues.append(
            QualityIssue(
                severity="should",
                code="UNGROUNDED_ASSUMPTION",
                path="$.analysis.assumptions",
                message="Every assumption should cite at least one persisted fact.",
                references=ungrounded_assumptions,
            )
        )
    if any(question.required for question in candidates.analysis.open_questions):
        issues.append(
            QualityIssue(
                severity="must",
                code="OPEN_REQUIRED_QUESTION",
                path="$.analysis.open_questions",
                message="Required clarification must be resolved before draft persistence.",
            )
        )
    if not candidates.risks.items:
        issues.append(
            QualityIssue(
                severity="should",
                code="NO_IDENTIFIED_RISKS",
                path="$.risks",
                message="No grounded risks were identified for this plan.",
            )
        )
    return issues


def _calendar(project: Project) -> DomainWorkCalendar:
    weekday_names = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if project.calendars:
        stored = project.calendars[0]
        weekday_hours = {
            weekday_names[key]: Decimal(str(value)) for key, value in stored.weekday_hours.items()
        }
        nominal_weekly = sum(weekday_hours.values(), start=Decimal(0)) * Decimal(project.team_size)
        factor = (
            min(Decimal(1), project.capacity_hours_per_week / nominal_weekly)
            if nominal_weekly > 0
            else Decimal(1)
        )
        return DomainWorkCalendar(
            timezone=project.timezone,
            weekday_hours=weekday_hours,
            holidays=frozenset(date.fromisoformat(value) for value in stored.holidays),
            effective_from=stored.effective_from,
            effective_to=stored.effective_to,
            availability_factor=factor,
            parallel_limit=stored.parallel_limit,
        )
    hours_per_day = project.capacity_hours_per_week / Decimal(project.team_size) / Decimal(5)
    return DomainWorkCalendar(
        timezone=project.timezone,
        weekday_hours={day: hours_per_day for day in range(5)},
        parallel_limit=max(1, project.team_size),
    )


def _report(issues: list[QualityIssue], warning_codes: tuple[str, ...] = ()) -> QualityReport:
    warnings = [item.code for item in issues if item.severity == "should"]
    return QualityReport(
        passed=not any(item.severity == "must" for item in issues),
        issues=issues,
        warning_codes=[*warning_codes, *warnings],
        calculation_versions={
            "graph": "graph-v1",
            "priority": "priority-v1",
            "scheduler": "scheduler-v1",
            "quality": "quality-v1",
        },
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, UUID)):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
