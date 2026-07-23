"""Schema-constrained semantic nodes for the persistent planning workflow."""

from __future__ import annotations

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
    ClarificationQuestionBatch,
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    RiskDraftBatch,
    TaskDraftBatch,
)
from app.ai.validation import ValidationContext, validate_candidate
from app.core.config import Settings
from app.db.models.run import AgentRun
from app.services.planning_context import PlanningFacts
from app.workflows.engine import NodeFailure


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

    async def detect_gaps(
        self, run: AgentRun, facts: PlanningFacts
    ) -> Generated[ClarificationQuestionBatch]:
        return await self._generate(
            run,
            "clarification.v1",
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

    async def analyze(
        self, run: AgentRun, facts: PlanningFacts
    ) -> Generated[ProjectAnalysisOutput]:
        return await self._generate(
            run,
            "analysis.v1",
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
        return await self._generate(
            run,
            "modules.v1",
            {
                "analysis": analysis.model_dump(mode="json"),
                "requirements": facts.requirements,
                "excluded_refs": sorted(facts.excluded_refs),
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )

    async def milestones(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        modules: ModuleDraftBatch,
    ) -> Generated[MilestoneDraftBatch]:
        module_refs = frozenset(item.temp_id for item in modules.items)
        return await self._generate(
            run,
            "milestones.v1",
            {
                "modules": modules.model_dump(mode="json"),
                "constraints": facts.constraints,
                "start_date": facts.intake["start_date"],
                "deadline": facts.intake["deadline"],
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs | module_refs,
                excluded_refs=facts.excluded_refs,
                project_start=facts.intake["start_date"],
            ),
        )

    async def tasks(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        milestones: MilestoneDraftBatch,
    ) -> Generated[TaskDraftBatch]:
        milestone_refs = frozenset(item.temp_id for item in milestones.items)
        return await self._generate(
            run,
            "tasks.v1",
            {
                "milestones": milestones.model_dump(mode="json"),
                "requirements": facts.requirements,
                "decisions": facts.decisions,
                "workstreams": sorted(
                    {workstream for item in milestones.items for workstream in item.module_refs}
                ),
            },
            ValidationContext(
                allowed_refs=facts.allowed_refs | milestone_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )

    async def acceptance(
        self,
        run: AgentRun,
        facts: PlanningFacts,
        tasks: TaskDraftBatch,
    ) -> Generated[TaskDraftBatch]:
        task_refs = frozenset(item.temp_id for item in tasks.items)
        milestone_refs = frozenset(item.milestone_ref for item in tasks.items)
        generated: Generated[TaskDraftBatch] = await self._generate(
            run,
            "acceptance.v1",
            {"tasks": tasks.model_dump(mode="json")},
            ValidationContext(
                allowed_refs=facts.allowed_refs | task_refs | milestone_refs,
                excluded_refs=facts.excluded_refs,
            ),
        )
        if {item.temp_id for item in generated.output.items} != task_refs:
            raise NodeFailure(
                "ACCEPTANCE_TASK_SET_CHANGED",
                "Acceptance refinement must preserve the exact task set.",
                validation=[
                    {
                        "stage": "business",
                        "code": "acceptance.task_set_changed",
                        "path": "$.items",
                        "message": "Acceptance refinement changed task identifiers.",
                    }
                ],
            )
        return generated

    async def dependencies(
        self, run: AgentRun, tasks: TaskDraftBatch
    ) -> Generated[DependencySuggestionBatch]:
        task_refs = frozenset(item.temp_id for item in tasks.items)
        return await self._generate(
            run,
            "dependencies.v1",
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
            "risks.v1",
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
        validation = validate_candidate(
            first.output.model_dump(mode="json"),
            output_type,
            validation_context,
        )
        if validation.is_valid and validation.candidate is not None:
            return Generated(validation.candidate, first.usage, repaired=False)
        errors = [item.as_dict() for item in validation.issues]
        repair_context = {
            "invalid_candidate": first.output.model_dump(mode="json"),
            "validation_errors": errors,
        }
        repaired = await self._call(
            run,
            template,
            repair_context,
            output_type,
            repair=True,
        )
        repaired_validation = validate_candidate(
            repaired.output.model_dump(mode="json"),
            output_type,
            validation_context,
        )
        if not repaired_validation.is_valid or repaired_validation.candidate is None:
            final_errors = [item.as_dict() for item in repaired_validation.issues]
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
                provider="openai",
                model=self.settings.openai_model,
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
