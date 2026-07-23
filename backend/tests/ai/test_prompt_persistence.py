from datetime import UTC, datetime

import pytest

from app.ai.prompts.persistence import (
    mark_prompt_used,
    record_provider_usage,
    sync_prompt_catalog,
)
from app.ai.prompts.registry import get_prompt
from app.ai.provider import ModelUsage
from app.db.models.prompt import PromptVersion
from app.db.session import SessionLocal


def test_prompt_catalog_syncs_all_versions_and_used_content_is_immutable() -> None:
    with SessionLocal() as session:
        records = sync_prompt_catalog(session)
        session.commit()
        assert len(records) == 12

        template = get_prompt("analysis.v1")
        record = mark_prompt_used(
            session,
            key=template.key,
            version=template.version,
            expected_hash=template.template_hash,
        )
        session.commit()
        assert record.first_used_at is not None

        record.purpose = "Attempted unversioned mutation"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()


def test_used_prompt_cannot_be_deleted() -> None:
    with SessionLocal() as session:
        sync_prompt_catalog(session)
        template = get_prompt("modules.v1")
        record = mark_prompt_used(
            session,
            key=template.key,
            version=template.version,
            expected_hash=template.template_hash,
        )
        session.commit()
        session.delete(record)
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()


def test_prompt_hash_mismatch_fails_before_usage() -> None:
    with SessionLocal() as session:
        sync_prompt_catalog(session)
        with pytest.raises(ValueError, match="unexpected content hash"):
            mark_prompt_used(
                session,
                key="analysis",
                version="v1",
                expected_hash=f"sha256:{'0' * 64}",
            )


def test_provider_usage_captures_all_token_classes_and_is_append_only() -> None:
    with SessionLocal() as session:
        records = sync_prompt_catalog(session)
        prompt = next(item for item in records if item.key == "analysis")
        usage = record_provider_usage(
            session,
            request_id="request-usage-1",
            prompt_version_id=prompt.id,
            provider="openai",
            model="gpt-5.6-terra",
            response_id="resp-1",
            usage=ModelUsage(
                input_tokens=100,
                output_tokens=40,
                reasoning_tokens=10,
                cached_input_tokens=20,
                cache_write_input_tokens=5,
                total_tokens=140,
            ),
            duration_ms=900,
            outcome="completed",
        )
        session.commit()
        assert usage.cache_write_input_tokens == 5

        usage.outcome = "failed"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()


def test_sync_rejects_drift_after_use() -> None:
    with SessionLocal() as session:
        records = sync_prompt_catalog(session)
        record = next(item for item in records if item.key == "risks")
        record.first_used_at = datetime.now(UTC)
        session.commit()

        session.query(PromptVersion).filter(PromptVersion.id == record.id).update(
            {"template_hash": f"sha256:{'f' * 64}"}
        )
        session.commit()
        with pytest.raises(ValueError, match="differs from code catalog"):
            sync_prompt_catalog(session)
