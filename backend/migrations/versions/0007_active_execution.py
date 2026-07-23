"""add active execution history and deterministic monitoring snapshots

Revision ID: 0007_active_execution
Revises: 0006_plan_lifecycle
Create Date: 2026-07-23 21:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_active_execution"
down_revision: str | None = "0006_plan_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_VALUES = "'pending', 'ready', 'in_progress', 'blocked', 'completed', 'cancelled'"


def upgrade() -> None:
    _extend_job_types()
    op.create_table(
        "task_execution_projections",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "progress_fraction",
            sa.Numeric(precision=5, scale=4),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "actual_effort_hours",
            sa.Numeric(precision=10, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("blocked_reason", sa.String(length=1000), nullable=True),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({STATUS_VALUES})",
            name=op.f("ck_task_execution_projections_status_allowed"),
        ),
        sa.CheckConstraint(
            "progress_fraction >= 0 AND progress_fraction <= 1",
            name=op.f("ck_task_execution_projections_progress_fraction_range"),
        ),
        sa.CheckConstraint(
            "actual_effort_hours >= 0",
            name=op.f("ck_task_execution_projections_actual_effort_nonnegative"),
        ),
        sa.CheckConstraint(
            "row_version >= 1",
            name=op.f("ck_task_execution_projections_row_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_task_execution_projections_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_task_execution_projections_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name=op.f("fk_task_execution_projections_task_version_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_execution_projections")),
        sa.UniqueConstraint(
            "task_id",
            name="task_execution_task",
        ),
    )
    op.create_index(
        "ix_task_execution_project_version_status",
        "task_execution_projections",
        ["project_id", "version_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_task_execution_version_changed",
        "task_execution_projections",
        ["version_id", "status_changed_at"],
        unique=False,
    )
    _create_status_events()
    _create_progress_updates()
    _create_monitoring_snapshots()
    op.execute(
        """
        INSERT INTO task_execution_projections (
            id, project_id, version_id, task_id, status, progress_fraction,
            actual_effort_hours, blocked_reason, status_changed_at, row_version,
            created_at, updated_at
        )
        SELECT t.id, p.project_id, t.version_id, t.id, t.status, 0, 0, NULL,
               CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM tasks t
        JOIN plan_versions p ON p.id = t.version_id
        WHERE p.state = 'active'
        """
    )
    _create_append_only_triggers()


def downgrade() -> None:
    _drop_append_only_triggers()
    op.drop_index("ix_monitoring_version_calculated", table_name="monitoring_snapshots")
    op.drop_index("ix_monitoring_project_calculated", table_name="monitoring_snapshots")
    op.drop_table("monitoring_snapshots")
    op.drop_index("ix_progress_updates_project_occurred", table_name="progress_updates")
    op.drop_index("ix_progress_updates_task_occurred", table_name="progress_updates")
    op.drop_table("progress_updates")
    op.drop_index("ix_task_status_events_project_occurred", table_name="task_status_events")
    op.drop_index("ix_task_status_events_task_occurred", table_name="task_status_events")
    op.drop_table("task_status_events")
    op.drop_index(
        "ix_task_execution_version_changed",
        table_name="task_execution_projections",
    )
    op.drop_index(
        "ix_task_execution_project_version_status",
        table_name="task_execution_projections",
    )
    op.drop_table("task_execution_projections")
    _restrict_job_types()


def _create_status_events() -> None:
    op.create_table(
        "task_status_events",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("progress_fraction", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("event_key", sa.String(length=240), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({STATUS_VALUES})",
            name=op.f("ck_task_status_events_from_status_allowed"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({STATUS_VALUES})",
            name=op.f("ck_task_status_events_to_status_allowed"),
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system')",
            name=op.f("ck_task_status_events_actor_type_allowed"),
        ),
        sa.CheckConstraint(
            "progress_fraction >= 0 AND progress_fraction <= 1",
            name=op.f("ck_task_status_events_progress_fraction_range"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_task_status_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_task_status_events_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_task_status_events_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name=op.f("fk_task_status_events_task_version_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_status_events")),
        sa.UniqueConstraint(
            "event_key",
            name="task_status_event_key",
        ),
    )
    op.create_index(
        "ix_task_status_events_task_occurred",
        "task_status_events",
        ["task_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_task_status_events_project_occurred",
        "task_status_events",
        ["project_id", "occurred_at"],
        unique=False,
    )


def _create_progress_updates() -> None:
    op.create_table(
        "progress_updates",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("fraction", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("actual_effort_hours", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("event_key", sa.String(length=240), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "fraction >= 0 AND fraction <= 1",
            name=op.f("ck_progress_updates_fraction_range"),
        ),
        sa.CheckConstraint(
            "actual_effort_hours >= 0",
            name=op.f("ck_progress_updates_actual_effort_nonnegative"),
        ),
        sa.CheckConstraint(
            "source IN ('user', 'system')",
            name=op.f("ck_progress_updates_source_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_progress_updates_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_progress_updates_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_progress_updates_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"],
            ["tasks.id", "tasks.version_id"],
            name=op.f("fk_progress_updates_task_version_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_progress_updates")),
        sa.UniqueConstraint(
            "event_key",
            name="progress_update_event_key",
        ),
    )
    op.create_index(
        "ix_progress_updates_task_occurred",
        "progress_updates",
        ["task_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_progress_updates_project_occurred",
        "progress_updates",
        ["project_id", "occurred_at"],
        unique=False,
    )


def _create_monitoring_snapshots() -> None:
    op.create_table(
        "monitoring_snapshots",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=71), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=False),
        sa.Column("schedule_json", sa.JSON(), nullable=False),
        sa.Column("health_label", sa.String(length=24), nullable=False),
        sa.Column("health_json", sa.JSON(), nullable=False),
        sa.Column("detections_json", sa.JSON(), nullable=False),
        sa.Column("calculation_versions", sa.JSON(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "health_label IN ('Completed', 'On track', 'At risk', 'Delayed', 'Insufficient data')",
            name=op.f("ck_monitoring_snapshots_health_label_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_monitoring_snapshots_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_monitoring_snapshots_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitoring_snapshots")),
        sa.UniqueConstraint(
            "version_id",
            "state_hash",
            name="monitoring_version_state_hash",
        ),
    )
    op.create_index(
        "ix_monitoring_project_calculated",
        "monitoring_snapshots",
        ["project_id", "calculated_at"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_version_calculated",
        "monitoring_snapshots",
        ["version_id", "calculated_at"],
        unique=False,
    )


def _extend_job_types() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("workflow_allowed", type_="check")
        batch.create_check_constraint(
            "workflow_allowed",
            "workflow IN ('planning', 'monitoring')",
        )
    with op.batch_alter_table("agent_jobs") as batch:
        batch.drop_constraint("job_type_allowed", type_="check")
        batch.create_check_constraint(
            "job_type_allowed",
            "job_type IN ('planning', 'monitoring')",
        )


def _restrict_job_types() -> None:
    with op.batch_alter_table("agent_jobs") as batch:
        batch.drop_constraint("job_type_allowed", type_="check")
        batch.create_check_constraint("job_type_allowed", "job_type = 'planning'")
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("workflow_allowed", type_="check")
        batch.create_check_constraint("workflow_allowed", "workflow = 'planning'")


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    tables = ("task_status_events", "progress_updates", "monitoring_snapshots")
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_execution_history_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'execution history is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in tables:
            op.execute(
                f"""
                CREATE TRIGGER {table}_append_only
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_execution_history_mutation()
                """
            )
    elif dialect == "sqlite":
        for table in tables:
            for operation in ("update", "delete"):
                op.execute(
                    f"""
                    CREATE TRIGGER {table}_reject_{operation}
                    BEFORE {operation.upper()} ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, 'execution history is append-only');
                    END
                    """
                )


def _drop_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    tables = ("task_status_events", "progress_updates", "monitoring_snapshots")
    if dialect == "postgresql":
        for table in tables:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_execution_history_mutation()")
    elif dialect == "sqlite":
        for table in tables:
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {table}_reject_{operation}")
