"""Prompt-version catalog and append-only provider usage accounting."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class PromptVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("key", "version", name="prompt_version_key_version"),
        CheckConstraint("output_token_budget > 0", name="prompt_token_budget_positive"),
        Index("ix_prompt_versions_active_key", "key", "is_active"),
    )

    key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    system_template: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    output_token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderUsage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "provider_usage"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('completed', 'refused', 'truncated', 'failed')",
            name="provider_usage_outcome_allowed",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0 "
            "AND cached_input_tokens >= 0 AND cache_write_input_tokens >= 0 "
            "AND total_tokens >= 0",
            name="provider_usage_tokens_nonnegative",
        ),
        CheckConstraint("duration_ms >= 0", name="provider_usage_duration_nonnegative"),
        Index("ix_provider_usage_prompt_occurred", "prompt_version_id", "occurred_at"),
        Index("ix_provider_usage_model_occurred", "provider", "model", "occurred_at"),
    )

    request_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    response_id: Mapped[str | None] = mapped_column(String(160))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_write_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


@event.listens_for(PromptVersion, "before_update")
def _prevent_used_prompt_update(_: object, __: object, target: PromptVersion) -> None:
    if target.first_used_at is not None:
        from sqlalchemy import inspect

        state = inspect(target)
        immutable_fields = (
            "key",
            "version",
            "template_hash",
            "schema_name",
            "purpose",
            "system_template",
            "user_template",
            "output_token_budget",
            "reasoning_effort",
        )
        if any(state.attrs[field].history.has_changes() for field in immutable_fields):
            raise ValueError("Used prompt versions are immutable.")
        first_used_history = state.attrs["first_used_at"].history
        if first_used_history.has_changes() and any(
            previous is not None for previous in first_used_history.deleted
        ):
            raise ValueError("Used prompt versions are immutable.")


@event.listens_for(PromptVersion, "before_delete")
def _prevent_used_prompt_delete(_: object, __: object, target: PromptVersion) -> None:
    if target.first_used_at is not None:
        raise ValueError("Used prompt versions are immutable.")


@event.listens_for(ProviderUsage, "before_update")
@event.listens_for(ProviderUsage, "before_delete")
def _prevent_usage_mutation(*_: object) -> None:
    raise ValueError("Provider usage records are append-only.")
