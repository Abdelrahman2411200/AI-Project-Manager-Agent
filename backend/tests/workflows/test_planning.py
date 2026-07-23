import asyncio
from copy import deepcopy
from uuid import UUID

from sqlalchemy import func, select

from app.ai.fake_provider import FakeStructuredModelProvider
from app.ai.provider import ModelFailureCode, StructuredModelError
from app.core.config import get_settings
from app.db.models.plan import Milestone, PlanVersion, Risk, Task, TaskDependency
from app.db.models.run import AgentRun, AgentRunStep
from app.db.session import SessionLocal
from app.schemas.run import ClarificationAnswer, PlanningRunRequest
from app.services.runs import PlanningRunService
from app.workflows.engine import NodeFailure
from app.workflows.planning import PLANNING_SEQUENCE, PlanningWorkflow
from tests.ai.fixtures import MILESTONE, MODULE, RISK, TASK
from tests.api.test_projects import (
    create_user_and_client,
    project_payload,
    write_headers,
)


def _outputs() -> list[dict]:
    analysis = {
        "summary": "A focused owner-facing project planning application for a reliable release.",
        "project_type": "web_application",
        "intended_users": ["Individual project owners"],
        "objectives": [{"text": "Deliver the planning assistant", "fact_ref": "REQ-001"}],
        "success_criteria": [
            {"text": "The owner can review a validated plan", "fact_ref": "REQ-001"}
        ],
        "modules": [],
        "workstreams": ["Backend"],
        "assumptions": [],
        "open_questions": [],
        "constraints": [{"text": "Use the confirmed backend stack", "fact_ref": "CONSTRAINT-001"}],
        "complexity": "medium",
        "risks": [],
        "mvp_boundary": ["Validated planning workflow"],
        "excluded_scope": ["Portfolio management"],
    }
    module = {
        **MODULE,
        "name": "Planning workflow",
        "description": "A durable workflow that creates a validated and reviewable project plan.",
        "objective": "Let the project owner produce a grounded implementation plan.",
        "deliverables": ["Validated planning draft"],
        "workstreams": ["Backend"],
    }
    milestone = {
        **MILESTONE,
        "name": "Planning draft ready",
        "description": "A complete planning workflow vertical slice ready for owner review.",
        "objective": "Produce a validated plan from the confirmed project intake.",
        "deliverable": "Validated planning draft",
        "planned_effort_hours": 12,
        "acceptance_criteria": ["The persisted draft passes every required quality gate"],
    }
    task = {
        **TASK,
        "title": "Implement durable planning workflow",
        "description": (
            "Implement the checkpointed workflow and persist its validated draft atomically."
        ),
        "deliverable": "Checkpointed planning workflow",
        "acceptance_criteria": ["A complete run persists exactly one validated draft"],
        "definition_of_done": ["Workflow integration tests pass"],
        "effort_min_hours": 8,
        "effort_likely_hours": 12,
        "effort_max_hours": 16,
        "workstreams": ["Backend"],
        "skill_tags": ["FastAPI"],
    }
    review_task = {
        **task,
        "temp_id": "TASK-002",
        "title": "Review the validated planning draft",
        "description": "Review the persisted plan and its deterministic quality evidence.",
        "deliverable": "Reviewed planning draft",
        "acceptance_criteria": ["The draft is ready for an explicit owner decision"],
        "definition_of_done": ["All quality evidence is visible to the owner"],
        "effort_min_hours": 3,
        "effort_likely_hours": 4,
        "effort_max_hours": 6,
        "workstreams": ["Quality"],
        "skill_tags": ["Planning"],
    }
    dependency = {
        "temp_id": "DEP-001",
        "predecessor_ref": "TASK-001",
        "successor_ref": "TASK-002",
        "type": "finish_to_start",
        "reason": "The persisted draft must exist before its evidence can be reviewed.",
        "evidence_refs": ["TASK-001", "TASK-002"],
        "confidence_label": "high",
    }
    risk = {
        **RISK,
        "description": "A provider interruption may delay completion of the planning workflow.",
        "trigger": "A required model call fails after all configured retries.",
        "mitigation": "Checkpoint every completed node and resume from the last valid state.",
        "contingency": "Let the owner safely restart the failed planning operation.",
        "related_refs": ["TASK-001"],
        "source_fact_refs": ["REQ-001"],
    }
    return [
        {"items": []},
        analysis,
        {"items": [module]},
        {"items": [milestone]},
        {"items": [task, review_task]},
        {"items": [deepcopy(task), deepcopy(review_task)]},
        {"items": [dependency]},
        {"items": [risk]},
    ]


