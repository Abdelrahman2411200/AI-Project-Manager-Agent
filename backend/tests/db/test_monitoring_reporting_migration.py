import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_sqlite_phase9_schema_indexes_triggers_and_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase9.sqlite'}"
    config = Config("alembic.ini")
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        schema = inspect(engine)
        tables = set(schema.get_table_names())
        assert {
            "recommendations",
            "recommendation_evidence",
            "recommendation_decisions",
            "reports",
            "product_metric_events",
        } <= tables
        assert {
            "uq_recommendations_open_input",
            "ix_recommendations_project_state_urgency",
        } <= {item["name"] for item in schema.get_indexes("recommendations")}
        with engine.connect() as connection:
            triggers = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE :pattern"
                    ),
                    {"pattern": "%_reject_%"},
                ).scalars()
            )
        assert {
            f"{table}_reject_{operation}"
            for table in (
                "recommendation_evidence",
                "recommendation_decisions",
                "reports",
                "product_metric_events",
            )
            for operation in ("update", "delete")
        } <= triggers
        engine.dispose()

        command.downgrade(config, "0007_active_execution")
        downgraded = create_engine(database_url)
        assert "reports" not in inspect(downgraded).get_table_names()
        downgraded.dispose()
        command.upgrade(config, "head")
        upgraded = create_engine(database_url)
        assert "reports" in inspect(upgraded).get_table_names()
        upgraded.dispose()
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)
