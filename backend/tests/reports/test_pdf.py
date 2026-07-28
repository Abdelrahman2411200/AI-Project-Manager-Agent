from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.models.insight import Report
from app.reports import pdf as pdf_module
from app.reports.pdf import (
    ChromiumPdfRenderer,
    PdfRenderError,
    _renderer_environment,
    build_report_html,
)


def _report() -> Report:
    return Report(
        data_json={
            "schema_version": "1.0",
            "project_id": "00000000-0000-4000-8000-000000000001",
            "project_name": "Campus <script>alert(1)</script>",
            "version_id": "00000000-0000-4000-8000-000000000002",
            "version_number": 4,
            "report_type": "weekly",
            "period_start": "2026-07-20",
            "period_end": "2026-07-26",
            "state_hash": f"sha256:{'1' * 64}",
            "event_cursor": None,
            "evidence": {
                "METRIC-PROGRESS": {
                    "entity_type": "metric",
                    "entity_ref": "PROJECT",
                    "fact_key": "weighted_progress",
                    "value": "18%",
                }
            },
            "metrics": {"weighted_progress_display": "18%"},
            "completed_refs": [],
            "blocker_refs": [],
            "risk_refs": [],
            "next_action_refs": [],
            "health_label": "At risk",
            "health_rule_codes": ["BLOCKED_CRITICAL_TASK"],
            "calculation_versions": {"health": "health-v1"},
        },
        narrative_json={
            "title": "Weekly <img src=x onerror=alert(1)>",
            "period_summary": "Stored facts only.",
            "blockers": [
                {
                    "text": "TASK-014 is blocked.",
                    "evidence_refs": ["METRIC-PROGRESS"],
                }
            ],
        },
        markdown="# ignored",
        content_hash=f"sha256:{'2' * 64}",
        period_start=date(2026, 7, 20),
        period_end=date(2026, 7, 26),
        report_type="weekly",
    )


def test_pdf_html_escapes_project_content_and_contains_hash_bound_facts() -> None:
    html = build_report_html(_report())

    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "METRIC-PROGRESS" in html
    assert "18%" in html
    assert f"sha256:{'2' * 64}" in html
    assert "http://" not in html
    assert "https://" not in html


def test_chromium_renderer_produces_a_real_bounded_pdf_with_network_blocked() -> None:
    renderer = ChromiumPdfRenderer(
        Settings(
            pdf_render_timeout_seconds=30,
            pdf_max_bytes=5_000_000,
            pdf_max_concurrency=1,
        )
    )
    content = renderer.render(
        "<!doctype html><title>Phase 12</title>"
        "<h1>Persisted report</h1>"
        '<img src="https://example.invalid/network-must-be-blocked.png">'
    )

    assert content.startswith(b"%PDF-")
    assert 1_000 < len(content) < 5_000_000


def test_renderer_rejects_oversized_child_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = ChromiumPdfRenderer(
        Settings(
            pdf_render_timeout_seconds=30,
            pdf_max_bytes=65_536,
            pdf_max_concurrency=1,
        )
    )

    def oversized_output(command: list[str], **_: object) -> subprocess.CompletedProcess:
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_bytes(b"%PDF-" + b"x" * 65_532)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pdf_module.subprocess, "run", oversized_output)
    with pytest.raises(PdfRenderError) as captured:
        renderer.render("<h1>Oversized output</h1>")
    assert captured.value.code == "PDF_TOO_LARGE"


def test_renderer_maps_child_timeout_to_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = ChromiumPdfRenderer(
        Settings(
            pdf_render_timeout_seconds=5,
            pdf_max_bytes=65_536,
            pdf_max_concurrency=1,
        )
    )

    def timeout(command: list[str], **_: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(command, timeout=5)

    monkeypatch.setattr(pdf_module.subprocess, "run", timeout)
    with pytest.raises(PdfRenderError) as captured:
        renderer.render("<h1>Timeout</h1>")
    assert captured.value.code == "PDF_TIMEOUT"


def test_renderer_rejects_work_when_capacity_is_saturated() -> None:
    renderer = ChromiumPdfRenderer(
        Settings(
            pdf_render_timeout_seconds=5,
            pdf_max_bytes=65_536,
            pdf_max_concurrency=1,
        )
    )
    assert renderer._slots.acquire(blocking=False)
    try:
        with pytest.raises(PdfRenderError) as captured:
            renderer.render("<h1>Busy</h1>")
        assert captured.value.code == "PDF_BUSY"
    finally:
        renderer._slots.release()


def test_renderer_environment_excludes_application_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-provider-key")
    monkeypatch.setenv("SESSION_HASH_SECRET", "secret-session-key")

    environment = _renderer_environment()

    assert "DATABASE_URL" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "SESSION_HASH_SECRET" not in environment
    assert environment["PYTHONIOENCODING"] == "utf-8"
