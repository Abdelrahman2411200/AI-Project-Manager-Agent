"""Create immutable prompt versions and append-only provider usage.

Revision ID: 0004_ai_contracts
Revises: 0003_audit
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ai_contracts"
down_revision: str | None = "0003_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("template_hash", sa.String(length=71), nullable=False),
        sa.Column("schema_name", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("output_token_budget", sa.Integer(), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("output_token_budget > 0", name="prompt_token_budget_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        sa.UniqueConstraint("key", "version", name="prompt_version_key_version"),
    )
    op.create_index(
        "ix_prompt_versions_active_key", "prompt_versions", ["key", "is_active"], unique=False
    )
    op.create_table(
        "provider_usage",
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("response_id", sa.String(length=160), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name="provider_usage_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "outcome IN ('completed', 'refused', 'truncated', 'failed')",
            name="provider_usage_outcome_allowed",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0 "
            "AND cached_input_tokens >= 0 AND cache_write_input_tokens >= 0 "
            "AND total_tokens >= 0",
            name="provider_usage_tokens_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name="fk_provider_usage_prompt_version_id_prompt_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_usage"),
        sa.UniqueConstraint("request_id", name="uq_provider_usage_request_id"),
    )
    op.create_index(
        "ix_provider_usage_model_occurred",
        "provider_usage",
        ["provider", "model", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_provider_usage_prompt_occurred",
        "provider_usage",
        ["prompt_version_id", "occurred_at"],
        unique=False,
    )
    _create_immutability_triggers()


def _create_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_used_prompt_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF OLD.first_used_at IS NOT NULL THEN
                        RAISE EXCEPTION 'used prompt versions are immutable';
                    END IF;
                    RETURN OLD;
                END IF;
                IF (
                    (OLD.first_used_at IS NOT NULL OR NEW.first_used_at IS NOT NULL)
                    AND (
                        OLD.key IS DISTINCT FROM NEW.key
                        OR OLD.version IS DISTINCT FROM NEW.version
                        OR OLD.template_hash IS DISTINCT FROM NEW.template_hash
                        OR OLD.schema_name IS DISTINCT FROM NEW.schema_name
                        OR OLD.purpose IS DISTINCT FROM NEW.purpose
                        OR OLD.system_template IS DISTINCT FROM NEW.system_template
                        OR OLD.user_template IS DISTINCT FROM NEW.user_template
                        OR OLD.output_token_budget IS DISTINCT FROM NEW.output_token_budget
                        OR OLD.reasoning_effort IS DISTINCT FROM NEW.reasoning_effort
                        OR (
                            OLD.first_used_at IS NOT NULL
                            AND OLD.first_used_at IS DISTINCT FROM NEW.first_used_at
                        )
                    )
                ) THEN
                    RAISE EXCEPTION 'used prompt versions are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER prompt_versions_immutable
            BEFORE UPDATE OR DELETE ON prompt_versions
            FOR EACH ROW EXECUTE FUNCTION reject_used_prompt_mutation()
            """
        )
        op.execute(
            """
            CREATE FUNCTION reject_provider_usage_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'provider usage records are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER provider_usage_append_only
            BEFORE UPDATE OR DELETE ON provider_usage
            FOR EACH ROW EXECUTE FUNCTION reject_provider_usage_mutation()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER prompt_versions_reject_used_update
            BEFORE UPDATE ON prompt_versions
            WHEN (
                (OLD.first_used_at IS NOT NULL OR NEW.first_used_at IS NOT NULL)
                AND (
                    OLD.key IS NOT NEW.key
                    OR OLD.version IS NOT NEW.version
                    OR OLD.template_hash IS NOT NEW.template_hash
                    OR OLD.schema_name IS NOT NEW.schema_name
                    OR OLD.purpose IS NOT NEW.purpose
                    OR OLD.system_template IS NOT NEW.system_template
                    OR OLD.user_template IS NOT NEW.user_template
                    OR OLD.output_token_budget IS NOT NEW.output_token_budget
                    OR OLD.reasoning_effort IS NOT NEW.reasoning_effort
                    OR (
                        OLD.first_used_at IS NOT NULL
                        AND OLD.first_used_at IS NOT NEW.first_used_at
                    )
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'used prompt versions are immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER prompt_versions_reject_used_delete
            BEFORE DELETE ON prompt_versions
            WHEN OLD.first_used_at IS NOT NULL
            BEGIN
                SELECT RAISE(ABORT, 'used prompt versions are immutable');
            END
            """
        )
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER provider_usage_reject_{operation.lower()}
                BEFORE {operation} ON provider_usage
                BEGIN
                    SELECT RAISE(ABORT, 'provider usage records are append-only');
                END
                """
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS provider_usage_append_only ON provider_usage")
        op.execute("DROP FUNCTION IF EXISTS reject_provider_usage_mutation()")
        op.execute("DROP TRIGGER IF EXISTS prompt_versions_immutable ON prompt_versions")
        op.execute("DROP FUNCTION IF EXISTS reject_used_prompt_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS provider_usage_reject_update")
        op.execute("DROP TRIGGER IF EXISTS provider_usage_reject_delete")
        op.execute("DROP TRIGGER IF EXISTS prompt_versions_reject_used_update")
        op.execute("DROP TRIGGER IF EXISTS prompt_versions_reject_used_delete")
    op.drop_table("provider_usage")
    op.drop_table("prompt_versions")
