from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cli.verify_restore import verify_restore
from app.db.session import engine


def test_restore_verifier_checks_schema_invariants_and_report_hashes() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
    with Session(engine) as session:
        result = verify_restore(session)
    assert result.passed
    assert result.missing_tables == ()
    assert result.active_version_duplicates == 0
    assert result.invalid_report_hashes == 0
