"""Read and verify the reviewed Phase 12 evaluation baseline."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

from app.core.hashing import canonical_hash
from app.schemas.evaluation import EvaluationDashboardView, EvaluationFixtureView

EXPECTED_FIXTURES = {
    "analytics_dashboard",
    "attendance_system",
    "ecommerce_six_weeks",
    "expense_tracker_mobile",
    "football_scouting_eight_weeks",
    "impossible_deadline",
    "incident_investigator",
    "marketing_site_small",
}
SUMMARY_METRICS = (
    "module_coverage",
    "missing_task_rate",
    "task_size_compliance",
    "dependency_validity",
    "hallucination_rate",
)
EXPECTED_DATASET_HASH = "sha256:037c259966794ee39d1b86aee1f22c6792aaca83e9ab00e2e6d068e36faecdb3"


class EvaluationBaselineError(RuntimeError):
    pass


@lru_cache
def latest_evaluation() -> EvaluationDashboardView:
    resource = files("app.evaluation.baselines").joinpath("university-v1.json")
    raw = cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))
    dataset_hash = canonical_hash(raw)
    if dataset_hash != EXPECTED_DATASET_HASH:
        raise EvaluationBaselineError(
            "The reviewed evaluation baseline does not match its accepted content hash."
        )
    fixtures = [EvaluationFixtureView.model_validate(item) for item in raw.get("fixtures", [])]
    identifiers = {item.fixture_id for item in fixtures}
    if identifiers != EXPECTED_FIXTURES or len(fixtures) != len(EXPECTED_FIXTURES):
        raise EvaluationBaselineError(
            "The reviewed evaluation baseline does not contain the required fixtures."
        )
    if any(set(item.metrics) != {*SUMMARY_METRICS, "schedule_match"} for item in fixtures):
        raise EvaluationBaselineError("The evaluation baseline metric set is incomplete.")
    summary = {
        metric: sum(float(item.metrics[metric]) for item in fixtures) / len(fixtures)
        for metric in SUMMARY_METRICS
    }
    pass_count = sum(item.passed for item in fixtures)
    return EvaluationDashboardView(
        schema_version=raw["schema_version"],
        dataset_version=raw["dataset_version"],
        dataset_hash=dataset_hash,
        fixture_source=raw["fixture_source"],
        fixture_count=len(fixtures),
        pass_count=pass_count,
        release_status="passed" if pass_count == len(fixtures) else "failed",
        thresholds=raw["thresholds"],
        summary=summary,
        fixtures=fixtures,
    )
