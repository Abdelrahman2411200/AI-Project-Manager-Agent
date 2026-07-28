import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.cli.demo_reset import ALLOWED_ENVIRONMENTS
from app.core.config import Settings
from app.demo.seed import DEMO_FIXTURE_NAMES

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATTERN = re.compile(r"(?m)^\| ((?:ARCH|DB|BE|AI|ALG|FE|TEST|SEC|OBS|DEVOPS|DOC)-\d{3}) \|")
EXPECTED_COUNTS = {
    "ARCH": 6,
    "DB": 8,
    "BE": 12,
    "AI": 10,
    "ALG": 8,
    "FE": 10,
    "TEST": 8,
    "SEC": 3,
    "OBS": 2,
    "DEVOPS": 3,
    "DOC": 2,
}
SOURCE_SPEC_SHA256 = "03e80036926b25cc16d6b7b5891a859047ad493cc4b983455142033682166e27"


def _text(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def test_original_source_spec_is_unchanged() -> None:
    content = (REPOSITORY_ROOT / "IMPLEMENTATION%20PLAN.MD").read_bytes()
    assert hashlib.sha256(content).hexdigest() == SOURCE_SPEC_SHA256


def test_plan_and_release_review_account_for_exactly_72_backlog_items() -> None:
    plan_ids = BACKLOG_PATTERN.findall(_text("IMPLEMENTATION PLAN.MD"))
    assert len(plan_ids) == 72
    assert len(set(plan_ids)) == 72
    assert Counter(item.split("-", 1)[0] for item in plan_ids) == EXPECTED_COUNTS

    review = _text("docs/release-review.md")
    reviewed_ids = re.findall(
        r"\b(?:ARCH|DB|BE|AI|ALG|FE|TEST|SEC|OBS|DEVOPS|DOC)-\d{3}\b",
        review,
    )
    assert set(reviewed_ids) == set(plan_ids)
    assert "no unresolved Must" in review
    assert "**72**" in review


def test_demo_document_contains_exact_23_ordered_steps_and_evidence() -> None:
    demo = _text("docs/demo.md")
    steps = [int(value) for value in re.findall(r"(?m)^(\d+)\. \*\*", demo)]
    assert steps == list(range(1, 24))
    for required in (
        "TASK-011 → TASK-014",
        "BLOCKED_CRITICAL_TASK",
        "METRIC-PROGRESS",
        "Markdown",
        "PDF",
        "browser reload",
        "Evidence checklist",
        "Retained draft",
        "Scenario",
        "Regeneration",
    ):
        assert required in demo
    for fixture in DEMO_FIXTURE_NAMES:
        assert fixture in demo


def test_exact_eight_fixture_files_have_synthetic_complete_contracts() -> None:
    root = REPOSITORY_ROOT / "backend" / "tests" / "fixtures" / "demo"
    files = sorted(root.glob("*.json"))
    assert [path.stem for path in files] == sorted(DEMO_FIXTURE_NAMES)
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["slug"] == path.stem
        assert payload["requirements"]
        assert payload["exclusions"]
        assert payload["clarifications"]
        assert payload["modules"]
        assert payload["risk"]
        assert payload["warning"]
        assert "@example.com" not in repr(payload).casefold()


def test_release_versions_and_required_artifacts_are_consistent() -> None:
    assert Settings().app_version == "0.13.0"
    assert 'version = "0.13.0"' in _text("backend/pyproject.toml")
    frontend = json.loads(_text("frontend/package.json"))
    lock = json.loads(_text("frontend/package-lock.json"))
    assert frontend["version"] == "0.13.0"
    assert lock["version"] == "0.13.0"
    assert lock["packages"][""]["version"] == "0.13.0"
    for path in (
        ".env.production.example",
        ".env.demo.example",
        "compose.production.yaml",
        "compose.demo.yaml",
        "docs/deploy.md",
        "docs/demo.md",
        "docs/operations/operator-developer-guide.md",
        "docs/release/final-system-audit.md",
        "docs/release-review.md",
        "docs/release/university-checklist.md",
        "infra/release/verify-demo.sh",
        ".github/workflows/release.yml",
    ):
        assert (REPOSITORY_ROOT / path).is_file(), path


def test_release_blockers_and_destructive_guards_are_explicit() -> None:
    client = _text("frontend/src/api/client.ts")
    nginx = _text("frontend/nginx.conf")
    reset = _text("backend/app/cli/demo_reset.py")
    production = _text("compose.production.yaml")
    assert '"/api/v1"' in client
    assert "location /api/" in nginx
    assert "proxy_pass http://api:8000" in nginx
    assert "location = /index.html" in nginx
    assert "expires -1" in nginx
    assert "location /assets/" in nginx
    assert "try_files $uri =404" in nginx
    assert "RESET-DEMO-DATA" in reset
    assert {"development", "demo", "test"} == ALLOWED_ENVIRONMENTS
    assert "production" not in ALLOWED_ENVIRONMENTS
    assert "staging" not in ALLOWED_ENVIRONMENTS
    assert 'COOKIE_SECURE: "true"' in production
    assert "127.0.0.1" in production
    assert "no-new-privileges:true" in production
    demo = _text("compose.demo.yaml")
    assert "USER_DAILY_RUN_LIMIT: ${USER_DAILY_RUN_LIMIT:-100}" in demo
    assert "USER_DAILY_TOKEN_BUDGET: ${USER_DAILY_TOKEN_BUDGET:-2000000}" in demo
    verifier = _text("infra/release/verify-demo.sh")
    assert "Cache-Control:.*no-cache" in verifier
    assert "release-verifier-missing-chunk.js" in verifier


def test_release_documents_prove_version_isolation_and_advanced_fixture_evidence() -> None:
    demo = _text("docs/demo.md")
    checklist = _text("docs/release/university-checklist.md")
    review = _text("docs/release-review.md")
    assert "one active plan and one retained draft" in demo
    assert "pending selective-regeneration proposal" in demo
    assert "sixteen plan content hashes verify" in checklist
    assert "immutable active-plan scenario" in review
