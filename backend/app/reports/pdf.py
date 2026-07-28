"""Hash-bound factual report HTML and bounded Chromium rendering."""

from __future__ import annotations

import hashlib
import json
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
    evidence_rows = "".join(
        (
            "<tr>"
            f'<th scope="row"><code>{_text(reference)}</code></th>'
            f"<td>{_text(fact.entity_type)}</td>"
            f"<td>{_label(fact.fact_key)}</td>"
            f"<td>{_value(fact.value)}</td>"
            "</tr>"
        )
        for reference, fact in sorted(data.evidence.items())
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
  tr {{ break-inside: avoid; }}
  th, td {{ border: 1px solid #c8d0e2; padding: 6px 7px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f7fb; font-weight: 700; }}
  code {{ font-family: "Courier New", monospace; overflow-wrap: anywhere; }}
  ul {{ margin: 6px 0 12px; padding-left: 20px; }}
  .citation {{ color: #4f5d78; display: block; font-size: 8.5pt; }}
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
<section>
  <h2>Factual metrics</h2>
  <table>
    <caption>Persisted deterministic report metrics</caption>
    <tbody>{metric_rows}</tbody>
  </table>
</section>
<section>
  <h2>Evidence index</h2>
  <table>
    <caption>References supporting the factual report</caption>
    <thead><tr><th>Reference</th><th>Entity</th><th>Fact</th><th>Value</th></tr></thead>
    <tbody>{evidence_rows}</tbody>
  </table>
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


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _label(value: str) -> str:
    return _text(value.replace("_", " ").strip().capitalize())


def _value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return _text(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return _text(value)
