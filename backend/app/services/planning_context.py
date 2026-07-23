"""Minimal, stable-reference project context for planning nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models.plan import PlanningDecision
from app.db.models.project import Project


@dataclass(frozen=True, slots=True)
class PlanningFacts:
    intake: dict[str, Any]
    requirements: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    allowed_refs: frozenset[str]
    excluded_refs: frozenset[str]


def build_planning_facts(
    project: Project,
    decisions: list[PlanningDecision] | tuple[PlanningDecision, ...] = (),
) -> PlanningFacts:
    requirements: list[dict[str, Any]] = []
    excluded: set[str] = set()
    for index, item in enumerate(
        sorted(project.requirements, key=lambda row: (row.created_at, str(row.id))),
        start=1,
    ):
        fact_ref = f"REQ-{index:03d}"
        requirements.append(
            {
                "fact_ref": fact_ref,
                "kind": item.kind,
                "text": item.text,
                "source": item.source,
                "status": item.status,
            }
        )
        if item.kind == "excluded" or item.status == "rejected":
            excluded.add(fact_ref)
    constraints = [
        {
            "fact_ref": f"CONSTRAINT-{index:03d}",
            "type": item.constraint_type,
            "value": item.value_json,
            "source": item.source,
            "confirmed": item.confirmed,
        }
        for index, item in enumerate(
            sorted(project.constraints, key=lambda row: (row.created_at, str(row.id))),
            start=1,
        )
    ]
    decision_items = [
        {
            "fact_ref": item.stable_key,
            "type": item.decision_type,
            "text": item.text,
            "rationale": item.rationale,
            "source_fact_refs": item.source_fact_refs,
        }
        for item in sorted(decisions, key=lambda row: row.stable_key)
    ]
    intake = {
        "name": project.name,
        "goal": project.goal,
        "desired_outcome": project.desired_outcome,
        "start_date": project.start_date,
        "deadline": project.deadline,
        "timezone": project.timezone,
        "capacity_hours_per_week": project.capacity_hours_per_week,
        "team_size": project.team_size,
        "notes": project.notes,
        "row_version": project.row_version,
    }
    refs = {
        *(item["fact_ref"] for item in requirements),
        *(item["fact_ref"] for item in constraints),
        *(item["fact_ref"] for item in decision_items),
    }
    return PlanningFacts(
        intake=intake,
        requirements=requirements,
        constraints=constraints,
        decisions=decision_items,
        allowed_refs=frozenset(refs),
        excluded_refs=frozenset(excluded),
    )
