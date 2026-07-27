"""Persisted full-version intelligence artifacts.

Scenarios are immutable virtual calculations. Regeneration proposals are mutable
only until an owner approves or rejects them; approval applies to a draft through
the service layer and never provides an active-plan write path.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'explanation_failed')",
            name="status_allowed",
        ),
        UniqueConstraint("owner_id", "idempotency_key", name="scenario_owner_idempotency"),
        Index("ix_scenarios_project_created", "project_id", "created_at"),
        Index("ix_scenarios_baseline_created", "baseline_version_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    baseline_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    baseline_content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    overrides_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    explanation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(48), nullable=False)


class RegenerationProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "regeneration_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'stale')",
            name="status_allowed",
        ),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="regeneration_owner_idempotency",
        ),
        Index("ix_regeneration_version_created", "version_id", "created_at"),
        Index("ix_regeneration_project_status", "project_id", "status"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    baseline_content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    selection_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    replacements_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    diff_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    impact_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {  # noqa: RUF012
        "version_id_col": row_version,
        "version_id_generator": lambda version: (version or 0) + 1,
    }


class RiskRelation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "risk_relations"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('task', 'milestone', 'dependency', 'requirement')",
            name="entity_type_allowed",
        ),
        UniqueConstraint(
            "version_id",
            "risk_id",
            "entity_type",
            "entity_ref",
            name="risk_relation_target",
        ),
        ForeignKeyConstraint(
            ["risk_id", "version_id"],
            ["risks.id", "risks.version_id"],
            name="risk_relation_same_version",
            ondelete="CASCADE",
        ),
        Index("ix_risk_relations_risk", "risk_id"),
        Index("ix_risk_relations_entity", "entity_type", "entity_ref"),
    )

    risk_id: Mapped[UUID] = mapped_column(nullable=False)
    version_id: Mapped[UUID] = mapped_column(nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(80), nullable=False)


@event.listens_for(Scenario, "before_update")
@event.listens_for(Scenario, "before_delete")
def _prevent_scenario_mutation(*_: object) -> None:
    raise ValueError("Scenarios are immutable virtual calculation records.")
