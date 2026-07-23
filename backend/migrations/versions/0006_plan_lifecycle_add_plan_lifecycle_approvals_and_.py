"""add plan lifecycle approvals and protection

Revision ID: 0006_plan_lifecycle
Revises: 0005_planning_workflow
Create Date: 2026-07-23 18:41:13.829193
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_plan_lifecycle"
down_revision: str | None = "0005_planning_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_approvals",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved', 'changes_requested', 'rejected')",
            name=op.f("ck_plan_approvals_decision_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_plan_approvals_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_plan_approvals_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_plan_approvals_version_id_plan_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_approvals")),
    )
    op.create_index(
        "ix_plan_approvals_project_created",
        "plan_approvals",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_plan_approvals_version_created",
        "plan_approvals",
        ["version_id", "created_at"],
        unique=False,
    )
    op.add_column(
        "milestones",
        sa.Column("source", sa.String(length=16), server_default="ai", nullable=False),
    )
    op.add_column(
        "milestones",
        sa.Column("protected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "milestones",
        sa.Column("locked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "milestones",
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index(
        "uq_plan_versions_one_active_per_project",
        "plan_versions",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )
    op.add_column(
        "task_dependencies",
        sa.Column("source", sa.String(length=16), server_default="ai", nullable=False),
    )
    op.add_column(
        "task_dependencies",
        sa.Column("protected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("protected", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_milestones_source_allowed",
            "milestones",
            "source IN ('ai', 'user')",
        )
        op.create_check_constraint(
            "ck_milestones_row_version_positive",
            "milestones",
            "row_version >= 1",
        )
        op.create_check_constraint(
            "ck_task_dependencies_source_allowed",
            "task_dependencies",
            "source IN ('ai', 'user')",
        )
    _create_lifecycle_triggers()


def downgrade() -> None:
    _drop_lifecycle_triggers()
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "ck_task_dependencies_source_allowed",
            "task_dependencies",
            type_="check",
        )
        op.drop_constraint(
            "ck_milestones_row_version_positive",
            "milestones",
            type_="check",
        )
        op.drop_constraint(
            "ck_milestones_source_allowed",
            "milestones",
            type_="check",
        )
    op.drop_column("tasks", "protected")
    op.drop_column("task_dependencies", "protected")
    op.drop_column("task_dependencies", "source")
    op.drop_index(
        "uq_plan_versions_one_active_per_project",
        table_name="plan_versions",
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )
    op.drop_column("milestones", "row_version")
    op.drop_column("milestones", "locked")
    op.drop_column("milestones", "protected")
    op.drop_column("milestones", "source")
    op.drop_index("ix_plan_approvals_version_created", table_name="plan_approvals")
    op.drop_index("ix_plan_approvals_project_created", table_name="plan_approvals")
    op.drop_table("plan_approvals")


def _create_lifecycle_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_plan_approval_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'plan approvals are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER plan_approvals_append_only
            BEFORE UPDATE OR DELETE ON plan_approvals
            FOR EACH ROW EXECUTE FUNCTION reject_plan_approval_mutation()
            """
        )
        op.execute(
            """
            CREATE FUNCTION reject_frozen_plan_content_mutation()
            RETURNS trigger AS $$
            DECLARE target_version uuid;
            BEGIN
                target_version := CASE
                    WHEN TG_OP = 'DELETE' THEN OLD.version_id
                    ELSE NEW.version_id
                END;
                IF EXISTS (
                    SELECT 1 FROM plan_versions
                    WHERE id = target_version AND state <> 'draft'
                ) THEN
                    RAISE EXCEPTION 'reviewed plan content is immutable';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in (
            "project_analyses",
            "milestones",
            "tasks",
            "task_dependencies",
            "risks",
        ):
            op.execute(
                f"""
                CREATE TRIGGER {table}_frozen_content
                BEFORE INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_frozen_plan_content_mutation()
                """
            )
        op.execute(
            """
            CREATE FUNCTION reject_frozen_plan_metadata_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF OLD.state <> 'draft' AND (
                    OLD.project_id IS DISTINCT FROM NEW.project_id
                    OR OLD.number IS DISTINCT FROM NEW.number
                    OR OLD.based_on_id IS DISTINCT FROM NEW.based_on_id
                    OR OLD.reason IS DISTINCT FROM NEW.reason
                    OR OLD.content_hash IS DISTINCT FROM NEW.content_hash
                    OR OLD.quality_status IS DISTINCT FROM NEW.quality_status
                    OR OLD.quality_report IS DISTINCT FROM NEW.quality_report
                    OR OLD.source_run_id IS DISTINCT FROM NEW.source_run_id
                ) THEN
                    RAISE EXCEPTION 'reviewed plan metadata is immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER plan_versions_frozen_metadata
            BEFORE UPDATE ON plan_versions
            FOR EACH ROW EXECUTE FUNCTION reject_frozen_plan_metadata_mutation()
            """
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER plan_approvals_reject_{operation.lower()}
                BEFORE {operation} ON plan_approvals
                BEGIN
                    SELECT RAISE(ABORT, 'plan approvals are append-only');
                END
                """
            )
        for table in (
            "project_analyses",
            "milestones",
            "tasks",
            "task_dependencies",
            "risks",
        ):
            for operation, version_expr in (
                ("insert", "NEW.version_id"),
                ("update", "NEW.version_id"),
                ("delete", "OLD.version_id"),
            ):
                op.execute(
                    f"""
                    CREATE TRIGGER {table}_reject_frozen_{operation}
                    BEFORE {operation.upper()} ON {table}
                    WHEN EXISTS (
                        SELECT 1 FROM plan_versions
                        WHERE id = {version_expr} AND state <> 'draft'
                    )
                    BEGIN
                        SELECT RAISE(ABORT, 'reviewed plan content is immutable');
                    END
                    """
                )
        op.execute(
            """
            CREATE TRIGGER plan_versions_reject_frozen_metadata
            BEFORE UPDATE ON plan_versions
            WHEN OLD.state <> 'draft' AND (
                OLD.project_id IS NOT NEW.project_id
                OR OLD.number IS NOT NEW.number
                OR OLD.based_on_id IS NOT NEW.based_on_id
                OR OLD.reason IS NOT NEW.reason
                OR OLD.content_hash IS NOT NEW.content_hash
                OR OLD.quality_status IS NOT NEW.quality_status
                OR OLD.quality_report IS NOT NEW.quality_report
                OR OLD.source_run_id IS NOT NEW.source_run_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'reviewed plan metadata is immutable');
            END
            """
        )


def _drop_lifecycle_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS plan_versions_frozen_metadata ON plan_versions")
        op.execute("DROP FUNCTION IF EXISTS reject_frozen_plan_metadata_mutation()")
        for table in (
            "project_analyses",
            "milestones",
            "tasks",
            "task_dependencies",
            "risks",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_frozen_content ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_frozen_plan_content_mutation()")
        op.execute("DROP TRIGGER IF EXISTS plan_approvals_append_only ON plan_approvals")
        op.execute("DROP FUNCTION IF EXISTS reject_plan_approval_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS plan_versions_reject_frozen_metadata")
        for table in (
            "project_analyses",
            "milestones",
            "tasks",
            "task_dependencies",
            "risks",
        ):
            for operation in ("insert", "update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {table}_reject_frozen_{operation}")
        op.execute("DROP TRIGGER IF EXISTS plan_approvals_reject_update")
        op.execute("DROP TRIGGER IF EXISTS plan_approvals_reject_delete")
