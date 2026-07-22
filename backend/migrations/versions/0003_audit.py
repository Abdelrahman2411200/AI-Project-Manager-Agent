"""Create append-only audit events.

Revision ID: 0003_audit
Revises: 0002_project_intake
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_audit"
down_revision: str | None = "0002_project_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before_ref", json_document, nullable=True),
        sa.Column("after_ref", json_document, nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'agent', 'worker')",
            name="actor_type_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_audit_events_owner_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_audit_events_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_owner_occurred", "audit_events", ["owner_id", "occurred_at"])
    op.create_index(
        "ix_audit_events_project_occurred", "audit_events", ["project_id", "occurred_at"]
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_audit_event_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER audit_events_reject_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_reject_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only');
            END
            """
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_reject_update")
        op.execute("DROP TRIGGER IF EXISTS audit_events_reject_delete")
    op.drop_table("audit_events")
    if dialect == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
