"""Hash-bound factual report HTML and bounded Chromium rendering."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
from collections.abc import Mapping
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from app.core.config import Settings
from app.db.models.insight import Report
from app.schemas.insight import FactualReportData


class PdfRenderError(RuntimeError):
    """Safe rendering failure with a stable operator-facing code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PdfRenderer(Protocol):
    def render(self, html: str) -> bytes: ...


class ChromiumPdfRenderer:
    """Run each render in a disposable, timeout-bound child process."""

    def __init__(self, settings: Settings) -> None:
        self.timeout_seconds = settings.pdf_render_timeout_seconds
        self.max_bytes = settings.pdf_max_bytes
        self._slots = threading.BoundedSemaphore(settings.pdf_max_concurrency)

    def render(self, html: str) -> bytes:
        if not self._slots.acquire(blocking=False):
            raise PdfRenderError("PDF_BUSY", "PDF rendering capacity is temporarily exhausted.")
        try:
            return self._render_bounded(html)
        finally:
            self._slots.release()

    def _render_bounded(self, html: str) -> bytes:
        with TemporaryDirectory(prefix="aipm-pdf-") as directory:
            root = Path(directory)
            input_path = root / "report.html"
            output_path = root / "report.pdf"
            input_path.write_text(html, encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "app.reports.pdf_worker",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=False,
                    timeout=self.timeout_seconds,
                    env=_renderer_environment(),
                    creationflags=creation_flags,
                )
            except subprocess.TimeoutExpired as error:
                raise PdfRenderError(
                    "PDF_TIMEOUT",
                    "PDF rendering exceeded its configured time limit.",
                ) from error
            if completed.returncode != 0:
                raise PdfRenderError(
                    "PDF_ENGINE_UNAVAILABLE",
                    "The isolated PDF renderer could not produce the document.",
                )
            if not output_path.is_file():
                raise PdfRenderError("PDF_INVALID_OUTPUT", "The PDF renderer returned no document.")
            content = output_path.read_bytes()
            if not content.startswith(b"%PDF-"):
                raise PdfRenderError("PDF_INVALID_OUTPUT", "The renderer output is not a PDF.")
            if len(content) > self.max_bytes:
                raise PdfRenderError(
                    "PDF_TOO_LARGE",
                    "The rendered PDF exceeds the configured output limit.",
                )
            return content