def _started_run(email: str = "workflow-owner@example.com") -> tuple[UUID, UUID]:
    user, client, csrf = create_user_and_client(email)
    with client:
        project = client.post(
            "/api/v1/projects",
            json=project_payload(),
            headers=write_headers(csrf),
        ).json()
    with SessionLocal() as session:
        run = PlanningRunService(session, user.id, "test-workflow").start(
            UUID(project["id"]),
            "workflow-test-key",
            PlanningRunRequest(),
        )
        return run.id, UUID(project["id"])


async def _no_sleep(_: float) -> None:
    return None


def test_complete_workflow_persists_one_validated_draft_and_trace() -> None:
    run_id, project_id = _started_run()
    provider = FakeStructuredModelProvider(_outputs())

    with SessionLocal() as session:
        run = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert run.status == "completed"
        assert run.proposed_plan_version_id is not None
        assert run.outcome == {
            "plan_version_id": str(run.proposed_plan_version_id),
            "approval_required": True,
            "quality_gate": "passed",
        }
        assert (
            session.scalar(
                select(func.count(PlanVersion.id)).where(PlanVersion.project_id == project_id)
            )
            == 1
        )
        plan = session.get(PlanVersion, run.proposed_plan_version_id)
        assert plan is not None
        assert plan.state == "draft"
        assert plan.quality_status == "passed"
        assert (
            session.scalar(select(func.count(Milestone.id)).where(Milestone.version_id == plan.id))
            == 1
        )
        assert session.scalar(select(func.count(Task.id)).where(Task.version_id == plan.id)) == 2
        assert (
            session.scalar(
                select(func.count(TaskDependency.id)).where(TaskDependency.version_id == plan.id)
            )
            == 1
        )
        assert session.scalar(select(func.count(Risk.id)).where(Risk.version_id == plan.id)) == 1
        steps = list(
            session.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == run_id)
                .order_by(AgentRunStep.started_at)
            )
        )
        assert [item.name for item in steps] == [item.name for item in PLANNING_SEQUENCE]
        assert all(item.status == "completed" for item in steps)
        assert len(provider.requests) == 8


def test_transient_model_failure_retries_the_node_without_replaying_checkpoints() -> None:
    run_id, _ = _started_run("retry-owner@example.com")
    transient = StructuredModelError(
        ModelFailureCode.TIMED_OUT,
        "Provider timeout.",
        retryable=True,
    )
    provider = FakeStructuredModelProvider([transient, *_outputs()])

    with SessionLocal() as session:
        run = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert run.status == "completed"
        detect_attempts = list(
            session.scalars(
                select(AgentRunStep)
                .where(
                    AgentRunStep.run_id == run_id,
                    AgentRunStep.name == "detect_gaps",
                )
                .order_by(AgentRunStep.attempt)
            )
        )
        assert [(item.attempt, item.status) for item in detect_attempts] == [
            (1, "failed"),
            (2, "completed"),
        ]
        assert len(provider.requests) == 9


def test_business_invalid_task_receives_one_minimal_repair() -> None:
    run_id, _ = _started_run("repair-owner@example.com")
    outputs = _outputs()
    oversized = {
        **outputs[4]["items"][0],
        "effort_likely_hours": 40,
        "effort_max_hours": 48,
    }
    provider = FakeStructuredModelProvider(
        [
            *outputs[:4],
            {"items": [oversized]},
            outputs[4],
            *outputs[5:],
        ]
    )

    with SessionLocal() as session:
        completed = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert completed.status == "completed"
        repair_request = provider.requests[5]
        assert '"invalid_candidate"' in repair_request.input_text
        assert '"validation_errors"' in repair_request.input_text
        assert '"intake"' not in repair_request.input_text
        task_step = session.scalar(
            select(AgentRunStep).where(
                AgentRunStep.run_id == run_id,
                AgentRunStep.name == "draft_tasks",
                AgentRunStep.status == "completed",
            )
        )
        assert task_step is not None
        assert task_step.usage["repaired"] is True
        assert len(provider.requests) == 9


