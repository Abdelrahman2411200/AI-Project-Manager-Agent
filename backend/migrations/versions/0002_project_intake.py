"""Create project intake entities.

Revision ID: 0002_project_intake
Revises: 0001_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_project_intake"
down_revision: str | None = "0001_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("capacity_hours_per_week", sa.Numeric(8, 2), nullable=False, server_default="40"),
        sa.Column("team_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="status_allowed"),
        sa.CheckConstraint("team_size >= 1 AND team_size <= 100", name="team_size_range"),
        sa.CheckConstraint(
            "capacity_hours_per_week > 0 AND capacity_hours_per_week <= 168",
            name="capacity_range",
        ),
        sa.CheckConstraint(
            "deadline IS NULL OR start_date IS NULL OR deadline >= start_date",
            name="dates_ordered",
        ),
        sa.CheckConstraint("row_version >= 1", name="row_version_positive"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_projects_owner_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index(
        "ix_projects_owner_status_updated", "projects", ["owner_id", "status", "updated_at"]
    )
    op.create_table(
        "project_requirements",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "kind IN ('stated', 'suggestion', 'confirmed', 'excluded')",
            name="kind_allowed",
        ),
        sa.CheckConstraint(
            "source IN ('user', 'agent', 'system')",
            name="source_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'confirmed', 'rejected')",
            name="status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_requirements_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_requirements"),
        sa.UniqueConstraint(
            "project_id",
            "normalized_text",
            "kind",
            name="uq_project_requirements_project_text_kind",
        ),
    )
    op.create_index(
        "ix_project_requirements_project_kind", "project_requirements", ["project_id", "kind"]
    )
    op.create_table(
        "project_constraints",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("constraint_type", sa.String(length=64), nullable=False),
        sa.Column("value_json", json_document, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "source IN ('user', 'agent', 'system')",
            name="source_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_constraints_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_constraints"),
    )
    op.create_index("ix_project_constraints_project", "project_constraints", ["project_id"])
    op.create_table(
        "work_calendars",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("weekday_hours", json_document, nullable=False),
        sa.Column("holidays", json_document, nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("parallel_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "parallel_limit >= 1 AND parallel_limit <= 100",
            name="parallel_limit_range",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="effective_dates_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_work_calendars_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_work_calendars"),
    )
    op.create_index(
        "ix_work_calendars_project_effective", "work_calendars", ["project_id", "effective_from"]
    )


def downgrade() -> None:
    op.drop_table("work_calendars")
    op.drop_table("project_constraints")
    op.drop_table("project_requirements")
    op.drop_table("projects")
