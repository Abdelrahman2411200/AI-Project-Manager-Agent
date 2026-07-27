import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_sqlite_phase11_schema_constraints_triggers_and_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase11.sqlite'}"
    config = Config("alembic.ini")
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        schema = inspect(engine)
        assert {
            "scenarios",
            "regeneration_proposals",
            "risk_relations",
        } <= set(schema.get_table_names())
        assert {
            "ix_scenarios_project_created",
            "ix_scenarios_baseline_created",
        } <= {item["name"] for item in schema.get_indexes("scenarios")}
        assert {
            "risk_relation_same_version",
        } <= {item["name"] for item in schema.get_foreign_keys("risk_relations")}
        risk_uniques = {item["name"] for item in schema.get_unique_constraints("risks")}
        assert "risk_id_version" in risk_uniques
        with engine.connect() as connection:
            triggers = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='trigger' AND name LIKE 'scenarios_reject_%'"
                    )
                ).scalars()
            )
        assert triggers == {"scenarios_reject_update", "scenarios_reject_delete"}
        engine.dispose()

        command.downgrade(config, "0008_monitoring_reporting")
        downgraded = create_engine(database_url)
        assert "scenarios" not in inspect(downgraded).get_table_names()
        downgraded.dispose()
        command.upgrade(config, "head")
        upgraded = create_engine(database_url)
        assert "scenarios" in inspect(upgraded).get_table_names()
        upgraded.dispose()
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)
