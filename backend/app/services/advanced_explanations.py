"""Schema-constrained, grounded explanations for deterministic advanced results."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.prompts.persistence import (
    mark_prompt_used,
    record_provider_usage,
    sync_prompt_catalog,
)
from app.ai.prompts.registry import get_prompt
from app.ai.provider import (
    ModelUsage,
    StructuredModelError,
    StructuredModelProvider,
    StructuredModelRequest,
    make_safety_identifier,
)
from app.ai.schemas.outputs import GroundedExplanation
from app.core.config import Settings
from app.domain.grounding import validate_grounded_explanation


class AdvancedExplanationGroundingError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Advanced explanation contains unsupported claims.")
        self.errors = errors


class AdvancedExplanationService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id

    async def generate(
        self,
        *,
        kind: Literal["change_impact", "scenario"],
        deterministic_result: dict[str, Any],
        provider: StructuredModelProvider,
        settings: Settings,
        artifact_id: UUID,
    ) -> tuple[GroundedExplanation, ModelUsage]:
        prompt = get_prompt(f"{kind}.v2")
        evidence = {
            "RESULT-BASELINE": deterministic_result.get("baseline", {}),
            "RESULT-SCENARIO": deterministic_result.get("scenario", {}),
            "RESULT-DELTA": deterministic_result.get("delta", deterministic_result),
            "RESULT-SOURCES": deterministic_result.get("sources", {}),
        }
        sync_prompt_catalog(self.session)
        prompt_record = mark_prompt_used(
            self.session,
            key=prompt.key,
            version=prompt.version,
            expected_hash=prompt.template_hash,
        )
        instructions, input_text = prompt.render(
            {
                "artifact_id": str(artifact_id),
                "evidence": evidence,
                "approval_boundary": (
                    "This explanation cannot apply changes. Owner approval remains required."
                ),
            }
        )
        try:
            result = await provider.generate(
                StructuredModelRequest(
                    prompt_key=prompt.key,
                    prompt_version=prompt.version,
                    instructions=instructions,
                    input_text=input_text,
                    output_type=GroundedExplanation,
                    token_budget=prompt.output_token_budget,
                    safety_identifier=make_safety_identifier(
                        self.owner_id,
                        settings.session_hash_secret.get_secret_value(),
                    ),
                    reasoning_effort=prompt.reasoning_effort,
                    metadata={
                        "artifact_id": str(artifact_id),
                        "workflow": kind,
                    },
                )
            )
        except StructuredModelError as error:
            record_provider_usage(
                self.session,
                request_id=self.request_id,
                prompt_version_id=prompt_record.id,
                provider=settings.planning_provider,
                model=settings.planning_model or "unconfigured",
                response_id=error.response_id,
                usage=ModelUsage(),
                duration_ms=0,
                outcome="failed",
                error_code=error.code.value,
            )
            raise
        errors = validate_grounded_explanation(result.output, evidence)
        if errors:
            record_provider_usage(
                self.session,
                request_id=self.request_id,
                prompt_version_id=prompt_record.id,
                provider=result.provider,
                model=result.model,
                response_id=result.response_id,
                usage=result.usage,
                duration_ms=result.duration_ms,
                outcome="failed",
                error_code="UNSUPPORTED_CLAIMS",
            )
            raise AdvancedExplanationGroundingError(errors)
        record_provider_usage(
            self.session,
            request_id=self.request_id,
            prompt_version_id=prompt_record.id,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            usage=result.usage,
            duration_ms=result.duration_ms,
            outcome="completed",
        )
        return result.output, result.usage
