"""Fail-closed validation ladder for all model-authored candidates."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.schemas.outputs import RecommendationDraftBatch, TaskDraftBatch, WeeklyReportNarrative

RepairFunction = Callable[[dict[str, Any], list[dict[str, Any]]], Awaitable[dict[str, Any]]]
DeterministicCheck = Callable[[BaseModel], Iterable["ValidationIssue"]]
TEMP_ID_PATTERN = re.compile(r"^(MOD|MS|TASK|DEP|RISK|Q|REC)-[0-9]{3,5}$")
FACT_TOKEN_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d+(?:\.\d+)?%?\b")


class ValidationStage(StrEnum):
    SCHEMA = "schema"
    IDENTIFIERS = "identifiers"
    BUSINESS = "business"
    PERMISSION = "permission"
    DETERMINISTIC = "deterministic"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    stage: ValidationStage
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage.value,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidationContext:
    allowed_refs: frozenset[str] = frozenset()
    protected_refs: frozenset[str] = frozenset()
    excluded_refs: frozenset[str] = frozenset()
    allowed_fact_tokens: frozenset[str] = frozenset()
    project_start: date | None = None
    deterministic_checks: tuple[DeterministicCheck, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult[ValidatedT: BaseModel]:
    candidate: ValidatedT | None
    issues: tuple[ValidationIssue, ...] = ()
    repaired: bool = False

    @property
    def is_valid(self) -> bool:
        return self.candidate is not None and not self.issues


async def validate_with_repair[ValidatedT: BaseModel](
    raw_candidate: dict[str, Any],
    output_type: type[ValidatedT],
    context: ValidationContext,
    *,
    repair: RepairFunction | None = None,
) -> ValidationResult[ValidatedT]:
    """Run the ladder and, at most once, request a schema/business repair."""
    initial = validate_candidate(raw_candidate, output_type, context)
    if initial.is_valid or repair is None:
        return initial
    repaired_raw = await repair(raw_candidate, [issue.as_dict() for issue in initial.issues])
    repaired = validate_candidate(repaired_raw, output_type, context)
    return ValidationResult(
        candidate=repaired.candidate,
        issues=repaired.issues,
        repaired=True,
    )


def validate_candidate[ValidatedT: BaseModel](
    raw_candidate: dict[str, Any],
    output_type: type[ValidatedT],
    context: ValidationContext,
) -> ValidationResult[ValidatedT]:
    try:
        candidate = output_type.model_validate(raw_candidate)
    except ValidationError as error:
        schema_issues = tuple(
            ValidationIssue(
                stage=ValidationStage.SCHEMA,
                code=f"pydantic.{item['type']}",
                path=_format_path(item["loc"]),
                message=str(item["msg"]),
            )
            for item in error.errors(include_url=False, include_input=False)
        )
        return ValidationResult(candidate=None, issues=schema_issues)

    issues = [
        *_validate_identifiers(candidate, context),
        *_validate_business_rules(candidate, context),
        *_validate_permissions(candidate, context),
    ]
    if not issues:
        for check in context.deterministic_checks:
            issues.extend(check(candidate))
    if issues:
        return ValidationResult(candidate=None, issues=tuple(issues))
    return ValidationResult(candidate=candidate)


def _format_path(parts: tuple[int | str, ...]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, BaseModel):
        yield from _walk(value.model_dump(mode="python"), path)
    elif isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            yield item_path, key, item
            yield from _walk(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def _validate_identifiers(
    candidate: BaseModel, context: ValidationContext
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    temp_ids: list[tuple[str, str]] = []
    references: list[tuple[str, str]] = []
    for path, key, value in _walk(candidate):
        if key == "temp_id" and isinstance(value, str):
            temp_ids.append((path, value))
        elif (key.endswith("_ref") or key.endswith("_refs")) and value is not None:
            values = value if isinstance(value, list) else [value]
            references.extend((path, item) for item in values if isinstance(item, str))

    seen: set[str] = set()
    for path, temp_id in temp_ids:
        if not TEMP_ID_PATTERN.fullmatch(temp_id):
            issues.append(
                ValidationIssue(
                    ValidationStage.IDENTIFIERS,
                    "identifier.invalid_temp_id",
                    path,
                    f"Temporary identifier {temp_id!r} is invalid.",
                )
            )
        elif temp_id in seen:
            issues.append(
                ValidationIssue(
                    ValidationStage.IDENTIFIERS,
                    "identifier.duplicate_temp_id",
                    path,
                    f"Temporary identifier {temp_id!r} is duplicated.",
                )
            )
        seen.add(temp_id)

    allowed = context.allowed_refs | seen
    for path, reference in references:
        if reference not in allowed:
            issues.append(
                ValidationIssue(
                    ValidationStage.IDENTIFIERS,
                    "identifier.unknown_reference",
                    path,
                    f"Reference {reference!r} was not supplied or generated in this candidate.",
                )
            )
    return issues


def _validate_business_rules(
    candidate: BaseModel, context: ValidationContext
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(candidate, TaskDraftBatch):
        parents = {item.parent_ref for item in candidate.items if item.parent_ref is not None}
        for index, task in enumerate(candidate.items):
            if task.temp_id not in parents and not 4 <= task.effort_likely_hours <= 24:
                issues.append(
                    ValidationIssue(
                        ValidationStage.BUSINESS,
                        "business.leaf_task_size",
                        f"$.items[{index}].effort_likely_hours",
                        "Leaf task likely effort must be between 4 and 24 hours.",
                    )
                )
    if context.project_start is not None:
        dumped = candidate.model_dump(mode="python")
        for path, key, value in _walk(dumped):
            if key == "target_date" and isinstance(value, date) and value < context.project_start:
                issues.append(
                    ValidationIssue(
                        ValidationStage.BUSINESS,
                        "business.target_before_project_start",
                        path,
                        "Milestone target date cannot precede project start.",
                    )
                )
    if isinstance(candidate, (RecommendationDraftBatch, WeeklyReportNarrative)):
        for path, key, value in _walk(candidate):
            if key not in {"temp_id", "evidence_refs"} and isinstance(value, str):
                for token in FACT_TOKEN_PATTERN.findall(value):
                    if token not in context.allowed_fact_tokens:
                        issues.append(
                            ValidationIssue(
                                ValidationStage.BUSINESS,
                                "business.unsupported_fact_token",
                                path,
                                f"Numeric/date fact {token!r} is absent from supplied evidence.",
                            )
                        )
    return issues


def _validate_permissions(
    candidate: BaseModel, context: ValidationContext
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for path, key, value in _walk(candidate):
        values = value if isinstance(value, list) else [value]
        string_values = {item for item in values if isinstance(item, str)}
        if key == "temp_id" and string_values & context.protected_refs:
            issues.append(
                ValidationIssue(
                    ValidationStage.PERMISSION,
                    "permission.protected_item",
                    path,
                    "A locked or user-edited item cannot be regenerated.",
                )
            )
        if (key.endswith("_ref") or key.endswith("_refs")) and (
            string_values & context.excluded_refs
        ):
            issues.append(
                ValidationIssue(
                    ValidationStage.PERMISSION,
                    "permission.excluded_scope",
                    path,
                    "The candidate references excluded scope.",
                )
            )
    return issues
