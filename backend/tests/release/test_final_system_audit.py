import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENT_PATTERN = re.compile(r"\b(?:FR|NFR)-\d{3}\b")
AUDIT_ROW_PATTERN = re.compile(r"(?m)^\| ((?:FR|NFR)-\d{3}) \| (Pass) \| (.+) \|$")


def _text(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def test_final_audit_has_one_pass_row_for_every_numbered_requirement() -> None:
    plan_requirements = set(REQUIREMENT_PATTERN.findall(_text("IMPLEMENTATION PLAN.MD")))
    audit_rows = AUDIT_ROW_PATTERN.findall(_text("docs/release/final-system-audit.md"))
    audited_requirements = [requirement for requirement, _, _ in audit_rows]

    assert len(plan_requirements) == 48
    assert len(audited_requirements) == 48
    assert len(set(audited_requirements)) == 48
    assert set(audited_requirements) == plan_requirements


def test_final_audit_records_every_delivery_verification_layer() -> None:
    audit = _text("docs/release/final-system-audit.md")
    for required in (
        "271 passed, 1 PostgreSQL-only test skipped",
        "272 passed against a fresh PostgreSQL 18 database",
        "90.64% aggregate branch coverage",
        "read p95 284.928 ms",
        "write p95 548.636 ms",
        "10 Playwright scenarios",
        "valid 122,572-byte PDF",
        "Gitleaks scanned 23 commits",
        "Encrypted recovery drill",
        "Unresolved delivery blockers | 0 | 0",
        "No unresolved delivery blocker was found",
    ):
        assert required in audit
