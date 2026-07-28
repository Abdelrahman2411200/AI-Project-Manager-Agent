from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.cli.demo_reset import CONFIRMATION, assert_demo_reset_allowed
from app.db.models.advanced import RegenerationProposal, Scenario
from app.db.models.execution import MonitoringSnapshot
from app.db.models.insight import Recommendation, RecommendationEvidence, Report
from app.db.models.plan import PlanVersion, ProjectAnalysis, Task, TaskDependency
from app.db.models.project import Project
from app.db.models.prompt import ProviderUsage
from app.db.models.run import AgentRun
from app.db.session import SessionLocal, engine
from app.demo.seed import (
    DEMO_EMAIL,
    DEMO_FIXTURE_NAMES,
    load_demo_fixtures,
    reset_and_seed_demo,
)
from app.schemas.insight import FactualReportData
from app.services.plan_content import persisted_content_hash

FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
DEMO_PASSWORD = "SyntheticDemoOnly!2026"


def test_fixture_catalog_is_exact_complete_and_safe() -> None:
    fixtures = load_demo_fixtures(FIXTURE_DIRECTORY)

    assert tuple(item["slug"] for item in fixtures) == DEMO_FIXTURE_NAMES
    assert sum(bool(item["main_demo"]) for item in fixtures) == 1
    serialized = repr(fixtures).casefold()
    assert "openai_api_key" not in serialized
    assert "gho_" not in serialized
    assert "@example.com" not in serialized


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_demo_reset_guard_rejects_non_demo_environments(app_env: str) -> None:
    with pytest.raises(RuntimeError, match="APP_ENV"):
        assert_demo_reset_allowed(
            app_env=app_env,
            database_url="postgresql+psycopg://user:secret@db/project_manager_demo",
            confirmation=CONFIRMATION,
        )


def test_demo_reset_guard_requires_confirmation_and_demo_database() -> None:
    with pytest.raises(RuntimeError, match="--confirm"):
        assert_demo_reset_allowed(
            app_env="demo",
            database_url="postgresql+psycopg://user:secret@db/project_manager_demo",
            confirmation="no",
        )
    with pytest.raises(RuntimeError, match="contain 'demo'"):
        assert_demo_reset_allowed(
            app_env="development",
            database_url="postgresql+psycopg://user:secret@db/project_manager",
            confirmation=CONFIRMATION,
        )
    assert_demo_reset_allowed(
        app_env="demo",
        database_url="postgresql+psycopg://user:secret@db/project_manager_demo",
        confirmation=CONFIRMATION,
    )


