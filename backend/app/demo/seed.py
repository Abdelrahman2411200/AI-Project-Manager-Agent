"""Deterministic university fixtures backed by the persisted domain model.

The seed makes no provider calls. It creates safe synthetic records that remain
available through the normal API after a browser reload.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import hash_password
from app.core.hashing import canonical_hash
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.models.advanced import RegenerationProposal, Scenario
from app.db.models.audit import AuditEvent
from app.db.models.execution import (
    ProgressUpdate,
    TaskExecutionProjection,
    TaskStatusEvent,
)
from app.db.models.identity import User
from app.db.models.insight import RecommendationDecision
from app.db.models.plan import (
    ClarificationQuestion,
    Milestone,
    PlanApproval,
    PlanningDecision,
    PlanVersion,
    ProjectAnalysis,
    Risk,
    Task,
    TaskDependency,
)
from app.db.models.project import (
    Project,
    ProjectConstraint,
    ProjectRequirement,
    WorkCalendar,
)
from app.db.models.run import AgentRun, AgentRunStep
from app.domain.change_impact import summarize_comparison
from app.schemas.advanced import (
    RegenerationCreate,
    RegenerationReplacement,
    RegenerationTarget,
    ScenarioCreate,
    ScenarioOverrides,
)
from app.schemas.insight import ReportCreateRequest
from app.services.advanced import AdvancedIntelligenceService
from app.services.monitoring import MonitoringService
from app.services.plan_content import (
    persisted_content_hash,
    plan_content_snapshot,
)
from app.services.recommendations import RecommendationService
from app.services.reports import ReportService

DEMO_EMAIL = "demo.owner@example.com"
DEMO_REFERENCE_DATE = date(2026, 7, 28)
DEMO_NAMESPACE = UUID("4d2d8d58-e2f6-5b32-9f85-459b0991edcf")
DEMO_SCENARIO_ID = uuid5(
    DEMO_NAMESPACE,
    "ecommerce_six_weeks:scenario:capacity-and-deadline",
)
DEMO_REGENERATION_PROPOSAL_ID = uuid5(
    DEMO_NAMESPACE,
    "ecommerce_six_weeks:regeneration:checkout-title",
)
DEMO_FIXTURE_NAMES = (
    "ecommerce_six_weeks",
    "football_scouting_eight_weeks",
    "attendance_system",
    "expense_tracker_mobile",
    "marketing_site_small",
    "analytics_dashboard",
    "incident_investigator",
    "impossible_deadline",
)
FIXTURE_DIRECTORY = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "demo"


@dataclass(frozen=True, slots=True)
class DemoSeedSummary:
    owner_id: UUID
    owner_email: str
    fixture_count: int
    project_ids: dict[str, UUID]
    active_plan_ids: dict[str, UUID]
    retained_draft_ids: dict[str, UUID]
    report_ids: dict[str, UUID]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _id(*parts: object) -> UUID:
    return uuid5(DEMO_NAMESPACE, ":".join(str(part) for part in parts))


def load_demo_fixtures(directory: Path | None = None) -> list[dict[str, Any]]:
    root = directory or FIXTURE_DIRECTORY
    fixtures: list[dict[str, Any]] = []
    for name in DEMO_FIXTURE_NAMES:
        path = root / f"{name}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("slug") != name:
            raise ValueError(f"Demo fixture {path} must declare slug {name!r}.")
        required = {
            "name",
            "goal",
            "desired_outcome",
            "weeks",
            "team_size",
            "capacity_hours_per_week",
            "timezone",
            "requirements",
            "exclusions",
            "clarifications",
            "modules",
            "risk",
            "warning",
            "main_demo",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"Demo fixture {name} is missing: {', '.join(missing)}.")
        fixtures.append(payload)
    if len(fixtures) != 8 or len({item["slug"] for item in fixtures}) != 8:
        raise ValueError("The university demo requires exactly eight unique fixtures.")
    if sum(bool(item["main_demo"]) for item in fixtures) != 1:
        raise ValueError("Exactly one demo fixture must be marked as the main scenario.")
    return fixtures


def clear_demo_database(engine: Engine) -> None:
    """Delete all rows from a database already proven safe by the CLI guard."""

    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
            connection.exec_driver_sql(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
            return
        plan_versions = Base.metadata.tables.get("plan_versions")
        if plan_versions is not None:
            connection.execute(update(plan_versions).values(based_on_id=None))
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(delete(table))


def reset_and_seed_demo(
    engine: Engine,
    *,
    password: str,
    fixture_directory: Path | None = None,
) -> DemoSeedSummary:
    clear_demo_database(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        result = seed_demo_data(
            session,
            password=password,
            fixture_directory=fixture_directory,
        )
        session.commit()
        return result


def seed_demo_data(
    session: Session,
    *,
    password: str,
    fixture_directory: Path | None = None,
) -> DemoSeedSummary:
    if len(password) < 12:
        raise ValueError("The demo owner password must contain at least 12 characters.")
    if session.scalar(select(User).where(User.email == DEMO_EMAIL)) is not None:
        raise ValueError("Demo data already exists; use the guarded reset command.")

    owner = User(
        id=_id("owner"),
        email=DEMO_EMAIL,
        password_hash=hash_password(password),
        status="active",
    )
    session.add(owner)
    session.flush()

    project_ids: dict[str, UUID] = {}
    plan_ids: dict[str, UUID] = {}
    draft_ids: dict[str, UUID] = {}
    report_ids: dict[str, UUID] = {}
    for fixture in load_demo_fixtures(fixture_directory):
        project, plan, draft, report_id = _seed_fixture(session, owner, fixture)
        project_ids[fixture["slug"]] = project.id
        plan_ids[fixture["slug"]] = plan.id
        draft_ids[fixture["slug"]] = draft.id
        report_ids[fixture["slug"]] = report_id

    session.add(
        AuditEvent(
            id=_id("audit", "demo-package-seeded"),
            owner_id=owner.id,
            project_id=None,
            actor_type="system",
            actor_id=None,
            action="DemoPackageSeeded",
            entity_type="DemoPackage",
            entity_id=None,
            before_ref=None,
            after_ref={
                "fixtures": list(DEMO_FIXTURE_NAMES),
                "synthetic_data": True,
                "provider_calls": 0,
            },
            request_id="demo-reset",
            occurred_at=_at(day_offset=0, hour=12),
        )
    )
    session.flush()
    return DemoSeedSummary(
        owner_id=owner.id,
        owner_email=owner.email,
        fixture_count=len(project_ids),
        project_ids=project_ids,
        active_plan_ids=plan_ids,
        retained_draft_ids=draft_ids,
        report_ids=report_ids,
    )


def _seed_fixture(
    session: Session,
    owner: User,
    fixture: dict[str, Any],
) -> tuple[Project, PlanVersion, PlanVersion, UUID]:
    slug = str(fixture["slug"])
    weeks = int(fixture["weeks"])
    start_date = DEMO_REFERENCE_DATE - timedelta(days=22)
    deadline = start_date + timedelta(weeks=weeks) - timedelta(days=1)
    project = Project(
        id=_id(slug, "project"),
        owner_id=owner.id,
        name=str(fixture["name"]),
        goal=str(fixture["goal"]),
        desired_outcome=str(fixture["desired_outcome"]),
        start_date=start_date,
        deadline=deadline,
        timezone=str(fixture["timezone"]),
        capacity_hours_per_week=Decimal(str(fixture["capacity_hours_per_week"])).quantize(
            Decimal("0.01")
        ),
        team_size=int(fixture["team_size"]),
        status="active",
        notes=(
            "Synthetic university fixture. No production secrets, live providers, "
            "or real personal data."
        ),
    )
    session.add(project)
    session.flush()
    _seed_intake(session, project, fixture, start_date)

    planning_run = AgentRun(
        id=_id(slug, "planning-run"),
        project_id=project.id,
        initiator_id=owner.id,
        workflow="planning",
        status="completed",
        idempotency_key=f"demo:{slug}:planning",
        input_hash=canonical_hash({"fixture": slug, "goal": project.goal}),
        token_budget=50_000,
        tokens_used=8_400 if fixture["main_demo"] else 4_200,
        current_step="plan.persist_draft",
        state_snapshot={
            "schema_version": "1.0",
            "workflow": "planning",
            "status": "completed",
            "current_step": "plan.persist_draft",
            "completed_steps": [
                "plan.clarify",
                "plan.analyze",
                "plan.modules",
                "plan.milestones",
                "plan.tasks",
                "plan.dependencies",
                "plan.estimates",
                "plan.schedule",
                "plan.risks",
                "plan.persist_draft",
            ],
            "failed_steps": [],
        },
        candidate_data={"fixture": slug, "validated": True, "provider": "fixture"},
        outcome={"quality_gate": "passed", "provider_calls": 0},
        proposed_plan_version_id=_id(slug, "plan"),
        started_at=_at(day_offset=-7, hour=9),
        completed_at=_at(day_offset=-7, hour=9, minute=3),
    )
    session.add(planning_run)
    session.flush()
    _seed_run_steps(session, planning_run, slug)
    _seed_clarifications(session, owner, project, planning_run, fixture)

    plan = PlanVersion(
        id=_id(slug, "plan"),
        project_id=project.id,
        number=1,
        state="draft",
        based_on_id=None,
        reason="Validated deterministic university fixture promoted after owner approval.",
        content_hash=canonical_hash({"pending": slug}),
        quality_status="passed",
        quality_report={
            "passed": True,
            "must_issue_count": 0,
            "module_coverage": "1.00",
            "invalid_edges": 0,
            "cycle_count": 0,
            "schedule_warning": str(fixture["warning"]),
            "fixture_assertion": True,
        },
        source_run_id=planning_run.id,
    )
    session.add(plan)
    session.flush()
    _seed_plan_content(session, project, plan, fixture)
    session.flush()
    plan.content_hash = persisted_content_hash(session, plan)
    approval = PlanApproval(
        id=_id(slug, "approval"),
        project_id=project.id,
        version_id=plan.id,
        actor_id=owner.id,
        decision="approved",
        reason="Approved for the synthetic university demonstration.",
        content_hash=plan.content_hash,
        created_at=_at(day_offset=-6, hour=10),
    )
    session.add(approval)
    session.flush()
    plan.state = "active"
    session.flush()
    _seed_execution(session, owner, project, plan, fixture)
    session.flush()

    snapshot = MonitoringService(session, owner.id).ensure_current(project.id)
    recommendations = RecommendationService(
        session,
        owner.id,
        f"demo:{slug}:recommendations",
    ).sync_for_snapshot(snapshot)
    if not recommendations:
        raise RuntimeError(f"Fixture {slug} did not yield an evidence-backed recommendation.")
    recommendation = next(
        (item for item in recommendations if item.detection_code == "BLOCKED_TASKS"),
        recommendations[0],
    )
    recommendation.state = "deferred"
    session.add(
        RecommendationDecision(
            id=_id(slug, "recommendation-decision"),
            recommendation_id=recommendation.id,
            actor_id=owner.id,
            decision="defer",
            reason="Review after the checkout contract working session.",
            defer_until=DEMO_REFERENCE_DATE + timedelta(days=7),
            event_key=f"demo:{slug}:recommendation:defer",
            request_hash=canonical_hash(
                {"recommendation_id": recommendation.id, "decision": "defer"}
            ),
            occurred_at=_at(day_offset=-1, hour=16),
        )
    )
    session.add(
        AuditEvent(
            id=_id(slug, "audit", "recommendation-deferred"),
            owner_id=owner.id,
            project_id=project.id,
            actor_type="user",
            actor_id=owner.id,
            action="RecommendationDecision",
            entity_type="Recommendation",
            entity_id=recommendation.id,
            before_ref={"state": "open"},
            after_ref={
                "state": "deferred",
                "decision": "defer",
                "active_plan_mutated": False,
            },
            request_id=f"demo:{slug}:recommendation",
            occurred_at=_at(day_offset=-1, hour=16),
        )
    )
    session.flush()
    report_id = _seed_report(session, owner, project, plan, slug)
    _seed_plan_audit(session, owner, project, plan, planning_run)
    retained_draft = _seed_retained_draft_and_intelligence(
        session,
        owner,
        project,
        plan,
        fixture,
    )
    return project, plan, retained_draft, report_id


def _seed_intake(
    session: Session,
    project: Project,
    fixture: dict[str, Any],
    start_date: date,
) -> None:
    for index, text in enumerate(fixture["requirements"], start=1):
        session.add(
            ProjectRequirement(
                id=_id(fixture["slug"], "requirement", index),
                project_id=project.id,
                kind="confirmed",
                text=str(text),
                normalized_text=" ".join(str(text).casefold().split()),
                source="user",
                status="confirmed",
            )
        )
    for index, text in enumerate(fixture["exclusions"], start=1):
        session.add(
            ProjectRequirement(
                id=_id(fixture["slug"], "exclusion", index),
                project_id=project.id,
                kind="excluded",
                text=str(text),
                normalized_text=" ".join(str(text).casefold().split()),
                source="user",
                status="confirmed",
            )
        )
    session.add_all(
        [
            ProjectConstraint(
                id=_id(fixture["slug"], "constraint", "scope"),
                project_id=project.id,
                constraint_type="scope_boundary",
                value_json={"excluded": list(fixture["exclusions"])},
                source="user",
                confirmed=True,
            ),
            ProjectConstraint(
                id=_id(fixture["slug"], "constraint", "deadline"),
                project_id=project.id,
                constraint_type="delivery_window",
                value_json={"weeks": int(fixture["weeks"])},
                source="user",
                confirmed=True,
            ),
            WorkCalendar(
                id=_id(fixture["slug"], "calendar"),
                project_id=project.id,
                weekday_hours={
                    "monday": 8,
                    "tuesday": 8,
                    "wednesday": 8,
                    "thursday": 8,
                    "friday": 8,
                },
                holidays=[],
                effective_from=start_date,
                effective_to=None,
                parallel_limit=int(fixture["team_size"]),
            ),
        ]
    )


def _seed_run_steps(session: Session, run: AgentRun, slug: str) -> None:
    names = [
        ("plan.clarify", "human"),
        ("plan.analyze", "llm"),
        ("plan.modules", "llm"),
        ("plan.milestones", "llm"),
        ("plan.tasks", "llm"),
        ("plan.dependencies", "deterministic"),
        ("plan.estimates", "deterministic"),
        ("plan.schedule", "deterministic"),
        ("plan.risks", "llm"),
        ("plan.persist_draft", "transactional"),
    ]
    for index, (name, mode) in enumerate(names, start=1):
        started = _at(day_offset=-7, hour=9, minute=index - 1)
        session.add(
            AgentRunStep(
                id=_id(slug, "run-step", name),
                run_id=run.id,
                name=name,
                mode=mode,
                purpose=f"Persisted fixture checkpoint for {name}.",
                attempt=1,
                status="completed",
                input_hash=canonical_hash({"fixture": slug, "step": name}),
                idempotency_key=f"demo:{slug}:step:{name}",
                input_refs=[{"type": "fixture", "ref": slug}],
                output_refs=[{"type": "checkpoint", "ref": name}],
                validation=[{"code": "FIXTURE_VALID", "passed": True}],
                usage={"input_tokens": 0, "output_tokens": 0, "fixture": True},
                failure_code=None,
                retryable=False,
                started_at=started,
                completed_at=started + timedelta(milliseconds=250),
                duration_ms=250,
            )
        )


def _seed_clarifications(
    session: Session,
    owner: User,
    project: Project,
    run: AgentRun,
    fixture: dict[str, Any],
) -> None:
    for index, item in enumerate(fixture["clarifications"], start=1):
        key = str(item["key"])
        question_id = _id(fixture["slug"], "clarification", key)
        session.add(
            ClarificationQuestion(
                id=question_id,
                project_id=project.id,
                run_id=run.id,
                stable_key=key,
                source_temp_id=key,
                question=str(item["question"]),
                reason="The answer changes scope, schedule, risk, or implementation assumptions.",
                affects=["scope", "schedule", "risks"],
                required=True,
                answer_type="text",
                options=[],
                default_assumption="Use a safe synthetic capability until the owner confirms.",
                source_fact_refs=["PROJECT-GOAL"],
                answer_json={"value": str(item["answer"])},
                status="answered",
                answered_by_id=owner.id,
                answered_at=_at(day_offset=-7, hour=8, minute=index),
            )
        )
        session.add(
            PlanningDecision(
                id=_id(fixture["slug"], "decision", key),
                project_id=project.id,
                run_id=run.id,
                stable_key=f"DEC-{index:03d}",
                decision_type="answer",
                text=str(item["answer"]),
                rationale="Recorded owner answer to a persisted clarification.",
                source_question_id=question_id,
                source_fact_refs=[key],
            )
        )


def _seed_plan_content(
    session: Session,
    project: Project,
    plan: PlanVersion,
    fixture: dict[str, Any],
    *,
    identity_scope: str | None = None,
) -> None:
    if project.start_date is None:
        raise ValueError("Demo projects require a deterministic start date.")
    project_start = project.start_date

    def content_id(kind: str, *parts: object) -> UUID:
        if identity_scope is None:
            return _id(fixture["slug"], kind, *parts)
        return _id(fixture["slug"], identity_scope, kind, *parts)

    modules = [
        {
            "temp_id": f"MOD-{index:03d}",
            "name": str(name).replace("-", " ").title(),
            "objective": f"Deliver the {str(name).replace('-', ' ')} capability.",
            "requirement_refs": [f"REQ-{min(index, len(fixture['requirements'])):03d}"],
        }
        for index, name in enumerate(fixture["modules"], start=1)
    ]
    summary = (
        "Six-week owner-operated commerce MVP for shoppers and an administrator."
        if fixture["main_demo"]
        else str(fixture["desired_outcome"])
    )
    session.add(
        ProjectAnalysis(
            id=content_id("analysis"),
            version_id=plan.id,
            summary=summary,
            project_type="commerce_web" if "commerce" in fixture["modules"] else "software_product",
            intended_users=(
                ["shoppers", "administrator"]
                if fixture["main_demo"]
                else ["authenticated owner", "authorized user"]
            ),
            objectives=[
                {
                    "text": str(fixture["desired_outcome"]),
                    "source_fact_refs": ["PROJECT-GOAL"],
                }
            ],
            success_criteria=[
                {
                    "text": "The evidence-backed end-to-end fixture passes without invalid edges.",
                    "source_fact_refs": ["PROJECT-GOAL"],
                }
            ],
            modules=modules,
            workstreams=[str(item) for item in fixture["modules"]],
            assumptions=[
                {
                    "temp_id": "ASM-001",
                    "text": (
                        "Sandbox payment provider until Q-001 is answered."
                        if fixture["main_demo"]
                        else "Only the explicitly confirmed synthetic capabilities are available."
                    ),
                    "rationale": "Avoids inventing external systems or credentials.",
                    "source_fact_refs": ["Q-001"],
                }
            ],
            constraints=[
                {
                    "text": f"{fixture['weeks']} week delivery window",
                    "source_fact_refs": ["PROJECT-DEADLINE"],
                }
            ],
            complexity="high" if fixture["main_demo"] else "medium",
            mvp_boundary=[str(item) for item in fixture["requirements"]],
            excluded_scope=[str(item) for item in fixture["exclusions"]],
        )
    )
    milestone_ids: list[UUID] = []
    milestone_names = [
        ("Foundation ready", "A secure executable foundation"),
        (
            "Purchasing flow demonstrable"
            if fixture["main_demo"]
            else "Core workflow demonstrable",
            (
                "A tested cart-to-sandbox-checkout vertical slice"
                if fixture["main_demo"]
                else "A tested primary workflow vertical slice"
            ),
        ),
        ("Release evidence complete", "A deployed, tested, and documented release candidate"),
    ]
    for index, (name, deliverable) in enumerate(milestone_names, start=1):
        milestone_id = content_id("milestone", index)
        milestone_ids.append(milestone_id)
        acceptance = (
            [
                "A seeded shopper can add two products, refresh, check out in sandbox, "
                "and see a persisted order."
            ]
            if fixture["main_demo"] and index == 2
            else [f"{deliverable} is demonstrated with persisted acceptance evidence."]
        )
        session.add(
            Milestone(
                id=milestone_id,
                version_id=plan.id,
                stable_key=f"MS-{index:03d}",
                module_refs=[f"MOD-{min(index, len(modules)):03d}"],
                name=name,
                description=f"Deliver milestone {index} for {project.name}.",
                objective=f"Complete a verifiable {name.casefold()} outcome.",
                deliverable=deliverable,
                sequence=index,
                target_date=project_start + timedelta(days=index * 10),
                planned_effort_hours=Decimal("44.00"),
                acceptance_criteria=acceptance,
                planned_start=project_start + timedelta(days=(index - 1) * 8),
                planned_finish=project_start + timedelta(days=index * 8 - 1),
                status="pending",
                source="ai",
                protected=False,
                locked=False,
            )
        )
    session.flush()

    task_count = 14 if fixture["main_demo"] else 5
    likely_efforts = (
        [Decimal("8")] * 11 + [Decimal("13"), Decimal("13"), Decimal("16")]
        if fixture["main_demo"]
        else [Decimal("8"), Decimal("8"), Decimal("12"), Decimal("12"), Decimal("16")]
    )
    task_ids: dict[int, UUID] = {}
    for index in range(1, task_count + 1):
        task_id = content_id("task", index)
        task_ids[index] = task_id
        milestone_index = min(3, ((index - 1) * 3 // task_count) + 1)
        title = _task_title(fixture, index)
        locked = bool(fixture["main_demo"] and index == 3)
        session.add(
            Task(
                id=task_id,
                version_id=plan.id,
                milestone_id=milestone_ids[milestone_index - 1],
                parent_id=None,
                stable_key=f"TASK-{index:03d}",
                title=title,
                description=f"Produce and verify: {title}.",
                deliverable=f"A persisted, testable {title.casefold()} deliverable.",
                acceptance_criteria=(
                    [
                        "Duplicate provider callbacks do not create duplicate orders.",
                        "Failed payments preserve a recoverable order state.",
                    ]
                    if fixture["main_demo"] and index == 14
                    else [f"{title} passes its deterministic fixture assertion."]
                ),
                definition_of_done=[
                    "Implementation is reviewed.",
                    "Automated verification passes.",
                    "Evidence is persisted.",
                ],
                effort_min_hours=max(Decimal("4.00"), likely_efforts[index - 1] / 2).quantize(
                    Decimal("0.01")
                ),
                effort_likely_hours=likely_efforts[index - 1].quantize(Decimal("0.01")),
                effort_max_hours=(likely_efforts[index - 1] + Decimal("8")).quantize(
                    Decimal("0.01")
                ),
                complexity="high" if index == task_count else "medium",
                workstreams=[str(fixture["modules"][(index - 1) % len(fixture["modules"])])],
                skill_tags=["implementation", "verification"],
                source="user" if locked else "ai",
                requirement_refs=[f"REQ-{((index - 1) % len(fixture['requirements'])) + 1:03d}"],
                assumption_refs=["ASM-001"],
                locked=locked,
                protected=locked,
                priority_score=(Decimal("96.00") if index == task_count else Decimal("72.00")),
                priority_label="Critical" if index == task_count else "High",
                priority_breakdown={
                    "mvp_necessity": "0.90",
                    "deadline_urgency": "0.85",
                    "user_value": "0.80",
                    "risk_reduction": "0.75",
                    "user_preference": "0.70",
                    "calculation_version": "priority-v1",
                },
                planned_start=project_start + timedelta(days=index - 1),
                planned_finish=project_start + timedelta(days=index),
                status="pending",
            )
        )
    session.flush()
    edges = [(1, 2)]
    if fixture["main_demo"]:
        edges.extend([(3, 4), (11, 14)])
    else:
        edges.append((4, 5))
    for predecessor, successor in edges:
        session.add(
            TaskDependency(
                id=content_id("dependency", predecessor, successor),
                version_id=plan.id,
                predecessor_id=task_ids[predecessor],
                successor_id=task_ids[successor],
                dependency_type="finish_to_start",
                reason=(
                    "Persistence cannot be implemented safely before order/payment "
                    "states are defined."
                    if fixture["main_demo"] and (predecessor, successor) == (11, 14)
                    else "The successor consumes the predecessor's tested deliverable."
                ),
                evidence_refs=[
                    f"TASK-{predecessor:03d}",
                    f"TASK-{successor:03d}",
                ],
                confidence_label="high",
                source="ai",
                protected=False,
            )
        )
    session.add(
        Risk(
            id=content_id("risk"),
            version_id=plan.id,
            stable_key="RISK-001",
            category="schedule" if fixture["slug"] == "impossible_deadline" else "dependency",
            description=str(fixture["risk"]),
            probability="likely",
            impact="critical" if fixture["main_demo"] else "high",
            severity=12 if fixture["main_demo"] else 9,
            trigger=str(fixture["warning"]),
            mitigation="Resolve the cited dependency or prepare an approval-gated plan change.",
            contingency=(
                "Reduce scope, add confirmed capacity, or move the deadline after approval."
            ),
            related_refs=[f"TASK-{task_count:03d}", "PROJECT-DEADLINE"],
            source_fact_refs=["PROJECT-GOAL", "PROJECT-DEADLINE"],
            status="open",
        )
    )


def _task_title(fixture: dict[str, Any], index: int) -> str:
    if fixture["main_demo"]:
        titles = {
            1: "Establish secure application foundation",
            2: "Define authentication session contract",
            3: "Implement catalog persistence",
            4: "Verify catalog browsing acceptance",
            5: "Implement cart state",
            6: "Persist cart across refresh",
            7: "Add inventory administration",
            8: "Validate inventory transitions",
            9: "Create sandbox payment adapter",
            10: "Test payment failure handling",
            11: "Define order/payment state contract",
            12: "Build checkout interaction",
            13: "Automate commerce acceptance journey",
            14: "Persist idempotent checkout result",
        }
        return titles[index]
    module = str(fixture["modules"][(index - 1) % len(fixture["modules"])]).replace("-", " ")
    return f"Deliver {module} increment {index}"


def _seed_execution(
    session: Session,
    owner: User,
    project: Project,
    plan: PlanVersion,
    fixture: dict[str, Any],
) -> None:
    tasks = list(
        session.scalars(select(Task).where(Task.version_id == plan.id).order_by(Task.stable_key))
    )
    completed_refs = {"TASK-001", "TASK-002"}
    if fixture["main_demo"]:
        completed_refs = {"TASK-003", "TASK-004", "TASK-011"}
    blocked_ref = "TASK-014" if fixture["main_demo"] else "TASK-005"
    for task in tasks:
        if task.stable_key in completed_refs:
            status = "completed"
            progress = Decimal("1.0000")
            actual = task.effort_likely_hours.quantize(Decimal("0.01"))
            reason = "Completed with persisted fixture acceptance evidence."
        elif task.stable_key == blocked_ref:
            status = "blocked"
            progress = Decimal("0.0000")
            actual = Decimal("0.00")
            reason = (
                "Checkout contract review is unresolved; downstream delivery is paused."
                if fixture["main_demo"]
                else str(fixture["warning"])
            )
        else:
            status = "ready"
            progress = Decimal("0.0000")
            actual = Decimal("0.00")
            reason = "Ready according to the accepted finish-to-start graph."
        session.add(
            TaskExecutionProjection(
                id=task.id,
                project_id=project.id,
                version_id=plan.id,
                task_id=task.id,
                status=status,
                progress_fraction=progress,
                actual_effort_hours=actual,
                blocked_reason=reason if status == "blocked" else None,
                status_changed_at=_at(day_offset=-1 if status == "blocked" else -2, hour=14),
            )
        )
        session.add(
            TaskStatusEvent(
                id=_id(fixture["slug"], "status-event", task.stable_key),
                project_id=project.id,
                version_id=plan.id,
                task_id=task.id,
                actor_id=owner.id if status in {"completed", "blocked"} else None,
                actor_type="user" if status in {"completed", "blocked"} else "system",
                from_status="in_progress" if status in {"completed", "blocked"} else None,
                to_status=status,
                reason=reason,
                progress_fraction=progress,
                correlation_id=f"demo:{fixture['slug']}:execution",
                event_key=f"demo:{fixture['slug']}:status:{task.stable_key}",
                request_hash=canonical_hash(
                    {"fixture": fixture["slug"], "task": task.stable_key, "status": status}
                ),
                occurred_at=_at(day_offset=-1 if status == "blocked" else -2, hour=14),
            )
        )
        if status == "completed":
            session.add(
                ProgressUpdate(
                    id=_id(fixture["slug"], "progress", task.stable_key),
                    project_id=project.id,
                    version_id=plan.id,
                    task_id=task.id,
                    actor_id=owner.id,
                    fraction=Decimal("1.0000"),
                    actual_effort_hours=actual,
                    note="Completed during the deterministic university fixture.",
                    source="user",
                    correlation_id=f"demo:{fixture['slug']}:execution",
                    event_key=f"demo:{fixture['slug']}:progress:{task.stable_key}",
                    request_hash=canonical_hash(
                        {"fixture": fixture["slug"], "task": task.stable_key, "fraction": "1"}
                    ),
                    occurred_at=_at(day_offset=-2, hour=14, minute=5),
                )
            )


def _seed_report(
    session: Session,
    owner: User,
    project: Project,
    plan: PlanVersion,
    slug: str,
) -> UUID:
    report_run = AgentRun(
        id=_id(slug, "report-run"),
        project_id=project.id,
        initiator_id=owner.id,
        workflow="reporting",
        status="completed",
        idempotency_key=f"demo:{slug}:weekly-report",
        input_hash=canonical_hash({"fixture": slug, "report": "weekly"}),
        token_budget=8_000,
        tokens_used=0,
        current_step="report.persist",
        state_snapshot={
            "schema_version": "1.0",
            "workflow": "reporting",
            "status": "completed",
            "current_step": "report.persist",
            "active_plan_version_id": str(plan.id),
            "completed_steps": ["report.aggregate", "report.validate", "report.persist"],
            "failed_steps": [],
        },
        candidate_data={"fixture": slug, "narrative_mode": "factual_fallback"},
        outcome={"fixture": True},
        started_at=_at(day_offset=0, hour=9),
        completed_at=_at(day_offset=0, hour=9, minute=1),
    )
    session.add(report_run)
    session.flush()
    service = ReportService(session, owner.id, f"demo:{slug}:report")
    payload = ReportCreateRequest(
        report_type="weekly",
        period_start=DEMO_REFERENCE_DATE - timedelta(days=7),
        period_end=DEMO_REFERENCE_DATE,
    )
    data = service.aggregate(project, plan, payload)
    report = service.persist(
        report_run,
        data,
        narrative=None,
        failure_code="FIXTURE_FACTUAL_FALLBACK",
    )
    report_run.outcome = {"fixture": True, "report_id": str(report.id)}
    session.flush()
    return report.id


def _seed_retained_draft_and_intelligence(
    session: Session,
    owner: User,
    project: Project,
    active_plan: PlanVersion,
    fixture: dict[str, Any],
) -> PlanVersion:
    """Retain a generated draft and representative full-version artifacts.

    The draft has independent persisted rows and a content hash of its own. The
    active version is used only as a baseline: no scenario or regeneration
    artifact provides a write path to it.
    """

    slug = str(fixture["slug"])
    draft_run = AgentRun(
        id=_id(slug, "retained-draft-run"),
        project_id=project.id,
        initiator_id=owner.id,
        workflow="planning",
        status="completed",
        idempotency_key=f"demo:{slug}:retained-draft",
        input_hash=canonical_hash(
            {
                "fixture": slug,
                "based_on_id": active_plan.id,
                "intent": "selective-regeneration-ready-draft",
            }
        ),
        token_budget=20_000,
        tokens_used=0,
        current_step="plan.persist_draft",
        state_snapshot={
            "schema_version": "1.0",
            "workflow": "planning",
            "status": "completed",
            "current_step": "plan.persist_draft",
            "active_plan_version_id": str(active_plan.id),
            "completed_steps": ["plan.clone_active", "plan.persist_draft"],
            "failed_steps": [],
        },
        candidate_data={
            "fixture": slug,
            "based_on_content_hash": active_plan.content_hash,
            "provider": "fixture",
            "locked_items_preserved": True,
        },
        outcome={"quality_gate": "passed", "provider_calls": 0},
        proposed_plan_version_id=_id(slug, "retained-draft"),
        started_at=_at(day_offset=-1, hour=10),
        completed_at=_at(day_offset=-1, hour=10, minute=1),
    )
    session.add(draft_run)
    session.flush()

    draft = PlanVersion(
        id=_id(slug, "retained-draft"),
        project_id=project.id,
        number=2,
        state="draft",
        based_on_id=active_plan.id,
        reason=(
            "Retained synthetic draft for comparison and approval-gated selective regeneration."
        ),
        content_hash=canonical_hash({"pending_draft": slug}),
        quality_status="passed",
        quality_report={
            "passed": True,
            "must_issue_count": 0,
            "module_coverage": "1.00",
            "invalid_edges": 0,
            "cycle_count": 0,
            "locked_items_preserved": True,
            "fixture_assertion": True,
        },
        source_run_id=draft_run.id,
    )
    session.add(draft)
    session.flush()
    _seed_plan_content(
        session,
        project,
        draft,
        fixture,
        identity_scope="retained-draft",
    )
    session.flush()
    draft.content_hash = persisted_content_hash(session, draft)
    session.flush()

    session.add(
        AuditEvent(
            id=_id(slug, "audit", "retained-draft-created"),
            owner_id=owner.id,
            project_id=project.id,
            actor_type="worker",
            actor_id=None,
            action="PlanDraftCreated",
            entity_type="PlanVersion",
            entity_id=draft.id,
            before_ref={
                "based_on_id": str(active_plan.id),
                "based_on_content_hash": active_plan.content_hash,
            },
            after_ref={
                "state": "draft",
                "content_hash": draft.content_hash,
                "active_plan_mutated": False,
                "locked_items_preserved": True,
            },
            request_id=f"demo:{slug}:retained-draft",
            occurred_at=_at(day_offset=-1, hour=10, minute=2),
        )
    )
    if fixture["main_demo"]:
        _seed_representative_intelligence(session, owner, project, active_plan, draft)
    session.flush()
    return draft


def _seed_representative_intelligence(
    session: Session,
    owner: User,
    project: Project,
    active_plan: PlanVersion,
    draft: PlanVersion,
) -> None:
    service = AdvancedIntelligenceService(
        session,
        owner.id,
        "demo:ecommerce_six_weeks:intelligence",
    )
    scenario_payload = ScenarioCreate(
        name="Add one week and twenty capacity hours",
        baseline_version_id=active_plan.id,
        overrides=ScenarioOverrides(
            capacity_hours_per_week=project.capacity_hours_per_week + Decimal("20"),
            deadline=(
                project.deadline + timedelta(days=7) if project.deadline is not None else None
            ),
        ),
    )
    active_snapshot = plan_content_snapshot(session, active_plan)
    scenario_result = service._scenario_result(
        project,
        active_plan,
        scenario_payload,
        active_snapshot,
    )
    scenario = Scenario(
        id=DEMO_SCENARIO_ID,
        project_id=project.id,
        baseline_version_id=active_plan.id,
        owner_id=owner.id,
        idempotency_key="demo:ecommerce_six_weeks:scenario:capacity-and-deadline",
        input_hash=canonical_hash(scenario_payload.model_dump(mode="json")),
        baseline_content_hash=active_plan.content_hash,
        name=scenario_payload.name,
        overrides_json=scenario_payload.overrides.model_dump(mode="json"),
        result_json=scenario_result,
        explanation_json=service._deterministic_explanation(scenario_result),
        status="completed",
        calculation_version="advanced-intelligence-v1",
    )
    session.add(scenario)

    regeneration_payload = RegenerationCreate(
        targets=[
            RegenerationTarget(
                entity_type="task",
                stable_key="TASK-012",
                fields=["title"],
            )
        ],
        replacements=[
            RegenerationReplacement(
                entity_type="task",
                stable_key="TASK-012",
                values={"title": "Build accessible checkout interaction"},
            )
        ],
    )
    baseline = plan_content_snapshot(session, draft)
    candidate = deepcopy(baseline)
    service._apply_virtual_replacements(candidate, regeneration_payload)
    service._validate_candidate(candidate)
    impact = summarize_comparison(baseline, candidate)
    proposal = RegenerationProposal(
        id=DEMO_REGENERATION_PROPOSAL_ID,
        project_id=project.id,
        version_id=draft.id,
        owner_id=owner.id,
        idempotency_key="demo:ecommerce_six_weeks:regeneration:checkout-title",
        input_hash=canonical_hash(regeneration_payload.model_dump(mode="json")),
        baseline_content_hash=draft.content_hash,
        selection_json=[item.model_dump(mode="json") for item in regeneration_payload.targets],
        replacements_json=[
            item.model_dump(mode="json") for item in regeneration_payload.replacements
        ],
        diff_json=service._json_safe(impact["changes"]),
        impact_json=service._json_safe(
            {key: value for key, value in impact.items() if key != "changes"}
        ),
        status="pending",
        row_version=1,
    )
    session.add(proposal)
    session.add_all(
        [
            AuditEvent(
                id=_id("ecommerce_six_weeks", "audit", "scenario-created"),
                owner_id=owner.id,
                project_id=project.id,
                actor_type="user",
                actor_id=owner.id,
                action="ScenarioCreated",
                entity_type="Scenario",
                entity_id=scenario.id,
                before_ref=None,
                after_ref={
                    "baseline_version_id": str(active_plan.id),
                    "baseline_content_hash": active_plan.content_hash,
                    "active_plan_mutated": False,
                },
                request_id="demo:ecommerce_six_weeks:intelligence",
                occurred_at=_at(day_offset=0, hour=10),
            ),
            AuditEvent(
                id=_id("ecommerce_six_weeks", "audit", "regeneration-proposed"),
                owner_id=owner.id,
                project_id=project.id,
                actor_type="user",
                actor_id=owner.id,
                action="RegenerationProposed",
                entity_type="RegenerationProposal",
                entity_id=proposal.id,
                before_ref={"draft_content_hash": draft.content_hash},
                after_ref={
                    "status": "pending",
                    "target": "TASK-012.title",
                    "active_plan_mutated": False,
                    "locked_task_003_preserved": True,
                },
                request_id="demo:ecommerce_six_weeks:intelligence",
                occurred_at=_at(day_offset=0, hour=10, minute=1),
            ),
        ]
    )


def _seed_plan_audit(
    session: Session,
    owner: User,
    project: Project,
    plan: PlanVersion,
    run: AgentRun,
) -> None:
    events = [
        (
            "PlanningRunCompleted",
            "AgentRun",
            run.id,
            {"status": "completed", "provider_calls": 0},
        ),
        (
            "PlanApproved",
            "PlanApproval",
            _id(project.id, "approval-audit-ref"),
            {"content_hash": plan.content_hash, "decision": "approved"},
        ),
        (
            "PlanActivated",
            "PlanVersion",
            plan.id,
            {"state": "active", "content_hash": plan.content_hash},
        ),
    ]
    for index, (action, entity_type, entity_id, after_ref) in enumerate(events, start=1):
        session.add(
            AuditEvent(
                id=_id(project.id, "audit", action),
                owner_id=owner.id,
                project_id=project.id,
                actor_type="user" if action != "PlanningRunCompleted" else "worker",
                actor_id=owner.id if action != "PlanningRunCompleted" else None,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_ref=None,
                after_ref=after_ref,
                request_id=f"demo:{project.id}:lifecycle",
                occurred_at=_at(day_offset=-6, hour=10, minute=index),
            )
        )


def _at(*, day_offset: int, hour: int, minute: int = 0) -> datetime:
    value = DEMO_REFERENCE_DATE + timedelta(days=day_offset)
    return datetime(value.year, value.month, value.day, hour, minute, tzinfo=UTC)
