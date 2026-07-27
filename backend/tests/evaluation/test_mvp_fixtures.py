import json
from pathlib import Path

from app.evaluation.runner import evaluate_fixture

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
