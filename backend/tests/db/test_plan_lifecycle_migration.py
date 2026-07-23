import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def test_sqlite_lifecycle_migration_enforces_immutability_and_one_active(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase6.sqlite"
    database_url = f"sqlite:///{database_path}"
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)

    engine = create_engine(database_url)
    user_id = uuid4().hex
    project_id = uuid4().hex
    first_id = uuid4().hex
    second_id = uuid4().hex
    milestone_id = uuid4().hex
    approval_id = uuid4().hex
    now = "2026-07-23 16:00:00"
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                "INSERT INTO users "
                "(email,password_hash,status,id,created_at,updated_at) "
                "VALUES (:email,:password_hash,'active',:id,:now,:now)"
            ),
            {"email": "migration@example.com", "password_hash": "x", "id": user_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO projects "
                "(owner_id,name,goal,desired_outcome,start_date,deadline,timezone,"
                "capacity_hours_per_week,team_size,status,notes,row_version,id,"
                "created_at,updated_at) "
                "VALUES (:owner,'Project','Goal',NULL,NULL,NULL,'UTC',40,1,'active',NULL,1,"
                ":id,:now,:now)"
            ),
            {"owner": user_id, "id": project_id, "now": now},
        )
        for number, plan_id in ((1, first_id), (2, second_id)):
            connection.execute(
                text(
                    "INSERT INTO plan_versions "
                    "(project_id,number,state,based_on_id,reason,content_hash,quality_status,"
                    "quality_report,source_run_id,row_version,id,created_at,updated_at) "
                    "VALUES (:project,:number,'draft',NULL,'Draft',:hash,'passed',"
                    ":quality,:run,1,:id,:now,:now)"
                ),
                {
                    "project": project_id,
                    "number": number,
                    "hash": f"sha256:{str(number) * 64}",
                    "run": uuid4().hex,
                    "id": plan_id,
                    "now": now,
                    "quality": '{"passed":true}',
                },
            )
        connection.execute(
            text(
                "INSERT INTO milestones "
                "(version_id,stable_key,module_refs,name,description,objective,deliverable,"
                "sequence,target_date,planned_effort_hours,acceptance_criteria,planned_start,"
                "planned_finish,status,id,created_at,updated_at,source,protected,locked,"
                "row_version) "
                "VALUES (:version,'MS-001','[]','Milestone','A sufficiently detailed description',"
                "'A clear milestone objective','Deliverable',1,NULL,4,'[\"Done\"]',NULL,NULL,"
                "'pending',:id,:now,:now,'ai',0,0,1)"
            ),
            {"version": first_id, "id": milestone_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO plan_approvals "
                "(project_id,version_id,actor_id,decision,reason,content_hash,id) "
                "VALUES (:project,:version,:actor,'approved',NULL,:hash,:id)"
            ),
            {
                "project": project_id,
                "version": first_id,
                "actor": user_id,
                "hash": f"sha256:{'1' * 64}",
                "id": approval_id,
            },
        )
        connection.execute(
            text("UPDATE plan_versions SET state='under_review' WHERE id=:id"),
            {"id": first_id},
        )

    with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE plan_approvals SET reason='changed' WHERE id=:id"),
            {"id": approval_id},
        )
    with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
        connection.execute(
            text("UPDATE milestones SET name='Changed' WHERE id=:id"),
            {"id": milestone_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text("UPDATE plan_versions SET state='active' WHERE id IN (:first,:second)"),
            {"first": first_id, "second": second_id},
        )
    engine.dispose()
