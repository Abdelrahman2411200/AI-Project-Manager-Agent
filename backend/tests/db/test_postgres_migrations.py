import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


@pytest.mark.postgres
def test_postgres_migrations_create_current_constraints() -> None:
    admin_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not configured")
    database_name = f"phase2_test_{uuid4().hex[:10]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    test_url = make_url(admin_url).set(database=database_name)
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        os.environ["ALEMBIC_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.check(config)
        test_engine = create_engine(test_url)
        try:
            inspector = inspect(test_engine)
            assert {
                "users",
                "sessions",
                "projects",
                "project_requirements",
                "project_constraints",
                "work_calendars",
                "audit_events",
                "prompt_versions",
                "provider_usage",
                "agent_runs",
                "agent_run_steps",
                "agent_jobs",
                "plan_versions",
                "project_analyses",
                "clarification_questions",
                "planning_decisions",
                "milestones",
                "tasks",
                "task_dependencies",
                "risks",
                "plan_approvals",
            }.issubset(inspector.get_table_names())
            project_checks = {item["name"] for item in inspector.get_check_constraints("projects")}
            assert "ck_projects_capacity_range" in project_checks
            session_indexes = {item["name"] for item in inspector.get_indexes("sessions")}
            assert "ix_sessions_token_hash_unique" in session_indexes
            with test_engine.begin() as connection:
                audit_trigger = connection.scalar(
                    text(
                        "SELECT trigger_name FROM information_schema.triggers "
                        "WHERE event_object_table = 'audit_events' "
                        "AND trigger_name = 'audit_events_append_only'"
                    )
                )
            assert audit_trigger == "audit_events_append_only"
            with test_engine.begin() as connection:
                phase_four_triggers = set(
                    connection.scalars(
                        text(
                            "SELECT trigger_name FROM information_schema.triggers "
                            "WHERE event_object_table IN ('prompt_versions', 'provider_usage')"
                        )
                    )
                )
            assert {
                "prompt_versions_immutable",
                "provider_usage_append_only",
            }.issubset(phase_four_triggers)
            step_indexes = {item["name"] for item in inspector.get_indexes("agent_run_steps")}
            assert "ix_agent_run_steps_input" in step_indexes
            dependency_foreign_keys = {
                item["name"] for item in inspector.get_foreign_keys("task_dependencies")
            }
            assert {
                "dependency_predecessor_same_version",
                "dependency_successor_same_version",
            }.issubset(dependency_foreign_keys)
            plan_indexes = {item["name"]: item for item in inspector.get_indexes("plan_versions")}
            assert plan_indexes["uq_plan_versions_one_active_per_project"]["unique"]
            with test_engine.begin() as connection:
                phase_six_triggers = set(
                    connection.scalars(
                        text(
                            "SELECT trigger_name FROM information_schema.triggers "
                            "WHERE event_object_table IN "
                            "('plan_approvals','plan_versions','milestones','tasks',"
                            "'task_dependencies','project_analyses','risks')"
                        )
                    )
                )
            assert {
                "plan_approvals_append_only",
                "plan_versions_frozen_metadata",
                "milestones_frozen_content",
                "tasks_frozen_content",
                "task_dependencies_frozen_content",
                "project_analyses_frozen_content",
                "risks_frozen_content",
            }.issubset(phase_six_triggers)
        finally:
            test_engine.dispose()
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()