def test_seed_creates_full_persisted_university_package_and_survives_reload() -> None:
    summary = reset_and_seed_demo(
        engine,
        password=DEMO_PASSWORD,
        fixture_directory=FIXTURE_DIRECTORY,
    )
    assert summary.owner_email == DEMO_EMAIL
    assert summary.fixture_count == 8
    assert set(summary.project_ids) == set(DEMO_FIXTURE_NAMES)
    assert set(summary.retained_draft_ids) == set(DEMO_FIXTURE_NAMES)

    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 8
        assert (
            session.scalar(
                select(func.count()).select_from(PlanVersion).where(PlanVersion.state == "active")
            )
            == 8
        )
        assert (
            session.scalar(
                select(func.count()).select_from(PlanVersion).where(PlanVersion.state == "draft")
            )
            == 8
        )
        assert session.scalar(select(func.count()).select_from(Report)) == 8
        assert session.scalar(select(func.count()).select_from(Recommendation)) >= 8
        assert session.scalar(select(func.count()).select_from(RecommendationEvidence)) >= 8
        assert session.scalar(select(func.count()).select_from(ProviderUsage)) == 0

        for slug, plan_id in summary.active_plan_ids.items():
            plan = session.get(PlanVersion, plan_id)
            assert plan is not None, slug
            assert plan.content_hash == persisted_content_hash(session, plan), slug
            retained_draft = session.scalar(
                select(PlanVersion).where(
                    PlanVersion.project_id == plan.project_id,
                    PlanVersion.state == "draft",
                )
            )
            assert retained_draft is not None, slug
            assert retained_draft.id == summary.retained_draft_ids[slug], slug
            assert retained_draft.based_on_id == plan.id, slug
            assert retained_draft.content_hash == persisted_content_hash(session, retained_draft), (
                slug
            )
            snapshot = session.scalar(
                select(MonitoringSnapshot).where(MonitoringSnapshot.version_id == plan.id)
            )
            assert snapshot is not None, slug
            report = session.get(Report, summary.report_ids[slug])
            assert report is not None, slug
            factual = FactualReportData.model_validate(report.data_json)
            assert factual.state_hash == snapshot.state_hash
            assert report.content_hash.startswith("sha256:")
            assert "Evidence index" in report.markdown

        commerce_id = summary.project_ids["ecommerce_six_weeks"]
        commerce = session.get(Project, commerce_id)
        assert commerce is not None
        assert commerce.team_size == 3
        assert str(commerce.capacity_hours_per_week) == "120.00"
        assert commerce.timezone == "Africa/Cairo"
        commerce_plan = session.get(
            PlanVersion,
            summary.active_plan_ids["ecommerce_six_weeks"],
        )
        assert commerce_plan is not None
        analysis = session.scalar(
            select(ProjectAnalysis).where(ProjectAnalysis.version_id == commerce_plan.id)
        )
        assert analysis is not None
        assert "shoppers and an administrator" in analysis.summary
        assert analysis.excluded_scope == ["Marketplace", "Native mobile applications"]
        tasks = {
            item.stable_key: item
            for item in session.scalars(select(Task).where(Task.version_id == commerce_plan.id))
        }
        assert len(tasks) == 14
        assert tasks["TASK-003"].locked is True
        assert tasks["TASK-003"].protected is True
        assert tasks["TASK-003"].source == "user"
        assert tasks["TASK-014"].title == "Persist idempotent checkout result"
        assert tasks["TASK-014"].effort_likely_hours == 16
        commerce_draft = session.scalar(
            select(PlanVersion).where(
                PlanVersion.project_id == commerce.id,
                PlanVersion.state == "draft",
            )
        )
        assert commerce_draft is not None
        draft_tasks = {
            item.stable_key: item
            for item in session.scalars(select(Task).where(Task.version_id == commerce_draft.id))
        }
        assert draft_tasks["TASK-003"].title == tasks["TASK-003"].title
        assert draft_tasks["TASK-003"].description == tasks["TASK-003"].description
        assert draft_tasks["TASK-003"].locked is True
        assert draft_tasks["TASK-003"].protected is True
        scenario = session.scalar(select(Scenario).where(Scenario.project_id == commerce.id))
        assert scenario is not None
        assert scenario.baseline_version_id == commerce_plan.id
        assert scenario.baseline_content_hash == commerce_plan.content_hash
        assert scenario.status == "completed"
        assert scenario.result_json["sources"]["baseline_content_hash"] == (
            commerce_plan.content_hash
        )
        proposal = session.scalar(
            select(RegenerationProposal).where(RegenerationProposal.project_id == commerce.id)
        )
        assert proposal is not None
        assert proposal.version_id == commerce_draft.id
        assert proposal.baseline_content_hash == commerce_draft.content_hash
        assert proposal.status == "pending"
        assert proposal.selection_json == [
            {
                "entity_type": "task",
                "stable_key": "TASK-012",
                "fields": ["title"],
            }
        ]
        assert proposal.diff_json
        assert commerce_plan.content_hash == persisted_content_hash(session, commerce_plan)
        dependency = session.scalar(
            select(TaskDependency).where(
                TaskDependency.version_id == commerce_plan.id,
                TaskDependency.predecessor_id == tasks["TASK-011"].id,
                TaskDependency.successor_id == tasks["TASK-014"].id,
            )
        )
        assert dependency is not None
        commerce_snapshot = session.scalar(
            select(MonitoringSnapshot).where(MonitoringSnapshot.version_id == commerce_plan.id)
        )
        assert commerce_snapshot is not None
        assert commerce_snapshot.health_label == "At risk"
        assert any(
            code in commerce_snapshot.health_json["rule_codes"]
            for code in ("BLOCKED_CRITICAL_TASK", "BLOCKED_EFFORT_THRESHOLD")
        ), commerce_snapshot.health_json

        impossible_plan = session.get(
            PlanVersion,
            summary.active_plan_ids["impossible_deadline"],
        )
        assert impossible_plan is not None
        impossible_snapshot = session.scalar(
            select(MonitoringSnapshot).where(MonitoringSnapshot.version_id == impossible_plan.id)
        )
        assert impossible_snapshot is not None
        assert impossible_snapshot.schedule_json["deadline_feasible"] is False

        planning_runs = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.workflow == "planning",
                    AgentRun.status == "completed",
                )
            )
        )
        assert len(planning_runs) == 16
        assert all(run.state_snapshot["completed_steps"] for run in planning_runs)
