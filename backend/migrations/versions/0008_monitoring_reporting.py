"""add grounded recommendations, factual reports, and product telemetry

Revision ID: 0008_monitoring_reporting
Revises: 0007_active_execution
Create Date: 2026-07-23 23:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_monitoring_reporting"
down_revision: str | None = "0007_active_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _extend_run_types()
    _create_recommendations()
    _create_reports()
    _create_product_metrics()
    _create_append_only_triggers()


def downgrade() -> None:
    _drop_append_only_triggers()
    op.drop_index("ix_product_metrics_run_occurred", table_name="product_metric_events")
    op.drop_index("ix_product_metrics_project_occurred", table_name="product_metric_events")
    op.drop_index("ix_product_metrics_name_occurred", table_name="product_metric_events")
    op.drop_table("product_metric_events")
    op.drop_index("ix_reports_version_period", table_name="reports")
    op.drop_index("ix_reports_project_type_created", table_name="reports")
    op.drop_table("reports")
    op.drop_index(
        "ix_recommendation_decisions_recommendation_occurred",
        table_name="recommendation_decisions",
    )
    op.drop_table("recommendation_decisions")
    op.drop_index(
        "ix_recommendation_evidence_recommendation",
        table_name="recommendation_evidence",
    )
    op.drop_table("recommendation_evidence")
    op.drop_index("ix_recommendations_version_created", table_name="recommendations")
    op.drop_index(
        "ix_recommendations_project_state_urgency",
        table_name="recommendations",
    )
    op.drop_index("uq_recommendations_open_input", table_name="recommendations")
    op.drop_table("recommendations")
    _restrict_run_types()


def _create_recommendations() -> None:
    op.create_table(
        "recommendations",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=32), nullable=False),
        sa.Column("detection_code", sa.String(length=80), nullable=False),
        sa.Column("why_it_matters", sa.String(length=1000), nullable=False),
        sa.Column("suggested_action", sa.String(length=1000), nullable=False),
        sa.Column("expected_impact", sa.String(length=1000), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("risk", sa.String(length=500), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("verification_step", sa.String(length=1000), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("explanation_source", sa.String(length=16), nullable=False),
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
            "recommendation_type IN ('dependency_warning', 'schedule_warning', "
            "'scope_warning', 'risk_mitigation', 'priority_adjustment', 'next_action')",
            name=op.f("ck_recommendations_type_allowed"),
        ),
        sa.CheckConstraint(
            "state IN ('open', 'accepted', 'dismissed', 'deferred')",
            name=op.f("ck_recommendations_state_allowed"),
        ),
        sa.CheckConstraint(
            "urgency IN ('low', 'medium', 'high', 'immediate')",
            name=op.f("ck_recommendations_urgency_allowed"),
        ),
        sa.CheckConstraint(
            "explanation_source IN ('deterministic', 'ai')",
            name=op.f("ck_recommendations_explanation_source_allowed"),
        ),
        sa.CheckConstraint(
            "row_version >= 1",
            name=op.f("ck_recommendations_row_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["monitoring_snapshots.id"],
            name=op.f("fk_recommendations_snapshot_id_monitoring_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_recommendations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_recommendations_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
    )
    open_condition = sa.text("state IN ('open', 'deferred')")
    op.create_index(
        "uq_recommendations_open_input",
        "recommendations",
        ["project_id", "recommendation_type", "input_hash"],
        unique=True,
        sqlite_where=open_condition,
        postgresql_where=open_condition,
    )
    op.create_index(
        "ix_recommendations_project_state_urgency",
        "recommendations",
        ["project_id", "state", "urgency"],
        unique=False,
    )
    op.create_index(
        "ix_recommendations_version_created",
        "recommendations",
        ["version_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "recommendation_evidence",
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_ref", sa.String(length=80), nullable=False),
        sa.Column("fact_key", sa.String(length=80), nullable=False),
        sa.Column("fact_value", sa.JSON(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('task', 'milestone', 'dependency', 'metric', 'forecast', "
            "'detection', 'event', 'project')",
            name=op.f("ck_recommendation_evidence_entity_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name=op.f("fk_recommendation_evidence_recommendation_id_recommendations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_evidence")),
        sa.UniqueConstraint(
            "recommendation_id",
            "entity_type",
            "entity_ref",
            "fact_key",
            name="recommendation_evidence_fact",
        ),
    )
    op.create_index(
        "ix_recommendation_evidence_recommendation",
        "recommendation_evidence",
        ["recommendation_id"],
        unique=False,
    )
    op.create_table(
        "recommendation_decisions",
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("defer_until", sa.Date(), nullable=True),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accept', 'dismiss', 'defer')",
            name=op.f("ck_recommendation_decisions_decision_allowed"),
        ),
        sa.CheckConstraint(
            "(decision = 'defer' AND defer_until IS NOT NULL) OR "
            "(decision <> 'defer' AND defer_until IS NULL)",
            name=op.f("ck_recommendation_decisions_defer_date_required"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_recommendation_decisions_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name=op.f("fk_recommendation_decisions_recommendation_id_recommendations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_decisions")),
        sa.UniqueConstraint(
            "event_key",
            name="recommendation_decision_event_key",
        ),
    )
    op.create_index(
        "ix_recommendation_decisions_recommendation_occurred",
        "recommendation_decisions",
        ["recommendation_id", "occurred_at"],
        unique=False,
    )


def _create_reports() -> None:
    op.create_table(
        "reports",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("narrative_json", sa.JSON(), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("state_hash", sa.String(length=71), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("narrative_failure_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "report_type IN ('weekly', 'project', 'milestone', 'risk', 'comparison')",
            name=op.f("ck_reports_type_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'partial')",
            name=op.f("ck_reports_status_allowed"),
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name=op.f("ck_reports_period_order"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_reports_run_id_agent_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_reports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_reports_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint(
            "project_id",
            "input_hash",
            name="report_project_input",
        ),
    )
    op.create_index(
        "ix_reports_project_type_created",
        "reports",
        ["project_id", "report_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reports_version_period",
        "reports",
        ["version_id", "period_start", "period_end"],
        unique=False,
    )


def _create_product_metrics() -> None:
    op.create_table(
        "product_metric_events",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_hash", sa.String(length=80), nullable=False),
        sa.Column("safe_attributes", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_product_metric_events_duration_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_product_metric_events_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_product_metric_events_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_metric_events")),
    )
    op.create_index(
        "ix_product_metrics_name_occurred",
        "product_metric_events",
        ["name", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_metrics_project_occurred",
        "product_metric_events",
        ["project_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_metrics_run_occurred",
        "product_metric_events",
        ["run_id", "occurred_at"],
        unique=False,
    )


def _extend_run_types() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("workflow_allowed", type_="check")
        batch.create_check_constraint(
            "workflow_allowed",
            "workflow IN ('planning', 'monitoring', 'reporting')",
        )
    with op.batch_alter_table("agent_jobs") as batch:
        batch.drop_constraint("job_type_allowed", type_="check")
        batch.create_check_constraint(
            "job_type_allowed",
            "job_type IN ('planning', 'monitoring', 'reporting')",
        )


def _restrict_run_types() -> None:
    with op.batch_alter_table("agent_jobs") as batch:
        batch.drop_constraint("job_type_allowed", type_="check")
        batch.create_check_constraint(
            "job_type_allowed",
            "job_type IN ('planning', 'monitoring')",
        )
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("workflow_allowed", type_="check")
        batch.create_check_constraint(
            "workflow_allowed",
            "workflow IN ('planning', 'monitoring')",
        )


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    tables = (
        "recommendation_evidence",
        "recommendation_decisions",
        "reports",
        "product_metric_events",
    )
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_insight_history_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'insight history is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in tables:
            op.execute(
                f"""
                CREATE TRIGGER {table}_append_only
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_insight_history_mutation()
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
                        SELECT RAISE(ABORT, 'insight history is append-only');
                    END
                    """
                )


def _drop_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    tables = (
        "recommendation_evidence",
        "recommendation_decisions",
        "reports",
        "product_metric_events",
    )
    if dialect == "postgresql":
        for table in tables:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_insight_history_mutation()")
    elif dialect == "sqlite":
        for table in tables:
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {table}_reject_{operation}")
