"""Construct Markdown from plain factual fields without rendering model-authored markup."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.ai.schemas.outputs import CitedStatement, WeeklyReportNarrative
from app.schemas.insight import FactualReportData

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RAW_HTML = re.compile(r"<[^>]*>")
FORMULA_PREFIX = re.compile(r"^(\s*)[=+@-]")
UNSAFE_SCHEME = re.compile(r"(?:javascript|data):", re.IGNORECASE)


def plain_text(value: str) -> str:
    normalized = CONTROL_CHARACTERS.sub("", value.replace("\r", " ").replace("\n", " "))
    normalized = RAW_HTML.sub("", normalized).strip()
    normalized = UNSAFE_SCHEME.sub("unsafe:", normalized)
    normalized = FORMULA_PREFIX.sub(r"\1'", normalized)
    for character in ("\\", "`", "*", "_", "{", "}", "[", "]", "<", ">", "#", "|"):
        normalized = normalized.replace(character, f"\\{character}")
    return normalized


def safe_filename(project_name: str, report_type: str, period_end: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.casefold()).strip("-")
    slug = (slug or "project")[:60]
    return f"{slug}-{report_type}-report-{period_end}.md"


def render_markdown(
    data: FactualReportData,
    narrative: WeeklyReportNarrative | None,
) -> str:
    lines = [
        f"# {plain_text(narrative.title if narrative else _fallback_title(data))}",
        "",
        f"**Period:** {data.period_start.isoformat()} through {data.period_end.isoformat()}",
        f"**Active plan version:** {data.version_number}",
        f"**Source state:** `{data.state_hash}`",
        "",
    ]
    if narrative is not None:
        lines.extend(
            [
                "## Summary",
                "",
                plain_text(narrative.period_summary),
                "",
            ]
        )
        _statement_section(lines, "Progress", [narrative.progress_statement])
        _statement_section(lines, "Completed work", narrative.completed_items)
        _statement_section(lines, "Blockers", narrative.blockers)
        _statement_section(lines, "Risks", narrative.risks)
        _statement_section(lines, "Next actions", narrative.next_actions)
        _statement_section(lines, "Decisions needed", narrative.decisions_needed)
        if narrative.caveats:
            lines.extend(["## Caveats", ""])
            lines.extend(f"- {plain_text(item)}" for item in narrative.caveats)
            lines.append("")
    else:
        _render_factual_fallback(lines, data)
    lines.extend(
        [
            "## Evidence index",
            "",
            "| Reference | Fact | Value |",
            "|---|---|---|",
        ]
    )
    for reference, fact in sorted(data.evidence.items()):
        value = plain_text(_display_value(fact.value))
        lines.append(f"| `{plain_text(reference)}` | {plain_text(fact.fact_key)} | {value} |")
    lines.extend(
        [
            "",
            "---",
            "",
            "This report was generated from persisted project state and immutable events. "
            "Narrative text cannot change the cited source facts.",
            "",
        ]
    )
    return "\n".join(lines)


def _statement_section(
    lines: list[str],
    heading: str,
    statements: Iterable[CitedStatement],
) -> None:
    items = list(statements)
    lines.extend([f"## {heading}", ""])
    if not items:
        lines.extend(["No recorded items for this section.", ""])
        return
    for statement in items:
        citations = ", ".join(f"`{plain_text(ref)}`" for ref in statement.evidence_refs)
        lines.append(f"- {plain_text(statement.text)} — Evidence: {citations}")
    lines.append("")


def _render_factual_fallback(lines: list[str], data: FactualReportData) -> None:
    progress = data.metrics["weighted_progress_display"]
    lines.extend(
        [
            "## Factual summary",
            "",
            "AI narrative was unavailable or rejected. The factual report remains complete.",
            "",
            "## Progress",
            "",
            (
                f"- Weighted project progress: {plain_text(str(progress))} "
                "— Evidence: `METRIC-PROGRESS`"
            ),
            f"- Project health: {plain_text(data.health_label)} — Evidence: `HEALTH-CURRENT`",
            "",
        ]
    )
    _reference_section(lines, "Completed work", data.completed_refs)
    _reference_section(lines, "Blockers", data.blocker_refs)
    _reference_section(lines, "Risks", data.risk_refs)
    _reference_section(lines, "Next actions", data.next_action_refs)


def _reference_section(lines: list[str], heading: str, references: list[str]) -> None:
    lines.extend([f"## {heading}", ""])
    if references:
        lines.extend(f"- `{plain_text(reference)}`" for reference in references)
    else:
        lines.append("No recorded items for this section.")
    lines.append("")


def _fallback_title(data: FactualReportData) -> str:
    return f"{data.project_name} {data.report_type} report"


def _display_value(value: object) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{key}={_display_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_display_value(item) for item in value)
    return str(value)
