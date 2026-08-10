"""Schema-constrained semantic nodes for the persistent planning workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.prompts.persistence import (
    mark_prompt_used,
    record_provider_usage,
)
from app.ai.prompts.registry import PromptTemplate, get_prompt
from app.ai.provider import (
    ModelUsage,
    StructuredModelError,
    StructuredModelProvider,
    StructuredModelRequest,
    make_safety_identifier,
)
from app.ai.schemas.outputs import (
    ClarificationQuestion,
    ClarificationQuestionBatch,
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    RiskDraftBatch,
    TaskDraft,
    TaskDraftBatch,
)
from app.ai.validation import ValidationContext, validate_candidate
from app.core.config import Settings
from app.db.models.run import AgentRun
from app.services.planning_context import PlanningFacts
from app.workflows.engine import NodeFailure

TASK_REQUIREMENT_BATCH_SIZE = 2
ACCEPTANCE_TASK_BATCH_SIZE = 4
FAST_LOCAL_MODULE_TARGET = 4


@dataclass(frozen=True, slots=True)
class Generated[OutputT: BaseModel]:
    output: OutputT
    usage: ModelUsage
    repaired: bool


class PlanningSemanticNodes:
    def __init__(
        self,
        session: Session,
        provider: StructuredModelProvider,
        settings: Settings,
    ) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings

    @property
    def _fast_local_planning(self) -> bool:
        """Use the bounded local path for CPU-hosted Ollama planning runs."""
        return self.settings.planning_provider == "ollama" and self.settings.ollama_fast_planning

    async def detect_gaps(
        self, run: AgentRun, facts: PlanningFacts
    ) -> Generated[ClarificationQuestionBatch]:
        if self._fast_local_planning and _local_intake_is_complete(facts):
            return Generated(ClarificationQuestionBatch(items=[]), ModelUsage(), repaired=False)
        generated: Generated[ClarificationQuestionBatch] = await self._generate(
            run,
            "clarification.v3",
            {
                "intake": facts.intake,
                "requirements": facts.requirements,
                "constraints": facts.constraints,
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )
        unanswered = [
            item
            for item in generated.output.items
            if not _question_is_answered_by_confirmed_facts(item, facts)
        ]
        if len(unanswered) == len(generated.output.items):
            return generated
        return Generated(
            ClarificationQuestionBatch(items=unanswered),
            generated.usage,
            repaired=True,
        )

    async def analyze(
        self, run: AgentRun, facts: PlanningFacts
    ) -> Generated[ProjectAnalysisOutput]:
        return await self._generate(
            run,
            "analysis.v3",
            {
                "intake": facts.intake,
                "requirements": facts.requirements,
                "constraints": facts.constraints,
                "decisions": facts.decisions,
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )

    async def modules(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        analysis: ProjectAnalysisOutput,
    ) -> Generated[ModuleDraftBatch]:
        required_refs = frozenset(
            item["fact_ref"]
            for item in facts.requirements
            if item["fact_ref"] not in facts.excluded_refs
        )
        generated: Generated[ModuleDraftBatch] = await self._generate(
            run,
            "modules.v3",
            {
                "analysis": analysis.model_dump(mode="json"),
                "requirements": facts.requirements,
                "required_requirement_refs": sorted(required_refs),
                "excluded_refs": sorted(facts.excluded_refs),
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs,
                required_refs=required_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )
        normalized_items: list[dict[str, Any]] = []
        changed = False
        for index, item in enumerate(generated.output.items, start=1):
            stable_id = f"MOD-{index:03d}"
            dumped = item.model_dump(mode="json")
            changed = changed or item.temp_id != stable_id
            dumped["temp_id"] = stable_id
            normalized_items.append(dumped)
        normalized = ModuleDraftBatch.model_validate({"items": normalized_items})
        if self._fast_local_planning:
            normalized, consolidated = _consolidate_local_modules(normalized)
            changed = changed or consolidated
        return Generated(
            normalized,
            generated.usage,
            repaired=generated.repaired or changed,
        )

    async def milestones(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        modules: ModuleDraftBatch,
    ) -> Generated[MilestoneDraftBatch]:
        if self._fast_local_planning:
            return Generated(
                _build_local_milestones(facts, modules),
                ModelUsage(),
                repaired=False,
            )
        items: list[dict[str, Any]] = []
        usage = ModelUsage()
        repaired = False
        next_milestone_number = 1
        next_sequence = 1
        for module in modules.items:
            generated: Generated[MilestoneDraftBatch] = await self._generate(
                run,
                "milestones.v4",
                {
                    "modules": {"items": [module.model_dump(mode="json")]},
                    "constraints": facts.constraints,
                    "start_date": facts.intake["start_date"],
                    "deadline": facts.intake["deadline"],
                    "allocated_temp_id_start": f"MS-{next_milestone_number:03d}",
                    "allocated_sequence_start": next_sequence,
                },
                ValidationContext(
                    allowed_refs=facts.allowed_refs | {module.temp_id},
                    excluded_refs=facts.excluded_refs,
                    project_start=facts.intake["start_date"],
                ),
            )
            id_map = {
                item.temp_id: f"MS-{next_milestone_number + index:03d}"
                for index, item in enumerate(generated.output.items)
            }
            for offset, item in enumerate(generated.output.items):
                dumped = item.model_dump(mode="json")
                dumped["temp_id"] = id_map[item.temp_id]
                dumped["sequence"] = next_sequence + offset
                dumped["dependency_refs"] = [
                    id_map.get(reference, reference) for reference in item.dependency_refs
                ]
                items.append(dumped)
            next_milestone_number += len(generated.output.items)
            next_sequence += len(generated.output.items)
            usage = _add_usage(usage, generated.usage)
            repaired = repaired or generated.repaired
        return Generated(
            MilestoneDraftBatch.model_validate({"items": items}),
            usage,
            repaired,
        )

    async def tasks(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        modules: ModuleDraftBatch,
        milestones: MilestoneDraftBatch,
    ) -> Generated[TaskDraftBatch]:
        if self._fast_local_planning:
            return Generated(
                _build_local_tasks(facts, modules, milestones),
                ModelUsage(),
                repaired=False,
            )
        items: list[dict[str, Any]] = []
        usage = ModelUsage()
        repaired = False
        next_task_number = 1
        module_requirements = {
            item.temp_id: frozenset(item.requirement_refs) for item in modules.items
        }
        for milestone in sorted(milestones.items, key=lambda item: item.sequence):
            required_refs = tuple(
                sorted(
                    {
                        reference
                        for module_ref in milestone.module_refs
                        for reference in module_requirements.get(module_ref, frozenset())
                    }
                )
            )
            requirement_batches = [
                required_refs[index : index + TASK_REQUIREMENT_BATCH_SIZE]
                for index in range(0, len(required_refs), TASK_REQUIREMENT_BATCH_SIZE)
            ] or [tuple()]
            for requirement_batch in requirement_batches:
                batch_refs = frozenset(requirement_batch)
                generated: Generated[TaskDraftBatch] = await self._generate(
                    run,
                    "tasks.v6",
                    {
                        "milestones": {"items": [milestone.model_dump(mode="json")]},
                        "requirements": [
                            item for item in facts.requirements if item["fact_ref"] in batch_refs
                        ],
                        "required_requirement_refs": list(requirement_batch),
                        "decisions": facts.decisions,
                        "workstreams": sorted(milestone.module_refs),
                        "allocated_temp_id_start": f"TASK-{next_task_number:03d}",
                        "sizing_rules": {
                            "leaf_likely_hours_min": 4,
                            "leaf_likely_hours_max": 24,
                            "split_larger_deliverables": True,
                        },
                    },
                    ValidationContext(
                        allowed_refs=facts.allowed_refs | {milestone.temp_id},
                        required_refs=batch_refs,
                        excluded_refs=facts.excluded_refs,
                    ),
                )
                id_map = {
                    item.temp_id: f"TASK-{next_task_number + index:03d}"
                    for index, item in enumerate(generated.output.items)
                }
                for item in generated.output.items:
                    dumped = item.model_dump(mode="json")
                    dumped["temp_id"] = id_map[item.temp_id]
                    if item.parent_ref is not None:
                        dumped["parent_ref"] = id_map[item.parent_ref]
                    items.append(dumped)
                next_task_number += len(generated.output.items)
                usage = _add_usage(usage, generated.usage)
                repaired = repaired or generated.repaired
        items, titles_changed = _deduplicate_task_titles(items, milestones)
        return Generated(
            TaskDraftBatch.model_validate({"items": items}),
            usage,
            repaired or titles_changed,
        )

    async def acceptance(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        tasks: TaskDraftBatch,
    ) -> Generated[TaskDraftBatch]:
        if self._fast_local_planning:
            # Local tasks are born with testable acceptance evidence. Rewriting the
            # complete task schema here was the slowest and least reliable model pass.
            return Generated(tasks, ModelUsage(), repaired=False)
        groups: dict[str, list[TaskDraft]] = {}
        for task in tasks.items:
            groups.setdefault(task.milestone_ref, []).append(task)
        enriched: list[TaskDraft] = []
        usage = ModelUsage()
        repaired = False
        for milestone_ref, milestone_tasks in groups.items():
            for index in range(0, len(milestone_tasks), ACCEPTANCE_TASK_BATCH_SIZE):
                task_batch = milestone_tasks[index : index + ACCEPTANCE_TASK_BATCH_SIZE]
                task_refs = frozenset(item.temp_id for item in task_batch)
                generated: Generated[TaskDraftBatch] = await self._generate(
                    run,
                    "acceptance.v5",
                    {"tasks": {"items": [item.model_dump(mode="json") for item in task_batch]}},
                    ValidationContext(
                        allowed_refs=facts.allowed_refs | task_refs | {milestone_ref},
                        excluded_refs=facts.excluded_refs,
                    ),
                )
                generated_by_id = {item.temp_id: item for item in generated.output.items}
                for task in task_batch:
                    candidate = generated_by_id.get(task.temp_id)
                    enriched.append(
                        task
                        if candidate is None
                        else task.model_copy(
                            update={
                                "acceptance_criteria": candidate.acceptance_criteria,
                                "definition_of_done": candidate.definition_of_done,
                            }
                        )
                    )
                usage = _add_usage(usage, generated.usage)
                repaired = repaired or generated.repaired
        return Generated(TaskDraftBatch(items=enriched), usage, repaired)

    async def dependencies(
        self, run: AgentRun, tasks: TaskDraftBatch
    ) -> Generated[DependencySuggestionBatch]:
        if self._fast_local_planning:
            # An absent edge is safer than inventing causality. Deterministic graph
            # validation and scheduling remain authoritative downstream.
            return Generated(DependencySuggestionBatch(items=[]), ModelUsage(), repaired=False)
        if len(tasks.items) < 2:
            return Generated(DependencySuggestionBatch(items=[]), ModelUsage(), repaired=False)
        task_refs = frozenset(item.temp_id for item in tasks.items)
        return await self._generate(
            run,
            "dependencies.v3",
            {
                "tasks": [
                    {
                        "temp_id": item.temp_id,
                        "title": item.title,
                        "deliverable": item.deliverable,
                        "milestone_ref": item.milestone_ref,
                    }
                    for item in tasks.items
                ]
            },
            ValidationContext(allowed_refs=task_refs),
        )

    async def risks(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        analysis: ProjectAnalysisOutput,
        modules: ModuleDraftBatch,
        milestones: MilestoneDraftBatch,
        tasks: TaskDraftBatch,
        dependencies: DependencySuggestionBatch,
        schedule: dict[str, Any],
    ) -> Generated[RiskDraftBatch]:
        if self._fast_local_planning:
            # Deterministic schedule and quality gates emit grounded warnings. Avoid
            # an additional large-context local-model pass and never fabricate risk facts.
            return Generated(RiskDraftBatch(items=[]), ModelUsage(), repaired=False)
        plan_refs = frozenset(
            [
                *(item.temp_id for item in modules.items),
                *(item.temp_id for item in milestones.items),
                *(item.temp_id for item in tasks.items),
                *(item.temp_id for item in dependencies.items),
            ]
        )
        return await self._generate(
            run,
            "risks.v3",
            {
                "analysis": analysis.model_dump(mode="json"),
                "facts": {
                    "requirements": facts.requirements,
                    "constraints": facts.constraints,
                    "decisions": facts.decisions,
                },
                "plan": {
                    "modules": modules.model_dump(mode="json"),
                    "milestones": milestones.model_dump(mode="json"),
                    "tasks": tasks.model_dump(mode="json"),
                    "dependencies": dependencies.model_dump(mode="json"),
                },
                "deterministic_schedule": schedule,
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs | plan_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )

    async def _generate[OutputT: BaseModel](
        self,
        run: AgentRun,
        prompt_identifier: str,
        context: dict[str, Any],
        validation_context: ValidationContext,
    ) -> Generated[OutputT]:
        template = get_prompt(prompt_identifier)
        output_type = cast(type[OutputT], template.output_type)
        first = await self._call(run, template, context, output_type, repair=False)
        first_output, first_normalized = _normalize_analysis_fact_refs(
            first.output,
            output_type,
            context,
            validation_context,
        )
        first_output, task_refs_normalized = _normalize_task_requirement_refs(
            first_output,
            output_type,
            context,
            validation_context,
        )
        first_normalized = first_normalized or task_refs_normalized
        validation = validate_candidate(
            first_output.model_dump(mode="json"),
            output_type,
            validation_context,
        )
        if validation.is_valid and validation.candidate is not None:
            return Generated(
                validation.candidate,
                first.usage,
                repaired=first_normalized,
            )
        errors = [item.as_dict() for item in validation.issues]
        repair_context = {
            "repair_directive": (
                "Return one complete corrected candidate. Resolve every listed validation error, "
                "preserve valid grounded content, and copy every required reference exactly."
            ),
            "original_context": context,
            "invalid_candidate": first_output.model_dump(mode="json"),
            "validation_errors": errors,
            "validation_constraints": {
                "allowed_refs": sorted(validation_context.allowed_refs),
                "required_refs": sorted(validation_context.required_refs),
                "excluded_refs": sorted(validation_context.excluded_refs),
                "protected_refs": sorted(validation_context.protected_refs),
            },
        }
        repaired = await self._call(
            run,
            template,
            repair_context,
            output_type,
            repair=True,
        )
        repaired_output, _ = _normalize_analysis_fact_refs(
            repaired.output,
            output_type,
            context,
            validation_context,
        )
        repaired_output, _ = _normalize_task_requirement_refs(
            repaired_output,
            output_type,
            context,
            validation_context,
        )
        repaired_validation = validate_candidate(
            repaired_output.model_dump(mode="json"),
            output_type,
            validation_context,
        )
        if not repaired_validation.is_valid or repaired_validation.candidate is None:
            final_errors = [item.as_dict() for item in repaired_validation.issues]
            grounded_modules = _complete_grounded_module_coverage(
                repaired_output,
                output_type,
                context,
                validation_context,
                final_errors,
            )
            if grounded_modules is not None:
                return Generated(
                    grounded_modules,
                    _add_usage(first.usage, repaired.usage),
                    repaired=True,
                )
            grounded_tasks = _complete_grounded_task_coverage(
                repaired_output,
                output_type,
                context,
                validation_context,
                final_errors,
            )
            if grounded_tasks is not None:
                return Generated(
                    grounded_tasks,
                    _add_usage(first.usage, repaired.usage),
                    repaired=True,
                )
            salvaged = _discard_invalid_optional_items(
                repaired_output,
                output_type,
                validation_context,
                final_errors,
            )
            if salvaged is not None:
                return Generated(
                    salvaged,
                    _add_usage(first.usage, repaired.usage),
                    repaired=True,
                )
            raise NodeFailure(
                "MODEL_OUTPUT_REJECTED",
                "Model output failed validation after one repair attempt.",
                validation=final_errors,
            )
        return Generated(
            repaired_validation.candidate,
            _add_usage(first.usage, repaired.usage),
            repaired=True,
        )

    async def _call[OutputT: BaseModel](
        self,
        run: AgentRun,
        template: PromptTemplate,
        context: dict[str, Any],
        output_type: type[OutputT],
        *,
        repair: bool,
    ) -> Generated[OutputT]:
        remaining = run.token_budget - run.tokens_used
        if remaining <= 0:
            raise NodeFailure(
                "MODEL_TOKEN_BUDGET_EXHAUSTED",
                "Planning token budget is exhausted.",
                partial=True,
            )
        prompt_record = mark_prompt_used(
            self.session,
            key=template.key,
            version=template.version,
            expected_hash=template.template_hash,
        )
        # Persist prompt provenance before yielding to a potentially slow model.
        # Keeping this transaction open would retain row/FK locks for the whole
        # provider call and can block admission of otherwise independent runs.
        self.session.commit()
        instructions, input_text = template.render(context)
        request_id = str(uuid4())
        try:
            result = await self.provider.generate(
                StructuredModelRequest(
                    prompt_key=template.key,
                    prompt_version=template.version,
                    instructions=instructions,
                    input_text=input_text,
                    output_type=output_type,
                    token_budget=min(template.output_token_budget, remaining),
                    safety_identifier=make_safety_identifier(
                        run.initiator_id,
                        self.settings.session_hash_secret.get_secret_value(),
                    ),
                    reasoning_effort=template.reasoning_effort,
                    metadata={
                        "run_id": str(run.id),
                        "repair": str(repair).lower(),
                    },
                )
            )
        except StructuredModelError as error:
            record_provider_usage(
                self.session,
                request_id=request_id,
                prompt_version_id=prompt_record.id,
                provider=self.settings.planning_provider,
                model=self.settings.planning_model or "unconfigured",
                response_id=error.response_id,
                usage=ModelUsage(),
                duration_ms=0,
                outcome=(
                    "refused"
                    if error.code.value == "refused"
                    else "truncated"
                    if error.code.value == "truncated"
                    else "failed"
                ),
                error_code=error.code.value,
            )
            raise NodeFailure(
                f"MODEL_{error.code.value.upper()}",
                str(error),
                retryable=error.retryable,
            ) from error
        except ValidationError as error:
            raise NodeFailure(
                "MODEL_SCHEMA_PARSE_FAILED",
                "Provider output did not satisfy the requested schema.",
                validation=[
                    {
                        "stage": "schema",
                        "code": f"pydantic.{item['type']}",
                        "path": str(item["loc"]),
                        "message": item["msg"],
                    }
                    for item in error.errors(include_url=False, include_input=False)
                ],
            ) from error
        run.tokens_used += result.usage.total_tokens
        record_provider_usage(
            self.session,
            request_id=request_id,
            prompt_version_id=prompt_record.id,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            usage=result.usage,
            duration_ms=result.duration_ms,
            outcome="completed",
        )
        # Usage belongs to the individual provider call, not to the surrounding
        # semantic node. Checkpoint it now so a validation-repair call does not
        # hold AgentRun and prompt locks while waiting on the model again.
        self.session.commit()
        if run.tokens_used > run.token_budget:
            raise NodeFailure(
                "MODEL_TOKEN_BUDGET_EXHAUSTED",
                "Planning token budget was exhausted by the latest model response.",
                partial=True,
            )
        return Generated(result.output, result.usage, repaired=repair)


def _add_usage(first: ModelUsage, second: ModelUsage) -> ModelUsage:
    return ModelUsage(
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        reasoning_tokens=first.reasoning_tokens + second.reasoning_tokens,
        cached_input_tokens=first.cached_input_tokens + second.cached_input_tokens,
        cache_write_input_tokens=(first.cache_write_input_tokens + second.cache_write_input_tokens),
        total_tokens=first.total_tokens + second.total_tokens,
    )


_QUESTION_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "are",
        "be",
        "does",
        "has",
        "have",
        "how",
        "for",
        "is",
        "it",
        "must",
        "of",
        "project",
        "requirement",
        "required",
        "should",
        "the",
        "this",
        "to",
        "what",
        "which",
    }
)


def _question_is_answered_by_confirmed_facts(
    question: ClarificationQuestion,
    facts: PlanningFacts,
) -> bool:
    normalized = " ".join(question.question.casefold().replace("-", " ").split())
    known_intake_topics = (
        (("deadline", "due date", "delivery date"), facts.intake.get("deadline")),
        (("start date", "project start", "project begin"), facts.intake.get("start_date")),
        (("timezone", "time zone"), facts.intake.get("timezone")),
        (
            ("weekly capacity", "hours per week", "weekly hours"),
            facts.intake.get("capacity_hours_per_week"),
        ),
        (
            ("team size", "team members", "how many people"),
            facts.intake.get("team_size"),
        ),
        (("project name", "name of the project"), facts.intake.get("name")),
        (("project goal", "goal of the project"), facts.intake.get("goal")),
        (("desired outcome",), facts.intake.get("desired_outcome")),
    )
    if any(
        value not in (None, "") and any(phrase in normalized for phrase in phrases)
        for phrases, value in known_intake_topics
    ):
        return True
    question_tokens = _meaningful_tokens(normalized)
    if len(question_tokens) < 2:
        return False
    confirmed_texts = [
        _flatten_fact_text(facts.intake.get("notes")),
        *(
            item.get("text", "")
            for item in facts.requirements
            if item["fact_ref"] not in facts.excluded_refs
        ),
        *(
            _flatten_fact_text(item.get("value"))
            for item in facts.constraints
            if item.get("confirmed")
        ),
        *(item.get("text", "") for item in facts.decisions),
    ]
    for text in confirmed_texts:
        fact_tokens = _meaningful_tokens(str(text))
        if len(question_tokens & fact_tokens) / len(question_tokens) >= 0.75:
            return True
    return False


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token not in _QUESTION_STOPWORDS
    }


def _flatten_fact_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_fact_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_fact_text(item) for item in value)
    return str(value) if value is not None else ""


def _normalize_analysis_fact_refs[OutputT: BaseModel](
    candidate: OutputT,
    output_type: type[OutputT],
    original_context: dict[str, Any],
    validation_context: ValidationContext,
) -> tuple[OutputT, bool]:
    """Ground Llama-authored analysis citations in confirmed input identifiers."""
    if output_type is not ProjectAnalysisOutput:
        return candidate, False

    valid_refs = validation_context.allowed_refs - validation_context.excluded_refs
    fact_text: dict[str, str] = {}
    requirement_refs: list[str] = []
    for collection_name in ("requirements", "constraints", "decisions"):
        collection = original_context.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            reference = item.get("fact_ref")
            if not isinstance(reference, str) or reference not in valid_refs:
                continue
            fact_text[reference] = " ".join(
                part
                for part in (
                    _flatten_fact_text(item.get("text")),
                    _flatten_fact_text(item.get("value")),
                    _flatten_fact_text(item.get("value_json")),
                )
                if part
            )
            if collection_name == "requirements":
                requirement_refs.append(reference)
    fallback_refs = requirement_refs or sorted(fact_text)
    if not fallback_refs:
        return candidate, False

    raw = candidate.model_dump(mode="json")
    changed = False
    for field in ("objectives", "success_criteria", "constraints"):
        items = raw.get(field, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("fact_ref") in valid_refs:
                continue
            item["fact_ref"] = _closest_fact_ref(
                str(item.get("text", "")),
                fact_text,
                fallback_refs[0],
            )
            changed = True
    return output_type.model_validate(raw), changed


def _closest_fact_ref(text: str, fact_text: dict[str, str], fallback: str) -> str:
    target_tokens = _meaningful_tokens(text)
    ranked = [
        (
            len(target_tokens & _meaningful_tokens(source_text)),
            reference,
        )
        for reference, source_text in fact_text.items()
    ]
    if not ranked:
        return fallback
    overlap, reference = max(ranked, key=lambda item: (item[0], item[1] == fallback))
    return reference if overlap > 0 else fallback


_TASK_GROUNDING_STOPWORDS = frozenset(
    {
        "build",
        "create",
        "deliver",
        "feature",
        "implement",
        "module",
        "project",
        "system",
        "the",
        "verify",
        "with",
    }
)


def _normalize_task_requirement_refs[OutputT: BaseModel](
    candidate: OutputT,
    output_type: type[OutputT],
    original_context: dict[str, Any],
    validation_context: ValidationContext,
) -> tuple[OutputT, bool]:
    """Ground task requirement and assumption citations in supplied planning facts."""
    if output_type is not TaskDraftBatch:
        return candidate, False
    requirement_text = {
        item.get("fact_ref"): item.get("text")
        for item in original_context.get("requirements", [])
        if isinstance(item, dict)
        and item.get("fact_ref") in validation_context.required_refs
        and isinstance(item.get("text"), str)
    }
    raw = candidate.model_dump(mode="json")
    changed = False
    allowed_refs = validation_context.allowed_refs - validation_context.excluded_refs
    for item in raw.get("items", []):
        grounded_assumptions = [
            reference for reference in item.get("assumption_refs", []) if reference in allowed_refs
        ]
        if grounded_assumptions != item.get("assumption_refs", []):
            item["assumption_refs"] = grounded_assumptions
            changed = True
        if requirement_text:
            task_text = " ".join(
                str(item.get(field, "")) for field in ("title", "description", "deliverable")
            )
            grounded_requirements = [
                reference
                for reference in item.get("requirement_refs", [])
                if reference in requirement_text
                and _task_matches_requirement(task_text, cast(str, requirement_text[reference]))
            ]
            if grounded_requirements != item.get("requirement_refs", []):
                item["requirement_refs"] = grounded_requirements
                changed = True
    return output_type.model_validate(raw), changed


def _task_matches_requirement(task_text: str, requirement_text: str) -> bool:
    return bool(_grounding_tokens(task_text) & _grounding_tokens(requirement_text))


def _grounding_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token in _TASK_GROUNDING_STOPWORDS or len(token) < 3:
            continue
        tokens.add(token[:-1] if token.endswith("s") and len(token) > 4 else token)
    return tokens


def _deduplicate_task_titles(
    items: list[dict[str, Any]],
    milestones: MilestoneDraftBatch,
) -> tuple[list[dict[str, Any]], bool]:
    """Make cross-batch task titles distinct without changing their scope."""
    milestone_names = {item.temp_id: item.name for item in milestones.items}
    seen: set[str] = set()
    changed = False
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        dumped = dict(item)
        title = str(dumped["title"])
        normalized = " ".join(title.casefold().split())
        if normalized in seen:
            milestone_ref = str(dumped["milestone_ref"])
            suffix = f" — {milestone_names.get(milestone_ref, milestone_ref)}"
            unique_title = f"{title[: max(1, 120 - len(suffix))].rstrip()}{suffix}"
            unique_normalized = " ".join(unique_title.casefold().split())
            if unique_normalized in seen:
                suffix = f" — {milestone_ref} {dumped['temp_id']}"
                unique_title = f"{title[: max(1, 120 - len(suffix))].rstrip()}{suffix}"
                unique_normalized = " ".join(unique_title.casefold().split())
            dumped["title"] = unique_title
            normalized = unique_normalized
            changed = True
        seen.add(normalized)
        normalized_items.append(dumped)
    return normalized_items, changed


def _consolidate_local_modules(
    batch: ModuleDraftBatch,
) -> tuple[ModuleDraftBatch, bool]:
    """Keep local-model fan-out near four modules without losing requirement coverage."""
    if len(batch.items) <= FAST_LOCAL_MODULE_TARGET:
        return batch, False

    groups: list[list[Any]] = [[item] for item in batch.items[:FAST_LOCAL_MODULE_TARGET]]
    group_refs = [set(item.requirement_refs) for item in batch.items[:FAST_LOCAL_MODULE_TARGET]]
    for item in batch.items[FAST_LOCAL_MODULE_TARGET:]:
        refs = set(item.requirement_refs)
        candidates = [
            index for index, existing in enumerate(group_refs) if len(existing | refs) <= 20
        ]
        if candidates:
            target = min(candidates, key=lambda index: (len(group_refs[index]), index))
            groups[target].append(item)
            group_refs[target].update(refs)
        else:
            groups.append([item])
            group_refs.append(refs)

    items: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        lead = group[0]
        names = _unique_strings(item.name for item in group)
        deliverables = _unique_strings(value for item in group for value in item.deliverables)
        workstreams = _unique_strings(value for item in group for value in item.workstreams)
        description = lead.description
        if len(group) > 1:
            description = (
                f"{lead.description} This module also coordinates the related delivery areas: "
                f"{', '.join(names[1:])}."
            )
        items.append(
            {
                "temp_id": f"MOD-{index:03d}",
                "name": lead.name,
                "description": _bounded_text(description, 2000),
                "objective": lead.objective,
                "deliverables": deliverables[:8],
                "workstreams": workstreams[:5],
                "requirement_refs": sorted(group_refs[index - 1]),
                "mvp_required": any(item.mvp_required for item in group),
            }
        )
    return ModuleDraftBatch.model_validate({"items": items}), True


def _local_intake_is_complete(facts: PlanningFacts) -> bool:
    """Skip a costly gap pass only when the structured form supplies delivery essentials."""
    intake = facts.intake
    confirmed_requirements = [
        item
        for item in facts.requirements
        if item["fact_ref"] not in facts.excluded_refs
        and item.get("status") == "confirmed"
        and str(item.get("text", "")).strip()
    ]
    return bool(
        str(intake.get("goal", "")).strip()
        and str(intake.get("desired_outcome", "")).strip()
        and intake.get("start_date") is not None
        and intake.get("deadline") is not None
        and intake.get("capacity_hours_per_week")
        and intake.get("team_size")
        and confirmed_requirements
    )


def _build_local_milestones(
    facts: PlanningFacts,
    modules: ModuleDraftBatch,
) -> MilestoneDraftBatch:
    """Create one reviewable milestone per shaped module with zero model fan-out."""
    items: list[dict[str, Any]] = []
    deadline = facts.intake.get("deadline")
    for index, module in enumerate(modules.items, start=1):
        deliverable = module.deliverables[0]
        items.append(
            {
                "temp_id": f"MS-{index:03d}",
                "module_refs": [module.temp_id],
                "name": _bounded_text(f"{module.name} delivery", 120),
                "description": _bounded_text(
                    f"Deliver, verify, and prepare the {module.name} module for owner review. "
                    f"{module.description}",
                    2000,
                ),
                "objective": module.objective,
                "deliverable": deliverable,
                "sequence": index,
                "target_date": deadline,
                "planned_effort_hours": max(8, 8 * len(module.requirement_refs)),
                "acceptance_criteria": [
                    _bounded_text(
                        f"{deliverable} is complete, verified, and ready for owner review",
                        120,
                    )
                ],
                "dependency_refs": [],
            }
        )
    return MilestoneDraftBatch.model_validate({"items": items})


def _build_local_tasks(
    facts: PlanningFacts,
    modules: ModuleDraftBatch,
    milestones: MilestoneDraftBatch,
) -> TaskDraftBatch:
    """Create one grounded, testable task for every confirmed requirement."""
    requirement_text = {
        item["fact_ref"]: str(item["text"]).strip()
        for item in facts.requirements
        if item["fact_ref"] not in facts.excluded_refs
    }
    modules_by_id = {item.temp_id: item for item in modules.items}
    items: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    task_number = 1
    for milestone in sorted(milestones.items, key=lambda item: item.sequence):
        for module_ref in milestone.module_refs:
            module = modules_by_id[module_ref]
            for reference in module.requirement_refs:
                if reference in seen_refs or reference not in requirement_text:
                    continue
                seen_refs.add(reference)
                text = requirement_text[reference]
                items.append(
                    {
                        "temp_id": f"TASK-{task_number:03d}",
                        "milestone_ref": milestone.temp_id,
                        "parent_ref": None,
                        "title": _bounded_text(f"Deliver {text}", 120),
                        "description": _bounded_text(
                            f"Implement and verify the confirmed project requirement: {text}",
                            2000,
                        ),
                        "deliverable": _bounded_text(f"Verified implementation of {text}", 500),
                        "acceptance_criteria": [
                            _bounded_text(
                                f"{reference}: the requested outcome is demonstrated "
                                "and passes review",
                                120,
                            )
                        ],
                        "definition_of_done": [
                            _bounded_text(
                                "Implementation, tests, and review evidence are complete "
                                f"for {reference}",
                                120,
                            )
                        ],
                        "effort_min_hours": 4,
                        "effort_likely_hours": 8,
                        "effort_max_hours": 12,
                        "complexity": "medium",
                        "workstreams": module.workstreams[:3],
                        "skill_tags": [],
                        "mvp_necessity": 100 if module.mvp_required else 60,
                        "user_value": 80,
                        "deadline_urgency": 50,
                        "risk_reduction": 50,
                        "user_preference": 100,
                        "source": "ai",
                        "requirement_refs": [reference],
                        "assumption_refs": [],
                        "locked": False,
                    }
                )
                task_number += 1
    normalized, _ = _deduplicate_task_titles(items, milestones)
    return TaskDraftBatch.model_validate({"items": normalized})


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _bounded_text(value: str, maximum: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= maximum else normalized[:maximum].rstrip()


def _discard_invalid_optional_items[OutputT: BaseModel](
    candidate: OutputT,
    output_type: type[OutputT],
    context: ValidationContext,
    errors: list[dict[str, str]],
) -> OutputT | None:
    optional_batches = (
        ClarificationQuestionBatch,
        DependencySuggestionBatch,
        RiskDraftBatch,
    )
    if output_type not in optional_batches:
        return None
    invalid_indices: set[int] = set()
    for error in errors:
        match = re.fullmatch(r"\$\.items\[(\d+)\](?:\..*)?", error["path"])
        if match is None:
            return None
        invalid_indices.add(int(match.group(1)))
    if not invalid_indices:
        return None
    raw = candidate.model_dump(mode="json")
    raw["items"] = [item for index, item in enumerate(raw["items"]) if index not in invalid_indices]
    validation = validate_candidate(raw, output_type, context)
    return validation.candidate if validation.is_valid else None


def _complete_grounded_module_coverage[OutputT: BaseModel](
    candidate: OutputT,
    output_type: type[OutputT],
    original_context: dict[str, Any],
    validation_context: ValidationContext,
    errors: list[dict[str, str]],
) -> OutputT | None:
    """Add one traceable module when a repaired draft only omitted requirement refs."""
    if output_type is not ModuleDraftBatch or not errors:
        return None
    if {error["code"] for error in errors} != {"business.requirement_coverage"}:
        return None

    batch = cast(ModuleDraftBatch, candidate)
    if len(batch.items) >= 20:
        return None
    covered = {reference for item in batch.items for reference in item.requirement_refs}
    missing = sorted(validation_context.required_refs - covered)
    requirement_text = {
        item.get("fact_ref"): item.get("text")
        for item in original_context.get("requirements", [])
        if isinstance(item, dict)
    }
    if not missing or any(not isinstance(requirement_text.get(ref), str) for ref in missing):
        return None

    missing_text = [cast(str, requirement_text[ref]).strip() for ref in missing]
    used_ids = {item.temp_id for item in batch.items}
    next_number = next(
        number for number in range(1, 100_000) if f"MOD-{number:03d}" not in used_ids
    )
    joined = "; ".join(missing_text)
    deliverables = [f"Verified {text}"[:120] for text in missing_text[:8]]
    if len(missing_text) > 8:
        deliverables[-1] = "Verified remaining confirmed requirements"
    raw = batch.model_dump(mode="json")
    raw["items"].append(
        {
            "temp_id": f"MOD-{next_number:03d}",
            "name": "Confirmed requirement coverage",
            "description": (
                "Deliver and verify the confirmed project requirements omitted by the model: "
                f"{joined}"
            )[:2000],
            "objective": "Complete traceable delivery of every confirmed in-scope requirement.",
            "deliverables": deliverables,
            "workstreams": ["Cross-cutting delivery"],
            "requirement_refs": missing,
            "mvp_required": True,
        }
    )
    validation = validate_candidate(raw, output_type, validation_context)
    return validation.candidate if validation.is_valid else None


def _complete_grounded_task_coverage[OutputT: BaseModel](
    candidate: OutputT,
    output_type: type[OutputT],
    original_context: dict[str, Any],
    validation_context: ValidationContext,
    errors: list[dict[str, str]],
) -> OutputT | None:
    """Add traceable tasks when a repaired milestone draft remains under-decomposed."""
    supported_codes = {
        "business.task_requirement_coverage",
        "business.requirement_task_count",
        "business.dedicated_requirement_task",
    }
    if output_type is not TaskDraftBatch or not errors:
        return None
    if not {error["code"] for error in errors} <= supported_codes:
        return None

    batch = cast(TaskDraftBatch, candidate)
    requirement_text = {
        item.get("fact_ref"): item.get("text")
        for item in original_context.get("requirements", [])
        if isinstance(item, dict)
    }
    required_refs = sorted(validation_context.required_refs)
    if not required_refs or any(
        not isinstance(requirement_text.get(ref), str) for ref in required_refs
    ):
        return None
    milestones = original_context.get("milestones", {}).get("items", [])
    if len(milestones) != 1 or not isinstance(milestones[0], dict):
        return None
    milestone_ref = milestones[0].get("temp_id")
    if not isinstance(milestone_ref, str):
        return None

    dedicated_refs = {
        item.requirement_refs[0] for item in batch.items if len(item.requirement_refs) == 1
    }
    to_add = [reference for reference in required_refs if reference not in dedicated_refs]
    if len(batch.items) + len(to_add) > 100:
        return None
    used_ids = {item.temp_id for item in batch.items}
    next_number = 1
    raw = batch.model_dump(mode="json")
    for reference in to_add:
        while f"TASK-{next_number:03d}" in used_ids:
            next_number += 1
        temp_id = f"TASK-{next_number:03d}"
        used_ids.add(temp_id)
        text = cast(str, requirement_text[reference]).strip()
        title = f"Implement {text}"[:120]
        acceptance = f"{reference} is implemented and verified: {text}"[:120]
        raw["items"].append(
            {
                "temp_id": temp_id,
                "milestone_ref": milestone_ref,
                "parent_ref": None,
                "title": title,
                "description": f"Implement and verify the confirmed requirement: {text}"[:2000],
                "deliverable": f"Verified {text}"[:500],
                "acceptance_criteria": [acceptance],
                "definition_of_done": [f"Evidence is recorded for {reference}"],
                "effort_min_hours": 4,
                "effort_likely_hours": 8,
                "effort_max_hours": 12,
                "complexity": "medium",
                "workstreams": ["Requirement delivery"],
                "skill_tags": [],
                "mvp_necessity": 100,
                "user_value": 80,
                "deadline_urgency": 50,
                "risk_reduction": 50,
                "user_preference": 100,
                "source": "ai",
                "requirement_refs": [reference],
                "assumption_refs": [],
                "locked": False,
            }
        )
        next_number += 1
    validation = validate_candidate(raw, output_type, validation_context)
    return validation.candidate if validation.is_valid else None


def usage_dict(usage: ModelUsage, *, repaired: bool = False) -> dict[str, Any]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "cache_write_input_tokens": usage.cache_write_input_tokens,
        "total_tokens": usage.total_tokens,
        "repaired": repaired,
    }