def test_required_quality_failure_never_exposes_a_draft() -> None:
    run_id, _ = _started_run("quality-owner@example.com")
    invalid_outputs = _outputs()
    invalid_outputs[2] = {
        "items": [
            {
                **invalid_outputs[2]["items"][0],
                "requirement_refs": ["CONSTRAINT-001"],
            }
        ]
    }
    for task_output_index in (4, 5):
        invalid_outputs[task_output_index] = {
            "items": [
                {**item, "requirement_refs": []}
                for item in invalid_outputs[task_output_index]["items"]
            ]
        }
    provider = FakeStructuredModelProvider(invalid_outputs)

    with SessionLocal() as session:
        try:
            asyncio.run(
                PlanningWorkflow(
                    session,
                    provider,
                    get_settings(),
                    sleeper=_no_sleep,
                ).execute(run_id)
            )
        except NodeFailure as error:
            assert error.code == "QUALITY_GATE_FAILED"
        else:
            raise AssertionError("Required quality failure did not stop the workflow.")
        session.expire_all()
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.proposed_plan_version_id is None
        assert session.scalar(select(func.count(PlanVersion.id))) == 0


def test_required_clarification_pauses_and_answer_resumes_from_checkpoint() -> None:
    run_id, project_id = _started_run("clarification-owner@example.com")
    question = {
        "temp_id": "Q-001",
        "question": "Which review audience must approve the first planning draft?",
        "reason": "The answer determines the required owner-facing acceptance evidence.",
        "affects": ["scope", "quality"],
        "required": True,
        "answer_type": "single_choice",
        "options": ["Project owner", "University reviewer"],
        "default_assumption": None,
        "source_fact_refs": ["REQ-001"],
    }
    provider = FakeStructuredModelProvider([{"items": [question]}, *_outputs()[1:]])

    with SessionLocal() as session:
        paused = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert paused.status == "waiting_for_user"
        assert paused.current_step == "wait_or_assume"
        questions = PlanningRunService(
            session,
            paused.initiator_id,
            "answer-request",
        ).list_clarifications(project_id, run_id=run_id)
        resumed, _, did_resume = PlanningRunService(
            session,
            paused.initiator_id,
            "answer-request",
        ).answer_clarifications(
            project_id,
            run_id,
            [ClarificationAnswer(question_id=questions[0].id, answer="Project owner")],
        )
        assert did_resume
        assert resumed.status == "queued"

        completed = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert completed.status == "completed"
        validate_steps = list(
            session.scalars(
                select(AgentRunStep).where(
                    AgentRunStep.run_id == run_id,
                    AgentRunStep.name == "validate_request",
                )
            )
        )
        assert len(validate_steps) == 1
        assert len(provider.requests) == 8


def test_refusal_fails_closed_and_budget_exhaustion_is_partial() -> None:
    refused_id, _ = _started_run("refused-owner@example.com")
    refusal = StructuredModelError(
        ModelFailureCode.REFUSED,
        "Provider refused the request.",
        retryable=False,
    )
    with SessionLocal() as session:
        try:
            asyncio.run(
                PlanningWorkflow(
                    session,
                    FakeStructuredModelProvider([refusal]),
                    get_settings(),
                    sleeper=_no_sleep,
                ).execute(refused_id)
            )
        except NodeFailure as error:
            assert error.code == "MODEL_REFUSED"
        else:
            raise AssertionError("A refusal must fail the required planning node.")
        refused = session.get(AgentRun, refused_id)
        assert refused is not None
        assert refused.status == "failed"
        assert refused.proposed_plan_version_id is None

    partial_id, _ = _started_run("budget-owner@example.com")
    with SessionLocal() as session:
        partial = session.get(AgentRun, partial_id)
        assert partial is not None
        partial.tokens_used = partial.token_budget
        session.commit()
        provider = FakeStructuredModelProvider([])
        try:
            asyncio.run(
                PlanningWorkflow(
                    session,
                    provider,
                    get_settings(),
                    sleeper=_no_sleep,
                ).execute(partial_id)
            )
        except NodeFailure as error:
            assert error.code == "MODEL_TOKEN_BUDGET_EXHAUSTED"
        else:
            raise AssertionError("Budget exhaustion must yield a partial run.")
        session.expire_all()
        partial = session.get(AgentRun, partial_id)
        assert partial is not None
        assert partial.status == "partial"
        assert partial.proposed_plan_version_id is None
        assert provider.requests == []


def test_cancelled_queued_run_never_invokes_provider() -> None:
    run_id, _ = _started_run("cancel-owner@example.com")
    provider = FakeStructuredModelProvider([])
    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        cancelled = PlanningRunService(session, run.initiator_id, "cancel-request").cancel(run_id)
        assert cancelled.status == "cancelled"
        result = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                get_settings(),
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert result.status == "cancelled"
        assert provider.requests == []
