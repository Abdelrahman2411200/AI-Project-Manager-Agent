"""Persistence boundary for the code-owned immutable prompt catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts.registry import DATA_END, DATA_START, GLOBAL_POLICY, PROMPT_REGISTRY
from app.ai.provider import ModelUsage
from app.db.models.prompt import PromptVersion, ProviderUsage


def sync_prompt_catalog(session: Session) -> list[PromptVersion]:
    """Insert/update unused versions and reject drift after first use."""
    synchronized: list[PromptVersion] = []
    for template in PROMPT_REGISTRY.values():
        record = session.scalar(
            select(PromptVersion).where(
                PromptVersion.key == template.key,
                PromptVersion.version == template.version,
            )
        )
        values = {
            "template_hash": template.template_hash,
            "schema_name": template.schema_name,
            "purpose": template.purpose,
            "system_template": f"{GLOBAL_POLICY}\nTask:\n{template.task_instructions}",
            "user_template": f"{DATA_START}\n{{context_json}}\n{DATA_END}",
            "output_token_budget": template.output_token_budget,
            "reasoning_effort": template.reasoning_effort,
        }
        if record is None:
            record = PromptVersion(
                key=template.key,
                version=template.version,
                **values,
            )
            session.add(record)
        elif record.template_hash != template.template_hash:
            if record.first_used_at is not None:
                raise ValueError(f"Used prompt {template.identifier} differs from code catalog.")
            for field, value in values.items():
                setattr(record, field, value)
        synchronized.append(record)
    session.flush()
    return synchronized


def mark_prompt_used(
    session: Session,
    *,
    key: str,
    version: str,
    expected_hash: str,
) -> PromptVersion:
    record = session.scalar(
        select(PromptVersion)
        .where(PromptVersion.key == key, PromptVersion.version == version)
        .with_for_update()
    )
    if record is None:
        raise LookupError(f"Prompt version {key}.{version} is not registered.")
    if record.template_hash != expected_hash:
        raise ValueError(f"Prompt version {key}.{version} has an unexpected content hash.")
    if record.first_used_at is None:
        record.first_used_at = datetime.now(UTC)
        session.flush()
    return record


def record_provider_usage(
    session: Session,
    *,
    request_id: str,
    prompt_version_id: UUID,
    provider: str,
    model: str,
    response_id: str | None,
    usage: ModelUsage,
    duration_ms: int,
    outcome: str,
    error_code: str | None = None,
) -> ProviderUsage:
    record = ProviderUsage(
        request_id=request_id,
        prompt_version_id=prompt_version_id,
        provider=provider,
        model=model,
        response_id=response_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_input_tokens=usage.cache_write_input_tokens,
        total_tokens=usage.total_tokens,
        duration_ms=duration_ms,
        outcome=outcome,
        error_code=error_code,
    )
    session.add(record)
    session.flush()
    return record
