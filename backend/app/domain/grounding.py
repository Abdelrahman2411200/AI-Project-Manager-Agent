"""Pure claim-to-evidence validation for recommendations and report narratives."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from app.ai.schemas.outputs import RecommendationDraft, WeeklyReportNarrative
from app.schemas.insight import EvidenceFact

FACT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"(?:TASK|MS|DEP|EVENT|METRIC|FORECAST|DETECTION|RISK)-[A-Z0-9_-]+"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d+(?:\.\d+)?%"
    r"|\d+(?:\.\d+)?"
    r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
UNSAFE_TEXT = re.compile(r"<\s*(?:script|iframe|object|embed|style)\b|javascript:", re.IGNORECASE)


def factual_tokens(value: Any) -> set[str]:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    return {item.upper() for item in FACT_TOKEN.findall(serialized)}


def validate_recommendation_draft(
    draft: RecommendationDraft,
    evidence: dict[str, EvidenceFact],
    *,
    expected_detection_code: str,
) -> list[str]:
    errors: list[str] = []
    if draft.detection_code != expected_detection_code:
        errors.append("Detection code does not match the deterministic candidate.")
    missing = sorted(set(draft.evidence_refs) - set(evidence))
    if missing:
        errors.append("Unknown evidence references: " + ", ".join(missing))
        return errors
    allowed = _allowed_tokens(draft.evidence_refs, evidence)
    text_fields = (
        draft.why_it_matters,
        draft.suggested_action,
        draft.expected_impact,
        draft.risk,
        draft.verification_step,
        *draft.alternatives,
    )
    errors.extend(_unsupported_tokens(text_fields, allowed))
    if any(UNSAFE_TEXT.search(value) for value in text_fields):
        errors.append("Recommendation text contains unsafe markup or a URL scheme.")
    return errors


def validate_weekly_narrative(
    narrative: WeeklyReportNarrative,
    evidence: dict[str, EvidenceFact],
) -> list[str]:
    errors: list[str] = []
    uncited_text = (narrative.title, narrative.period_summary, *narrative.caveats)
    errors.extend(_unsupported_tokens(uncited_text, set()))
    if any(UNSAFE_TEXT.search(value) for value in uncited_text):
        errors.append("Uncited report text contains unsafe markup or a URL scheme.")
    statements = (
        *narrative.completed_items,
        narrative.progress_statement,
        *narrative.blockers,
        *narrative.risks,
        *narrative.next_actions,
        *narrative.decisions_needed,
    )
    for index, statement in enumerate(statements):
        missing = sorted(set(statement.evidence_refs) - set(evidence))
        if missing:
            errors.append(f"Statement {index} cites unknown evidence: " + ", ".join(missing))
            continue
        errors.extend(
            f"Statement {index}: {error}"
            for error in _unsupported_tokens(
                (statement.text,),
                _allowed_tokens(statement.evidence_refs, evidence),
            )
        )
        if UNSAFE_TEXT.search(statement.text):
            errors.append(f"Statement {index} contains unsafe markup or a URL scheme.")
    return errors


def _allowed_tokens(
    references: Iterable[str],
    evidence: dict[str, EvidenceFact],
) -> set[str]:
    result: set[str] = set()
    for reference in references:
        result.update(factual_tokens(reference))
        fact = evidence.get(reference)
        if fact is not None:
            result.update(factual_tokens(fact.model_dump(mode="json")))
    return result


def _unsupported_tokens(texts: Iterable[str], allowed: set[str]) -> list[str]:
    unsupported: set[str] = set()
    for value in texts:
        unsupported.update(factual_tokens(value) - allowed)
    return ["Unsupported factual tokens: " + ", ".join(sorted(unsupported))] if unsupported else []
