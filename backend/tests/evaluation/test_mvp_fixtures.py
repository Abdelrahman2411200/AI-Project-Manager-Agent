import json
from pathlib import Path

import pytest

from app.evaluation.runner import evaluate_fixture
from app.services import evaluations
from app.services.evaluations import EvaluationBaselineError, latest_evaluation

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "evals" / "mvp_evaluation.jsonl"


def load_fixtures() -> list[dict]:
    return [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_all_eight_specified_evaluation_scenarios_are_versioned_and_unique() -> None:
    fixtures = load_fixtures()
    assert len(fixtures) == 8
    assert len({item["fixture_id"] for item in fixtures}) == 8
    assert sum(item["mvp_release_fixture"] for item in fixtures) >= 5


def test_five_mvp_release_fixtures_and_all_scenarios_pass_hard_thresholds() -> None:
    fixtures = load_fixtures()
    results = [evaluate_fixture(item) for item in fixtures]
    assert all(result.passed for result in results)
    assert (
        sum(
            result.passed
            for result, fixture in zip(results, fixtures, strict=True)
            if fixture["mvp_release_fixture"]
        )
        >= 5
    )


def test_reviewed_dashboard_baseline_matches_the_versioned_fixture_runner() -> None:
    fixtures = load_fixtures()
    calculated = {result.fixture_id: result for result in map(evaluate_fixture, fixtures)}
    baseline = latest_evaluation()

    assert baseline.dataset_version == "university-evaluation-v1"
    assert baseline.fixture_count == baseline.pass_count == 8
    assert baseline.release_status == "passed"
    assert (
        baseline.dataset_hash
        == "sha256:037c259966794ee39d1b86aee1f22c6792aaca83e9ab00e2e6d068e36faecdb3"
    )
    assert {item.fixture_id for item in baseline.fixtures} == set(calculated)
    for item in baseline.fixtures:
        result = calculated[item.fixture_id]
        assert item.passed is result.passed
        assert item.metrics == {
            "module_coverage": result.module_coverage,
            "missing_task_rate": result.missing_task_rate,
            "task_size_compliance": result.task_size_compliance,
            "dependency_validity": result.dependency_validity,
            "hallucination_rate": result.hallucination_rate,
            "schedule_match": result.schedule_match,
        }


def test_reviewed_dashboard_baseline_fails_closed_on_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest_evaluation.cache_clear()
    monkeypatch.setattr(evaluations, "EXPECTED_DATASET_HASH", f"sha256:{'0' * 64}")
    with pytest.raises(EvaluationBaselineError, match="accepted content hash"):
        latest_evaluation()
    latest_evaluation.cache_clear()
