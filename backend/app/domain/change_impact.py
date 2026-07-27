"""Stable-key diff summaries and affected-successor discovery."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from app.services.plan_content import compare_plan_content

CALCULATION_VERSION = "change-impact-v1"


def summarize_comparison(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    changes = compare_plan_content(before, after)
    categories = Counter(change["category"] for change in changes)
    changed_keys = {
        change["stable_key"] for change in changes if change["entity_type"] in {"task", "milestone"}
    }
    downstream = _task_downstream(after)
    affected = set(changed_keys)
    for key in tuple(changed_keys):
        affected.update(downstream.get(key, set()))
    before_finish = _last_finish(before)
    after_finish = _last_finish(after)
    return {
        "changes": changes,
        "summary": dict(sorted(categories.items())),
        "affected_stable_keys": sorted(affected),
        "schedule_delta_days": (
            None
            if before_finish is None or after_finish is None
            else (after_finish - before_finish).days
        ),
        "risk_delta": len(after["risks"]) - len(before["risks"]),
        "scope_delta": (
            len(after["tasks"])
            + len(after["milestones"])
            - len(before["tasks"])
            - len(before["milestones"])
        ),
        "calculation_version": CALCULATION_VERSION,
    }


def _task_downstream(snapshot: dict[str, Any]) -> dict[str, set[str]]:
    successors: dict[str, set[str]] = {task["stable_key"]: set() for task in snapshot["tasks"]}
    for edge in snapshot["dependencies"]:
        predecessor = edge["predecessor_ref"]
        successor = edge["successor_ref"]
        if predecessor in successors and successor in successors:
            successors[predecessor].add(successor)
    result: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def visit(key: str) -> set[str]:
        if key in result:
            return result[key]
        if key in visiting:
            return set()
        visiting.add(key)
        reachable = set(successors[key])
        for successor in successors[key]:
            reachable.update(visit(successor))
        visiting.remove(key)
        result[key] = reachable
        return reachable

    for key in successors:
        visit(key)
    return result


def _last_finish(snapshot: dict[str, Any]) -> date | None:
    values = [
        value
        for item in [*snapshot["tasks"], *snapshot["milestones"]]
        if (value := item.get("planned_finish") or item.get("target_date")) is not None
    ]
    return max(values, default=None)
