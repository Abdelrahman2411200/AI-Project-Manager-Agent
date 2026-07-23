"""Canonical persisted plan snapshots, hashes, and deterministic version diffs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
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


def plan_content_snapshot(session: Session, plan: PlanVersion) -> dict[str, Any]:
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
        session.scalars(
            select(TaskDependency)
            .where(TaskDependency.version_id == plan.id)
            .order_by(TaskDependency.predecessor_id, TaskDependency.successor_id)
        )
    )
    risks = list(
        session.scalars(select(Risk).where(Risk.version_id == plan.id).order_by(Risk.stable_key))
    )
    milestone_keys = {item.id: item.stable_key for item in milestones}
    task_keys = {item.id: item.stable_key for item in tasks}
    return {
        "metadata": {
            "reason": plan.reason,
            "based_on_id": str(plan.based_on_id) if plan.based_on_id else None,
        },
        "analysis": (
            {
                "summary": analysis.summary,
                "project_type": analysis.project_type,
                "intended_users": analysis.intended_users,
                "objectives": analysis.objectives,
                "success_criteria": analysis.success_criteria,
                "modules": analysis.modules,
                "workstreams": analysis.workstreams,
                "assumptions": analysis.assumptions,
                "constraints": analysis.constraints,
                "complexity": analysis.complexity,
                "mvp_boundary": analysis.mvp_boundary,
                "excluded_scope": analysis.excluded_scope,
            }
            if analysis is not None
            else None
        ),
        "milestones": [
            {
                "stable_key": item.stable_key,
                "module_refs": item.module_refs,
                "name": item.name,
                "description": item.description,
                "objective": item.objective,
                "deliverable": item.deliverable,
                "sequence": item.sequence,
                "target_date": item.target_date,
                "planned_effort_hours": item.planned_effort_hours,
                "acceptance_criteria": item.acceptance_criteria,
                "planned_start": item.planned_start,
                "planned_finish": item.planned_finish,
                "status": item.status,
                "source": item.source,
                "protected": item.protected,
                "locked": item.locked,
            }
            for item in milestones
        ],
        "tasks": [
            {
                "stable_key": item.stable_key,
                "milestone_ref": milestone_keys.get(item.milestone_id),
                "parent_ref": task_keys.get(item.parent_id) if item.parent_id else None,
                "title": item.title,
                "description": item.description,
                "deliverable": item.deliverable,
                "acceptance_criteria": item.acceptance_criteria,
                "definition_of_done": item.definition_of_done,
                "effort_min_hours": item.effort_min_hours,
                "effort_likely_hours": item.effort_likely_hours,
                "effort_max_hours": item.effort_max_hours,
                "complexity": item.complexity,
                "workstreams": item.workstreams,
                "skill_tags": item.skill_tags,
                "source": item.source,
                "requirement_refs": item.requirement_refs,
                "assumption_refs": item.assumption_refs,
                "locked": item.locked,
                "protected": item.protected,
                "priority_score": item.priority_score,
                "priority_label": item.priority_label,
                "priority_breakdown": item.priority_breakdown,
                "planned_start": item.planned_start,
                "planned_finish": item.planned_finish,
                "status": item.status,
            }
            for item in tasks
        ],
        "dependencies": [
            {
                "predecessor_ref": task_keys.get(item.predecessor_id),
                "successor_ref": task_keys.get(item.successor_id),
                "dependency_type": item.dependency_type,
                "reason": item.reason,
                "evidence_refs": item.evidence_refs,
                "confidence_label": item.confidence_label,
                "source": item.source,
                "protected": item.protected,
            }
            for item in dependencies
        ],
        "risks": [
            {
                "stable_key": item.stable_key,
                "category": item.category,
                "description": item.description,
                "probability": item.probability,
                "impact": item.impact,
                "severity": item.severity,
                "trigger": item.trigger,
                "mitigation": item.mitigation,
                "contingency": item.contingency,
                "related_refs": item.related_refs,
                "source_fact_refs": item.source_fact_refs,
                "status": item.status,
            }
            for item in risks
        ],
    }


def persisted_content_hash(session: Session, plan: PlanVersion) -> str:
    return canonical_hash(plan_content_snapshot(session, plan))


def compare_plan_content(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if before["metadata"] != after["metadata"] or before["analysis"] != after["analysis"]:
        changes.append(
            {
                "category": "content_changed",
                "entity_type": "plan",
                "stable_key": "PLAN",
                "before": {
                    "metadata": before["metadata"],
                    "analysis": before["analysis"],
                },
                "after": {
                    "metadata": after["metadata"],
                    "analysis": after["analysis"],
                },
            }
        )
    for entity_type, key_fields in (
        ("milestone", ("stable_key",)),
        ("task", ("stable_key",)),
        ("dependency", ("predecessor_ref", "successor_ref")),
        ("risk", ("stable_key",)),
    ):
        collection = f"{entity_type}s"
        if entity_type == "dependency":
            collection = "dependencies"
        before_items = {_item_key(item, key_fields): item for item in before[collection]}
        after_items = {_item_key(item, key_fields): item for item in after[collection]}
        for key in sorted(before_items.keys() - after_items.keys()):
            changes.append(_change("removed", entity_type, key, before_items[key], None))
        for key in sorted(after_items.keys() - before_items.keys()):
            changes.append(_change("added", entity_type, key, None, after_items[key]))
        for key in sorted(before_items.keys() & after_items.keys()):
            old = before_items[key]
            new = after_items[key]
            if old == new:
                continue
            category = _change_category(entity_type, old, new)
            changes.append(_change(category, entity_type, key, old, new))
    return changes


def _item_key(item: dict[str, Any], fields: tuple[str, ...]) -> str:
    return "->".join(str(item.get(field)) for field in fields)


def _change(
    category: str,
    entity_type: str,
    stable_key: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "category": category,
        "entity_type": entity_type,
        "stable_key": stable_key,
        "before": before,
        "after": after,
    }


def _change_category(
    entity_type: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> str:
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    if entity_type == "dependency":
        return "dependency_changed"
    if changed & {"effort_min_hours", "effort_likely_hours", "effort_max_hours"}:
        return "estimate_changed"
    if changed & {"target_date", "planned_start", "planned_finish"}:
        return "date_changed"
    if changed & {"locked", "protected", "source"}:
        return "lock_source_changed"
    return "content_changed"


def task_reference_map(session: Session, version_id: UUID) -> dict[UUID, str]:
    return {
        task_id: stable_key
        for task_id, stable_key in session.execute(
            select(Task.id, Task.stable_key).where(Task.version_id == version_id)
        ).tuples()
    }
