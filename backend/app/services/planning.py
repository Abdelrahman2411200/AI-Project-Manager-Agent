"""Atomic conversion of validated temporary references into a complete draft graph."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.hashing import canonical_hash
from app.db.models.plan import (
    Milestone,
    PlanVersion,
    ProjectAnalysis,
    Risk,
    Task,
    TaskDependency,
)
from app.db.models.project import Project
from app.db.models.run import AgentRun
from app.services.audit import AuditRecorder
from app.services.plan_quality import (
    PlanningCalculations,
    PlanningCandidates,
    QualityReport,
)


class DraftPersistenceError(RuntimeError):
    pass


def persist_validated_draft(
    session: Session,
    *,
    owner_id: UUID,
    request_id: str,
    project: Project,
    run: AgentRun,
    candidates: PlanningCandidates,
    report: QualityReport,
    calculations: PlanningCalculations,
) -> PlanVersion:
    if not report.passed:
        raise DraftPersistenceError("A failed quality gate cannot be persisted as a draft.")
    existing = session.scalar(select(PlanVersion).where(PlanVersion.source_run_id == run.id))
    if existing is not None:
        return existing
    locked_project = session.scalar(
        select(Project)
        .where(Project.id == project.id, Project.owner_id == owner_id)
        .with_for_update()
    )
    if locked_project is None:
        raise DraftPersistenceError("Project is unavailable for draft persistence.")
    latest = session.scalar(
        select(PlanVersion)
        .where(PlanVersion.project_id == project.id)
        .order_by(PlanVersion.number.desc())
        .limit(1)
    )
    number = (
        int(
            session.scalar(
                select(func.coalesce(func.max(PlanVersion.number), 0)).where(
                    PlanVersion.project_id == project.id
                )
            )
            or 0
        )
        + 1
    )
    content = {
        "analysis": candidates.analysis.model_dump(mode="json"),
        "modules": candidates.modules.model_dump(mode="json"),
        "milestones": candidates.milestones.model_dump(mode="json"),
        "tasks": candidates.tasks.model_dump(mode="json"),
        "dependencies": candidates.dependencies.model_dump(mode="json"),
        "risks": candidates.risks.model_dump(mode="json"),
        "quality": report.model_dump(mode="json"),
        "calculations": calculations.as_dict(),
    }
    plan = PlanVersion(
        id=uuid4(),
        project_id=project.id,
        number=number,
        state="draft",
        based_on_id=latest.id if latest is not None else None,
        reason="AI-generated validated planning draft",
        content_hash=canonical_hash(content),
        quality_status="passed",
        quality_report=report.model_dump(mode="json"),
        source_run_id=run.id,
    )
    session.add(plan)
    session.flush()
    analysis = candidates.analysis
    session.add(
        ProjectAnalysis(
            version_id=plan.id,
            summary=analysis.summary,
            project_type=analysis.project_type,
            intended_users=analysis.intended_users,
            objectives=[item.model_dump(mode="json") for item in analysis.objectives],
            success_criteria=[item.model_dump(mode="json") for item in analysis.success_criteria],
            modules=[item.model_dump(mode="json") for item in candidates.modules.items],
            workstreams=analysis.workstreams,
            assumptions=[item.model_dump(mode="json") for item in analysis.assumptions],
            constraints=[item.model_dump(mode="json") for item in analysis.constraints],
            complexity=analysis.complexity,
            mvp_boundary=analysis.mvp_boundary,
            excluded_scope=analysis.excluded_scope,
        )
    )
    milestone_ids = {
        item.temp_id: uuid5(project.id, f"{run.id}:{item.temp_id}")
        for item in candidates.milestones.items
    }
    for milestone_item in candidates.milestones.items:
        calculated = calculations.milestone_schedule[milestone_item.temp_id]
        session.add(
            Milestone(
                id=milestone_ids[milestone_item.temp_id],
                version_id=plan.id,
                stable_key=milestone_item.temp_id,
                module_refs=milestone_item.module_refs,
                name=milestone_item.name,
                description=milestone_item.description,
                objective=milestone_item.objective,
                deliverable=milestone_item.deliverable,
                sequence=milestone_item.sequence,
                target_date=milestone_item.target_date,
                planned_effort_hours=Decimal(calculated["planned_effort_hours"]),
                acceptance_criteria=milestone_item.acceptance_criteria,
                planned_start=calculated["planned_start"],
                planned_finish=calculated["planned_finish"],
                status="pending",
            )
        )
    session.flush()
    for task_item in candidates.tasks.items:
        priority = calculations.priorities[task_item.temp_id]
        scheduled = calculations.task_schedule[task_item.temp_id]
        session.add(
            Task(
                id=calculations.task_ids[task_item.temp_id],
                version_id=plan.id,
                milestone_id=milestone_ids[task_item.milestone_ref],
                parent_id=(
                    calculations.task_ids[task_item.parent_ref]
                    if task_item.parent_ref is not None
                    else None
                ),
                stable_key=task_item.temp_id,
                title=task_item.title,
                description=task_item.description,
                deliverable=task_item.deliverable,
                acceptance_criteria=task_item.acceptance_criteria,
                definition_of_done=task_item.definition_of_done,
                effort_min_hours=Decimal(str(task_item.effort_min_hours)),
                effort_likely_hours=Decimal(str(task_item.effort_likely_hours)),
                effort_max_hours=Decimal(str(task_item.effort_max_hours)),
                complexity=task_item.complexity,
                workstreams=task_item.workstreams,
                skill_tags=task_item.skill_tags,
                source=task_item.source,
                requirement_refs=task_item.requirement_refs,
                assumption_refs=task_item.assumption_refs,
                locked=False,
                priority_score=Decimal(priority["score"]),
                priority_label=priority["label"],
                priority_breakdown=priority["breakdown"],
                planned_start=scheduled["planned_start"],
                planned_finish=scheduled["planned_finish"],
                status="pending",
            )
        )
    session.flush()
    for dependency_item in candidates.dependencies.items:
        session.add(
            TaskDependency(
                version_id=plan.id,
                predecessor_id=calculations.task_ids[dependency_item.predecessor_ref],
                successor_id=calculations.task_ids[dependency_item.successor_ref],
                dependency_type=dependency_item.type,
                reason=dependency_item.reason,
                evidence_refs=dependency_item.evidence_refs,
                confidence_label=dependency_item.confidence_label,
            )
        )
    probability_score = {"unlikely": 1, "possible": 2, "likely": 3}
    impact_score = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    for risk_item in candidates.risks.items:
        session.add(
            Risk(
                version_id=plan.id,
                stable_key=risk_item.temp_id,
                category=risk_item.category,
                description=risk_item.description,
                probability=risk_item.probability,
                impact=risk_item.impact,
                severity=probability_score[risk_item.probability] * impact_score[risk_item.impact],
                trigger=risk_item.trigger,
                mitigation=risk_item.mitigation,
                contingency=risk_item.contingency,
                related_refs=risk_item.related_refs,
                source_fact_refs=risk_item.source_fact_refs,
                status="open",
            )
        )
    session.flush()
    AuditRecorder(session).append(
        owner_id=owner_id,
        actor_id=None,
        actor_type="agent",
        project_id=project.id,
        action="PlanDraftGenerated",
        entity_type="PlanVersion",
        entity_id=plan.id,
        request_id=request_id,
        after_ref={
            "number": plan.number,
            "state": plan.state,
            "content_hash": plan.content_hash,
            "source_run_id": str(run.id),
        },
    )
    return plan
