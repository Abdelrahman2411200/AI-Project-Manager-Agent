"""Verify a restored database without mutating application data."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.orm import Session

from app.core.hashing import canonical_hash
from app.db.models.insight import Report
from app.db.models.plan import PlanVersion
from app.db.session import engine

REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "users",
        "projects",
        "plan_versions",
        "agent_runs",
        "agent_jobs",
        "reports",
        "audit_events",
        "provider_usage",
    }
)


@dataclass(frozen=True, slots=True)
class RestoreVerification:
    schema_ok: bool
    missing_tables: tuple[str, ...]
    active_version_duplicates: int
    sampled_report_hashes: int
    invalid_report_hashes: int
    row_counts: dict[str, int]

    @property
    def passed(self) -> bool:
        return (
            self.schema_ok
            and self.active_version_duplicates == 0
            and self.invalid_report_hashes == 0
        )


def verify_restore(session: Session) -> RestoreVerification:
    bind = session.get_bind()
    tables = set(inspect(bind).get_table_names())
    missing = tuple(sorted(REQUIRED_TABLES - tables))
    row_counts: dict[str, int] = {}
    metadata = MetaData()
    for table_name in sorted(REQUIRED_TABLES & tables):
        table = Table(table_name, metadata, autoload_with=bind)
        row_counts[table_name] = int(
            session.execute(select(func.count()).select_from(table)).scalar_one()
        )
    duplicate_groups = int(
        session.execute(
            select(func.count()).select_from(
                select(PlanVersion.project_id)
                .where(PlanVersion.state == "active")
                .group_by(PlanVersion.project_id)
                .having(func.count(PlanVersion.id) > 1)
                .subquery()
            )
        ).scalar_one()
    )
    reports = list(session.scalars(select(Report).order_by(Report.created_at.desc()).limit(20)))
    invalid_hashes = sum(
        canonical_hash(
            {
                "data": report.data_json,
                "narrative": report.narrative_json,
                "markdown": report.markdown,
            }
        )
        != report.content_hash
        for report in reports
    )
    return RestoreVerification(
        schema_ok=not missing,
        missing_tables=missing,
        active_version_duplicates=duplicate_groups,
        sampled_report_hashes=len(reports),
        invalid_report_hashes=invalid_hashes,
        row_counts=row_counts,
    )


def main() -> int:
    with Session(engine) as session:
        result = verify_restore(session)
    print(json.dumps({**asdict(result), "passed": result.passed}, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
