import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_sqlite_active_execution_migration_is_complete_and_reversible(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8.sqlite"
    database_url = f"sqlite:///{database_path}"
    config = Config("alembic.ini")
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        schema = inspect(engine)
        assert {
            "task_execution_projections",
            "task_status_events",
            "progress_updates",
            "monitoring_snapshots",
        }.issubset(schema.get_table_names())
        assert {index["name"] for index in schema.get_indexes("task_execution_projections")} >= {
            "ix_task_execution_project_version_status",
            "ix_task_execution_version_changed",
        }
        with engine.connect() as connection:
            trigger_names = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE :pattern"
                    ),
                    {"pattern": "%_reject_%"},
                ).scalars()
            )
        assert trigger_names >= {
            "task_status_events_reject_update",
            "task_status_events_reject_delete",
            "progress_updates_reject_update",
            "progress_updates_reject_delete",
            "monitoring_snapshots_reject_update",
            "monitoring_snapshots_reject_delete",
        }
        engine.dispose()

        command.downgrade(config, "0006_plan_lifecycle")
        downgraded = create_engine(database_url)
        assert "task_execution_projections" not in inspect(downgraded).get_table_names()
        downgraded.dispose()

        command.upgrade(config, "head")
        upgraded = create_engine(database_url)
        assert "monitoring_snapshots" in inspect(upgraded).get_table_names()
        upgraded.dispose()
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)