def _renderer_environment() -> dict[str, str]:
    """Pass browser runtime paths without forwarding application secrets."""

    allowed = {
        "HOME",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "PATH",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def pdf_sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def build_report_html(report: Report) -> str:
    """Build print HTML from escaped stored fields, never interpreted Markdown."""

    data = FactualReportData.model_validate(report.data_json)
    narrative: Mapping[str, Any] = (
        report.narrative_json if isinstance(report.narrative_json, Mapping) else {}
    )
    title = narrative.get("title")
    safe_title = str(title) if isinstance(title, str) else f"{data.project_name} factual report"
    summary = narrative.get("period_summary")
    safe_summary = (
        str(summary)
        if isinstance(summary, str)
        else "This document uses the persisted deterministic report snapshot."
    )
    metric_rows = "".join(
        f'<tr><th scope="row">{_label(key)}</th><td>{_value(value)}</td></tr>'
        for key, value in sorted(data.metrics.items())
    )
    task_schedules = _task_schedule_index(data)
    task_rows = "".join(
        _task_row(reference, fact.fact_key, fact.value, task_schedules.get(reference))
        for reference, fact in sorted(data.evidence.items())
        if fact.entity_type == "task"
    )
    task_section = (
        f"""<section>
  <h2>Task index</h2>
  <p class="section-note">Current task facts cited by this immutable report.</p>
  <table class="task-table">
    <caption>Referenced project tasks</caption>
    <thead><tr><th>Reference</th><th>Task</th><th>Status</th><th>Priority</th><th>Progress</th><th>Schedule</th></tr></thead>
    <tbody>{task_rows}</tbody>
  </table>
</section>"""
        if task_rows
        else ""
    )
    evidence_cards = "".join(
        _evidence_card(reference, fact.entity_type, fact.fact_key, fact.value)
        for reference, fact in sorted(
            data.evidence.items(),
            key=lambda item: (_entity_order(item[1].entity_type), item[0]),
        )
        if fact.entity_type != "task"
    )
    narrative_sections = "".join(
        _narrative_section(narrative, key, heading)
        for key, heading in (
            ("completed_items", "Completed work"),
            ("blockers", "Blockers"),
            ("risks", "Risks"),
            ("next_actions", "Next actions"),
            ("decisions_needed", "Decisions needed"),
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_text(safe_title)}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm 18mm; }}
  * {{ box-sizing: border-box; }}
  body {{ color: #172033; font: 10.5pt/1.5 Arial, sans-serif; margin: 0; }}
  header {{ border-bottom: 3px solid #3157d5; margin-bottom: 20px; padding-bottom: 14px; }}
  h1 {{ font-size: 24pt; line-height: 1.15; margin: 0 0 8px; }}
  h2 {{ break-after: avoid; color: #243a84; font-size: 14pt; margin: 22px 0 8px; }}
  p {{ margin: 0 0 10px; }}
  .meta {{ color: #4f5d78; display: grid; gap: 3px; }}
  .summary {{ background: #eef3ff; border-left: 4px solid #3157d5; padding: 12px; }}
  table {{ border-collapse: collapse; font-size: 9pt; width: 100%; }}
  thead {{ display: table-header-group; }}
  tr {{ break-inside: avoid; }}
  th, td {{ border: 1px solid #c8d0e2; padding: 6px 7px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f7fb; font-weight: 700; }}
  code {{ font-family: "Courier New", monospace; overflow-wrap: anywhere; }}
  ul {{ margin: 6px 0 12px; padding-left: 20px; }}
  .citation {{ color: #4f5d78; display: block; font-size: 8.5pt; }}
  .section-note {{ color: #4f5d78; font-size: 9pt; margin-top: -4px; }}
  .task-table {{ font-size: 7.8pt; table-layout: fixed; }}
  .task-table th:nth-child(1) {{ width: 14%; }}
  .task-table th:nth-child(2) {{ width: 28%; }}
  .task-table th:nth-child(3),
  .task-table th:nth-child(4),
  .task-table th:nth-child(5) {{ width: 11%; }}
  .task-table th:nth-child(6) {{ width: 25%; }}
  .claim-kicker {{
    color: #3157d5; font-size: 8pt; font-weight: 700; letter-spacing: .08em;
    margin-top: 24px; text-transform: uppercase;
  }}
  .claim-kicker + h2 {{ margin-top: 3px; }}
  .evidence-card {{
    border: 1px solid #c8d0e2; border-left: 4px solid #3157d5;
    border-radius: 5px; margin: 0 0 10px; padding: 9px 10px;
    break-inside: avoid;
  }}
  .evidence-card-large {{ break-inside: auto; }}
  .evidence-card-header {{
    align-items: flex-start; display: flex; gap: 10px;
    justify-content: space-between; margin-bottom: 6px;
  }}
  .evidence-card h3 {{ color: #172033; font-size: 10pt; line-height: 1.35; margin: 0; }}
  .entity-label {{
    background: #eef3ff; border-radius: 999px; color: #243a84;
    font-size: 7.5pt; font-weight: 700; padding: 2px 6px; text-transform: capitalize;
  }}
  .field-list {{ margin: 0; }}
  .field-row {{
    border-top: 1px solid #e0e5ef; display: grid; gap: 8px;
    grid-template-columns: 32% minmax(0, 1fr); padding: 4px 0;
  }}
  .field-row dt {{ color: #4f5d78; font-size: 8pt; font-weight: 700; }}
  .field-row dd {{ margin: 0; min-width: 0; overflow-wrap: anywhere; }}
  .nested-table {{ font-size: 7.5pt; margin: 4px 0; table-layout: fixed; }}
  .nested-table th, .nested-table td {{ padding: 4px 5px; overflow-wrap: anywhere; }}
  .empty-value {{ color: #4f5d78; font-style: italic; }}
  .value-list {{ margin: 2px 0; padding-left: 18px; }}
  .compact-values {{ display: flex; flex-wrap: wrap; gap: 3px 10px; list-style: none; padding: 0; }}
  .compact-values li {{ background: #f5f7fb; border-radius: 3px; padding: 1px 4px; }}
  footer {{
    border-top: 1px solid #c8d0e2;
    color: #4f5d78;
    font-size: 8pt;
    margin-top: 24px;
    padding-top: 8px;
  }}
</style>
</head>
<body>
<header>
  <h1>{_text(safe_title)}</h1>
  <div class="meta">
    <span>Project: {_text(data.project_name)}</span>
    <span>
      Period: {_text(data.period_start.isoformat())}
      through {_text(data.period_end.isoformat())}
    </span>
    <span>Active plan version: {_text(data.version_number)}</span>
    <span>Report type: {_text(data.report_type)}</span>
  </div>
</header>
<p class="summary">{_text(safe_summary)}</p>
{narrative_sections}
{task_section}
<section>
  <h2>Factual metrics</h2>
  <table>
    <caption>Persisted deterministic report metrics</caption>
    <tbody>{metric_rows}</tbody>
  </table>
</section>
<section>
  <div class="claim-kicker">Claim verification</div>
  <h2>Evidence index</h2>
  <p class="section-note">
    Each reference identifies a persisted fact used to verify statements in this report.
  </p>
  <div class="evidence-list">{evidence_cards}</div>
</section>
<footer>
  <div>Report content hash: <code>{_text(report.content_hash)}</code></div>
  <div>Source state hash: <code>{_text(data.state_hash)}</code></div>
  <div>
    Generated from persisted project state and immutable events.
    Narrative cannot change source facts.
  </div>
</footer>
</body>
</html>"""


def _narrative_section(
    narrative: Mapping[str, Any],
    key: str,
    heading: str,
) -> str:
    raw = narrative.get(key)
    if not isinstance(raw, list) or not raw:
        return ""
    items: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("text"), str):
            continue
        refs = item.get("evidence_refs")
        citations = ", ".join(str(value) for value in refs) if isinstance(refs, list) else ""
        citation = (
            f'<span class="citation">Evidence: {_text(citations)}</span>' if citations else ""
        )
        items.append(f"<li>{_text(item['text'])}{citation}</li>")
    if not items:
        return ""
    return f"<section><h2>{_text(heading)}</h2><ul>{''.join(items)}</ul></section>"


def _task_schedule_index(data: FactualReportData) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for fact in data.evidence.values():
        if fact.entity_type != "forecast" or not isinstance(fact.value, Mapping):
            continue
        tasks = fact.value.get("tasks")
        if not isinstance(tasks, Mapping):
            continue
        for item in tasks.values():
            if isinstance(item, Mapping) and isinstance(item.get("stable_key"), str):
                result[str(item["stable_key"])] = item
    return result


def _entity_order(entity_type: str) -> int:
    return {
        "period": 0,
        "metric": 1,
        "forecast": 2,
        "milestone": 3,
        "risk": 4,
        "event": 5,
        "dependency": 6,
        "detection": 7,
        "project": 8,
    }.get(entity_type, 99)


def _task_row(
    reference: str,
    fact_key: str,
    value: object,
    forecast_schedule: Mapping[str, object] | None,
) -> str:
    details = value if isinstance(value, Mapping) else {}
    title = details.get("title") or fact_key
    status = details.get("status")
    priority = details.get("priority") or details.get("priority_label")
    progress = details.get("progress") or details.get("progress_display")
    start = (
        details.get("planned_start")
        or details.get("start_date")
        or (forecast_schedule or {}).get("start_date")
    )
    finish = (
        details.get("planned_finish")
        or details.get("finish_date")
        or (forecast_schedule or {}).get("finish_date")
    )
    if start and finish:
        schedule = f"{_text(start)} to {_text(finish)}"
    elif start or finish:
        schedule = _text(start or finish)
    else:
        schedule = '<span class="empty-value">Not scheduled</span>'
    return (
        "<tr>"
        f'<th scope="row"><code>{_text(reference)}</code></th>'
        f"<td>{_text(title)}</td>"
        f"<td>{_scalar_html(status)}</td>"
        f"<td>{_scalar_html(priority)}</td>"
        f"<td>{_scalar_html(progress)}</td>"
        f"<td>{schedule}</td>"
        "</tr>"
    )


def _evidence_card(reference: str, entity_type: str, fact_key: str, value: object) -> str:
    large_class = " evidence-card-large" if _contains_record_collection(value) else ""
    return (
        f'<article class="evidence-card{large_class}">'
        '<div class="evidence-card-header">'
        f"<h3><code>{_text(reference)}</code> - {_label(fact_key)}</h3>"
        f'<span class="entity-label">{_label(entity_type)}</span>'
        "</div>"
        f"{_structured_value(value)}"
        "</article>"
    )


def _contains_record_collection(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return any(
        isinstance(item, Mapping) and _is_simple_record_collection(item) for item in value.values()
    )


def _structured_value(value: object) -> str:
    if isinstance(value, Mapping):
        if not value:
            return '<span class="empty-value">None recorded</span>'
        if _is_simple_record_collection(value):
            return _record_table(value)
        rows = "".join(
            (
                '<div class="field-row">'
                f"<dt>{_label(str(key))}</dt>"
                f"<dd>{_structured_value(item)}</dd>"
                "</div>"
            )
            for key, item in value.items()
        )
        return f'<dl class="field-list">{rows}</dl>'
    if isinstance(value, (list, tuple)):
        if not value:
            return '<span class="empty-value">None recorded</span>'
        items = "".join(f"<li>{_structured_value(item)}</li>" for item in value)
        compact = all(not isinstance(item, (Mapping, list, tuple)) for item in value)
        class_name = "value-list compact-values" if compact else "value-list"
        return f'<ol class="{class_name}">{items}</ol>'
    return _scalar_html(value)


def _is_simple_record_collection(value: Mapping[object, object]) -> bool:
    records = list(value.values())
    if not records or not all(isinstance(item, Mapping) for item in records):
        return False
    record_mappings = [item for item in records if isinstance(item, Mapping)]
    columns = {str(key) for record in record_mappings for key in record}
    return len(columns) <= 6 and all(
        not isinstance(item, (Mapping, list, tuple))
        for record in record_mappings
        for item in record.values()
    )


def _record_table(value: Mapping[object, object]) -> str:
    records = [item for item in value.values() if isinstance(item, Mapping)]
    preferred = ["stable_key", "task_ref", "reference", "title", "start_date", "finish_date"]
    discovered = [str(key) for record in records for key in record]
    columns = [key for key in preferred if key in discovered]
    columns.extend(key for key in dict.fromkeys(discovered) if key not in columns)
    rows = "".join(
        "<tr>"
        + "".join(f"<td>{_scalar_html(record.get(column))}</td>" for column in columns)
        + "</tr>"
        for record in sorted(
            records,
            key=lambda item: str(
                item.get("stable_key") or item.get("task_ref") or item.get("title") or ""
            ),
        )
    )
    headings = "".join(f"<th>{_label(column)}</th>" for column in columns)
    return (
        '<table class="nested-table">'
        f"<thead><tr>{headings}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _scalar_html(value: object) -> str:
    if value is None or value == "":
        return '<span class="empty-value">Not recorded</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return _text(value)


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _label(value: str) -> str:
    return _text(value.replace("_", " ").strip().capitalize())


def _value(value: object) -> str:
    return _structured_value(value)
