"""add scenarios, regeneration proposals, and normalized risk relations

Revision ID: 0009_advanced_intelligence
Revises: 0008_monitoring_reporting
Create Date: 2026-07-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_advanced_intelligence"
down_revision: str | None = "0008_monitoring_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("risks") as batch_op:
        batch_op.create_unique_constraint(
            "risk_id_version",
            ["id", "version_id"],
        )
    op.create_table(
        "scenarios",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_version_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("baseline_content_hash", sa.String(length=71), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("overrides_json", JSON_DOCUMENT, nullable=False),
        sa.Column("result_json", JSON_DOCUMENT, nullable=False),
        sa.Column("explanation_json", JSON_DOCUMENT, nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("calculation_version", sa.String(length=48), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'explanation_failed')",
            name=op.f("ck_scenarios_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["baseline_version_id"],
            ["plan_versions.id"],
            name=op.f("fk_scenarios_baseline_version_id_plan_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_scenarios_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_scenarios_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenarios")),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="scenario_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_scenarios_project_created",
        "scenarios",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_scenarios_baseline_created",
        "scenarios",
        ["baseline_version_id", "created_at"],
    )

    op.create_table(
        "regeneration_proposals",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=71), nullable=False),
        sa.Column("baseline_content_hash", sa.String(length=71), nullable=False),
        sa.Column("selection_json", JSON_DOCUMENT, nullable=False),
        sa.Column("replacements_json", JSON_DOCUMENT, nullable=False),
        sa.Column("diff_json", JSON_DOCUMENT, nullable=False),
        sa.Column("impact_json", JSON_DOCUMENT, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'stale')",
            name=op.f("ck_regeneration_proposals_status_allowed"),
        ),
        sa.CheckConstraint(
            "row_version >= 1",
            name=op.f("ck_regeneration_proposals_row_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_regeneration_proposals_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_regeneration_proposals_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["plan_versions.id"],
            name=op.f("fk_regeneration_proposals_version_id_plan_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regeneration_proposals")),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="regeneration_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_regeneration_version_created",
        "regeneration_proposals",
        ["version_id", "created_at"],
    )
    op.create_index(
        "ix_regeneration_project_status",
        "regeneration_proposals",
        ["project_id", "status"],
    )

    op.create_table(
        "risk_relations",
        sa.Column("risk_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_ref", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('task', 'milestone', 'dependency', 'requirement')",
            name=op.f("ck_risk_relations_entity_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["risk_id", "version_id"],
            ["risks.id", "risks.version_id"],
            name="risk_relation_same_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_relations")),
        sa.UniqueConstraint(
            "version_id",
            "risk_id",
            "entity_type",
            "entity_ref",
            name="risk_relation_target",
        ),
    )
    op.create_index("ix_risk_relations_risk", "risk_relations", ["risk_id"])
    op.create_index(
        "ix_risk_relations_entity",
        "risk_relations",
        ["entity_type", "entity_ref"],
    )
    _create_scenario_triggers()


def downgrade() -> None:
    _drop_scenario_triggers()
    op.drop_index("ix_risk_relations_entity", table_name="risk_relations")
    op.drop_index("ix_risk_relations_risk", table_name="risk_relations")
    op.drop_table("risk_relations")
    with op.batch_alter_table("risks") as batch_op:
        batch_op.drop_constraint("risk_id_version", type_="unique")
    op.drop_index("ix_regeneration_project_status", table_name="regeneration_proposals")
    op.drop_index("ix_regeneration_version_created", table_name="regeneration_proposals")
    op.drop_table("regeneration_proposals")
    op.drop_index("ix_scenarios_baseline_created", table_name="scenarios")
    op.drop_index("ix_scenarios_project_created", table_name="scenarios")
    op.drop_table("scenarios")


def _create_scenario_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER scenarios_reject_{operation.lower()}
                BEFORE {operation} ON scenarios
                BEGIN
                  SELECT RAISE(ABORT, 'scenarios are append-only');
                END;
                """
            )
        return
    if dialect != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION prevent_scenario_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'scenarios are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER scenarios_append_only
        BEFORE UPDATE OR DELETE ON scenarios
        FOR EACH ROW EXECUTE FUNCTION prevent_scenario_mutation();
        """
    )


def _drop_scenario_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS scenarios_reject_update")
        op.execute("DROP TRIGGER IF EXISTS scenarios_reject_delete")
        return
    if dialect != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS scenarios_append_only ON scenarios")
    op.execute("DROP FUNCTION IF EXISTS prevent_scenario_mutation()")
