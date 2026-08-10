import asyncio
import math
import time
from copy import deepcopy
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.ai.fake_provider import FakeStructuredModelProvider
from app.ai.provider import ModelFailureCode, StructuredModelError
from app.ai.schemas.outputs import (
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    TaskDraftBatch,
)
from app.core.config import get_settings
from app.core.hashing import canonical_json
from app.db.models.plan import Milestone, PlanVersion, Risk, Task, TaskDependency
from app.db.models.project import Project
from app.db.models.run import AgentRun, AgentRunStep
from app.db.session import SessionLocal
from app.schemas.run import ClarificationAnswer, PlanningRunRequest
from app.services.planning_context import build_planning_facts
from app.services.runs import PlanningRunService
from app.workflows.engine import NodeFailure
from app.workflows.planning import PLANNING_SEQUENCE, PlanningWorkflow
from app.workflows.planning_nodes import PlanningSemanticNodes
from tests.ai.fixtures import MILESTONE, MODULE, RISK, TASK
from tests.api.test_projects import (
    create_user_and_client,
    project_payload,
    write_headers,
)


def _outputs() -> list[dict[str, Any]]:
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
        "title": "Implement owner-scoped project data",
        "description": (
            "Implement and verify owner-scoped project data persistence and authorization."
        ),
        "deliverable": "Verified owner-scoped project data",
        "acceptance_criteria": ["One owner cannot access another owner's project data"],
        "definition_of_done": ["Owner authorization integration tests pass"],
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


def test_clarification_generation_discards_questions_answered_by_confirmed_facts() -> None:
    run_id, _ = _started_run("known-fact-questions-owner@example.com")
    deadline_question = {
        "temp_id": "Q-001",
        "question": "What is the deadline for this project?",
        "reason": "The deadline was mentioned in the supplied intake.",
        "affects": ["schedule"],
        "required": True,
        "answer_type": "text",
        "options": [],
        "default_assumption": None,
        "source_fact_refs": [],
    }
    access_question = {
        "temp_id": "Q-002",
        "question": "Is role-based access control required?",
        "reason": "The supplied requirement mentions role-based access control.",
        "affects": ["scope"],
        "required": True,
        "answer_type": "boolean",
        "options": [],
        "default_assumption": None,
        "source_fact_refs": ["REQ-001"],
    }
    identity_provider_question = {
        "temp_id": "Q-003",
        "question": "Which identity provider should authenticate portal users?",
        "reason": "The authentication requirement does not select an identity provider.",
        "affects": ["architecture"],
        "required": True,
        "answer_type": "single_choice",
        "options": ["University SSO", "Application accounts"],
        "default_assumption": None,
        "source_fact_refs": ["REQ-001"],
    }
    language_question = {
        "temp_id": "Q-004",
        "question": "What is the launch language for this project?",
        "reason": "The launch language affects the interface.",
        "affects": ["scope"],
        "required": True,
        "answer_type": "text",
        "options": [],
        "default_assumption": None,
        "source_fact_refs": [],
    }
    provider = FakeStructuredModelProvider(
        [
            {
                "items": [
                    deadline_question,
                    access_question,
                    identity_provider_question,
                    language_question,
                ]
            }
        ]
    )

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        facts = replace(
            facts,
            intake={**facts.intake, "notes": "English is the launch language."},
            requirements=[
                {
                    "fact_ref": "REQ-001",
                    "kind": "stated",
                    "text": "Secure authentication and role-based access control",
                    "source": "user",
                    "status": "confirmed",
                }
            ],
            constraints=[],
            allowed_refs=frozenset({"REQ-001"}),
            excluded_refs=frozenset(),
        )
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).detect_gaps(run, facts)
        )

    assert result.repaired is True
    assert [item.temp_id for item in result.output.items] == ["Q-003"]


def test_model_call_does_not_hold_a_database_transaction_while_awaiting_provider() -> None:
    run_id, _ = _started_run("provider-transaction-owner@example.com")

    with SessionLocal() as session:
        transaction_states: list[bool] = []

        class TransactionObservingProvider(FakeStructuredModelProvider):
            async def generate(self, request: Any) -> Any:
                transaction_states.append(session.in_transaction())
                return await super().generate(request)

        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        provider = TransactionObservingProvider([{"items": []}])

        generated = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).detect_gaps(
                run,
                build_planning_facts(project),
            )
        )

        assert generated.output.items == []
        assert transaction_states == [False]
        assert session.in_transaction() is False


def test_analysis_normalizes_invented_fact_identifiers_to_confirmed_input() -> None:
    run_id, _ = _started_run("analysis-ref-normalization-owner@example.com")
    analysis = deepcopy(_outputs()[1])
    analysis["objectives"][0]["fact_ref"] = "OBJ-001"
    analysis["success_criteria"][0]["fact_ref"] = "SC-001"
    provider = FakeStructuredModelProvider([analysis])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).analyze(
                run,
                build_planning_facts(project),
            )
        )

    assert result.repaired is True
    assert result.output.objectives[0].fact_ref == "REQ-001"
    assert result.output.success_criteria[0].fact_ref == "REQ-001"
    assert len(provider.requests) == 1


def test_module_generation_repairs_missing_requirement_coverage_with_original_context() -> None:
    run_id, _ = _started_run("module-coverage-owner@example.com")
    valid = deepcopy(_outputs()[2])
    incomplete = {
        "items": [
            {
                **deepcopy(valid["items"][0]),
                "requirement_refs": ["CONSTRAINT-001"],
            }
        ]
    }
    provider = FakeStructuredModelProvider([incomplete, valid])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).modules(
                run,
                facts,
                ProjectAnalysisOutput.model_validate(_outputs()[1]),
            )
        )

    assert result.repaired is True
    assert result.output.items[0].requirement_refs == ["REQ-001"]
    repair_input = provider.requests[1].input_text
    assert '"original_context"' in repair_input
    assert '"requirements"' in repair_input
    assert '"required_requirement_refs":["REQ-001"]' in repair_input
    assert '"required_refs":["REQ-001"]' in repair_input
    assert '"repair_directive"' in repair_input


def test_module_generation_adds_grounded_coverage_after_bounded_repair() -> None:
    run_id, _ = _started_run("module-grounded-fallback-owner@example.com")
    incomplete = deepcopy(_outputs()[2])
    incomplete["items"][0]["requirement_refs"] = ["CONSTRAINT-001"]
    provider = FakeStructuredModelProvider([incomplete, deepcopy(incomplete)])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).modules(
                run,
                facts,
                ProjectAnalysisOutput.model_validate(_outputs()[1]),
            )
        )

    assert result.repaired is True
    assert len(provider.requests) == 2
    assert result.output.items[-1].name == "Confirmed requirement coverage"
    assert result.output.items[-1].requirement_refs == ["REQ-001"]
    assert "Owner-scoped project data" in result.output.items[-1].description


def test_module_generation_normalizes_model_supplied_identifiers() -> None:
    run_id, _ = _started_run("module-id-normalization-owner@example.com")
    generated_module = deepcopy(_outputs()[2])
    generated_module["items"][0]["temp_id"] = "MOD-12345"
    provider = FakeStructuredModelProvider([generated_module])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).modules(
                run,
                build_planning_facts(project),
                ProjectAnalysisOutput.model_validate(_outputs()[1]),
            )
        )

    assert result.repaired is True
    assert [item.temp_id for item in result.output.items] == ["MOD-001"]


def test_task_generation_batches_each_milestone_and_assigns_unique_plan_refs() -> None:
    run_id, _ = _started_run("task-batch-owner@example.com")
    first_module = deepcopy(_outputs()[2]["items"][0])
    second_module = {
        **deepcopy(first_module),
        "temp_id": "MOD-002",
        "name": "Owner review",
    }
    first_milestone = deepcopy(_outputs()[3]["items"][0])
    second_milestone = {
        **deepcopy(first_milestone),
        "temp_id": "MS-002",
        "module_refs": ["MOD-002"],
        "name": "Owner review ready",
        "sequence": 2,
    }
    first_task = deepcopy(_outputs()[4]["items"][0])
    second_task = {
        **deepcopy(first_task),
        "milestone_ref": "MS-002",
        "title": first_task["title"],
    }
    provider = FakeStructuredModelProvider([{"items": [first_task]}, {"items": [second_task]}])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).tasks(
                run,
                build_planning_facts(project),
                ModuleDraftBatch.model_validate({"items": [first_module, second_module]}),
                MilestoneDraftBatch.model_validate({"items": [first_milestone, second_milestone]}),
            )
        )

    assert [item.temp_id for item in result.output.items] == ["TASK-001", "TASK-002"]
    assert [item.milestone_ref for item in result.output.items] == ["MS-001", "MS-002"]
    assert [item.title for item in result.output.items] == [
        first_task["title"],
        f"{first_task['title']} — Owner review ready",
    ]
    assert result.repaired is True
    assert [request.prompt_version for request in provider.requests] == ["v6", "v6"]


def test_task_generation_splits_large_requirement_sets_into_bounded_batches() -> None:
    run_id, _ = _started_run("task-requirement-batch-owner@example.com")
    requirement_refs = [f"REQ-{index:03d}" for index in range(1, 8)]
    requirement_text = {
        reference: f"Verified capability {index}"
        for index, reference in enumerate(requirement_refs, start=1)
    }
    module = deepcopy(_outputs()[2]["items"][0])
    module["requirement_refs"] = requirement_refs
    milestone = deepcopy(_outputs()[3]["items"][0])
    responses: list[dict[str, Any]] = []
    expected_batches = [
        requirement_refs[:2],
        requirement_refs[2:4],
        requirement_refs[4:6],
        requirement_refs[6:],
    ]
    for index, batch in enumerate(expected_batches, start=1):
        task = deepcopy(_outputs()[4]["items"][0])
        task["temp_id"] = f"TASK-{900 + index}"
        task["title"] = f"Implement {' and '.join(requirement_text[item] for item in batch)}"
        task["description"] = task["title"]
        task["requirement_refs"] = batch
        response = {"items": [task]}
        responses.extend([response, deepcopy(response)])
    provider = FakeStructuredModelProvider(responses)

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        requirements = [
            {
                "fact_ref": reference,
                "kind": "stated",
                "text": requirement_text[reference],
                "source": "user",
                "status": "confirmed",
            }
            for reference in requirement_refs
        ]
        facts = replace(
            facts,
            requirements=requirements,
            allowed_refs=facts.allowed_refs | frozenset(requirement_refs),
            excluded_refs=frozenset(),
        )
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).tasks(
                run,
                facts,
                ModuleDraftBatch.model_validate({"items": [module]}),
                MilestoneDraftBatch.model_validate({"items": [milestone]}),
            )
        )

    assert {
        reference for item in result.output.items for reference in item.requirement_refs
    } == set(requirement_refs)
    first_attempts = [
        request for request in provider.requests if request.metadata.get("repair") == "false"
    ]
    assert len(first_attempts) == 4
    for request, expected_batch in zip(first_attempts, expected_batches, strict=True):
        expected_json = f'"required_requirement_refs":{canonical_json(expected_batch)}'
        assert expected_json in request.input_text


def test_task_generation_adds_one_grounded_task_per_requirement_after_repair() -> None:
    run_id, _ = _started_run("task-grounded-fallback-owner@example.com")
    module = deepcopy(_outputs()[2]["items"][0])
    module["requirement_refs"] = ["REQ-001", "REQ-002", "REQ-003"]
    milestone = deepcopy(_outputs()[3]["items"][0])
    incomplete_task = deepcopy(_outputs()[4]["items"][0])
    incomplete_task["requirement_refs"] = []
    incomplete_task["assumption_refs"] = ["ASS-001"]
    provider = FakeStructuredModelProvider(
        [
            {"items": [deepcopy(incomplete_task)]},
            {"items": [deepcopy(incomplete_task)]},
            {"items": [deepcopy(incomplete_task)]},
            {"items": [deepcopy(incomplete_task)]},
        ]
    )

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        requirements = [
            {
                "fact_ref": f"REQ-{index:03d}",
                "kind": "stated",
                "text": text,
                "source": "user",
                "status": "confirmed",
            }
            for index, text in enumerate(
                [
                    "Owner authentication",
                    "Validated project planning",
                    "Approval-gated activation",
                ],
                start=1,
            )
        ]
        facts = replace(
            facts,
            requirements=requirements,
            allowed_refs=frozenset(item["fact_ref"] for item in requirements),
            excluded_refs=frozenset(),
        )
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).tasks(
                run,
                facts,
                ModuleDraftBatch.model_validate({"items": [module]}),
                MilestoneDraftBatch.model_validate({"items": [milestone]}),
            )
        )

    assert result.repaired is True
    assert len(provider.requests) == 4
    assert [item.temp_id for item in result.output.items] == [
        "TASK-001",
        "TASK-002",
        "TASK-003",
        "TASK-004",
        "TASK-005",
    ]
    dedicated_refs = {
        item.requirement_refs[0] for item in result.output.items if len(item.requirement_refs) == 1
    }
    assert dedicated_refs == {"REQ-001", "REQ-002", "REQ-003"}
    assert all(not item.assumption_refs for item in result.output.items)
    assert all(
        item.milestone_ref == "MS-001" and 4 <= item.effort_likely_hours <= 24
        for item in result.output.items
    )


def test_task_generation_removes_semantically_unrelated_requirement_citations() -> None:
    run_id, _ = _started_run("task-semantic-grounding-owner@example.com")
    unrelated = {
        **deepcopy(_outputs()[4]["items"][0]),
        "title": "Prepare marketing illustrations",
        "description": "Create decorative campaign artwork for a public launch.",
        "deliverable": "Marketing illustration set",
        "requirement_refs": ["REQ-001"],
    }
    provider = FakeStructuredModelProvider(
        [{"items": [unrelated]}, {"items": [deepcopy(unrelated)]}]
    )

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).tasks(
                run,
                build_planning_facts(project),
                ModuleDraftBatch.model_validate(_outputs()[2]),
                MilestoneDraftBatch.model_validate(_outputs()[3]),
            )
        )

    assert result.repaired is True
    assert result.output.items[0].requirement_refs == []
    assert result.output.items[1].requirement_refs == ["REQ-001"]
    assert "Owner-scoped project data" in result.output.items[1].title


def test_milestone_generation_batches_each_module_and_assigns_unique_sequences() -> None:
    run_id, _ = _started_run("milestone-batch-owner@example.com")
    first_module = deepcopy(_outputs()[2]["items"][0])
    second_module = {
        **deepcopy(first_module),
        "temp_id": "MOD-002",
        "name": "Planning review",
        "objective": "Let the project owner review deterministic planning evidence.",
    }
    first_milestone = deepcopy(_outputs()[3]["items"][0])
    second_milestone = {
        **deepcopy(first_milestone),
        "module_refs": ["MOD-002"],
        "name": "Planning review ready",
    }
    provider = FakeStructuredModelProvider(
        [{"items": [first_milestone]}, {"items": [second_milestone]}]
    )

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).milestones(
                run,
                build_planning_facts(project),
                ModuleDraftBatch.model_validate({"items": [first_module, second_module]}),
            )
        )

    assert [item.temp_id for item in result.output.items] == ["MS-001", "MS-002"]
    assert [item.sequence for item in result.output.items] == [1, 2]
    assert [item.module_refs for item in result.output.items] == [["MOD-001"], ["MOD-002"]]
    assert [request.prompt_version for request in provider.requests] == ["v4", "v4"]


def test_dependency_generation_skips_model_for_a_single_task() -> None:
    run_id, _ = _started_run("single-task-dependency-owner@example.com")
    provider = FakeStructuredModelProvider([])
    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).dependencies(
                run,
                TaskDraftBatch.model_validate({"items": [_outputs()[4]["items"][0]]}),
            )
        )

    assert result.output.items == []
    assert provider.requests == []


def test_acceptance_refinement_cannot_remove_or_rewrite_tasks() -> None:
    run_id, _ = _started_run("acceptance-protection-owner@example.com")
    original = TaskDraftBatch.model_validate({"items": _outputs()[4]["items"]})
    refined_first = {
        **deepcopy(_outputs()[4]["items"][0]),
        "acceptance_criteria": ["The durable workflow passes its end-to-end test"],
        "definition_of_done": ["The verified workflow evidence is stored"],
    }
    provider = FakeStructuredModelProvider([{"items": [refined_first]}])

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).acceptance(
                run,
                build_planning_facts(project),
                original,
            )
        )

    assert [item.temp_id for item in result.output.items] == ["TASK-001", "TASK-002"]
    assert result.output.items[0].acceptance_criteria == refined_first["acceptance_criteria"]
    assert result.output.items[1] == original.items[1]
    assert len(provider.requests) == 1


def test_acceptance_refinement_splits_large_milestones_into_bounded_batches() -> None:
    run_id, _ = _started_run("acceptance-batch-owner@example.com")
    tasks = []
    for index in range(1, 10):
        task = deepcopy(_outputs()[4]["items"][0])
        task["temp_id"] = f"TASK-{index:03d}"
        task["title"] = f"Implement verified planning capability {index}"
        task["acceptance_criteria"] = [f"Capability {index} is verified"]
        tasks.append(task)
    original = TaskDraftBatch.model_validate({"items": tasks})
    responses = [
        {"items": [item.model_dump(mode="json") for item in original.items[index : index + 4]]}
        for index in range(0, len(original.items), 4)
    ]
    provider = FakeStructuredModelProvider(responses)

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, get_settings()).acceptance(
                run,
                build_planning_facts(project),
                original,
            )
        )

    assert [item.temp_id for item in result.output.items] == [
        f"TASK-{index:03d}" for index in range(1, 10)
    ]
    assert len(provider.requests) == 3
    assert "TASK-005" not in provider.requests[0].input_text
    assert "TASK-005" in provider.requests[1].input_text
    assert "TASK-009" in provider.requests[2].input_text


def test_optional_invalid_risk_is_discarded_after_bounded_repair() -> None:
    run_id, _ = _started_run("risk-salvage-owner@example.com")
    invalid_risk = {
        "items": [
            {
                **deepcopy(_outputs()[7]["items"][0]),
                "source_fact_refs": ["CONSTRAINT-NOT-SUPPLIED"],
            }
        ]
    }
    provider = FakeStructuredModelProvider([*_outputs()[:7], invalid_risk, invalid_risk])

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
        assert completed.proposed_plan_version_id is not None
        assert (
            session.scalar(
                select(func.count(Risk.id)).where(
                    Risk.version_id == completed.proposed_plan_version_id
                )
            )
            == 0
        )
    assert len(provider.requests) == 9


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


def test_fast_local_workflow_finishes_with_two_model_calls_for_complete_intake() -> None:
    run_id, project_id = _started_run("fast-local-owner@example.com")
    provider = FakeStructuredModelProvider(_outputs()[1:3])
    settings = get_settings().model_copy(
        update={"ai_provider": "ollama", "ollama_fast_planning": True}
    )

    with SessionLocal() as session:
        run = asyncio.run(
            PlanningWorkflow(
                session,
                provider,
                settings,
                sleeper=_no_sleep,
            ).execute(run_id)
        )
        assert run.status == "completed"
        assert run.proposed_plan_version_id is not None
        assert len(provider.requests) == 2
        assert (
            session.scalar(
                select(func.count(PlanVersion.id)).where(PlanVersion.project_id == project_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Task.id)).where(Task.version_id == run.proposed_plan_version_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(TaskDependency.id)).where(
                    TaskDependency.version_id == run.proposed_plan_version_id
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(Risk.id)).where(Risk.version_id == run.proposed_plan_version_id)
            )
            == 0
        )


def test_fast_local_module_shaping_consolidates_fan_out_without_losing_coverage() -> None:
    run_id, _ = _started_run("fast-local-module-owner@example.com")
    requirements = [
        {
            "fact_ref": f"REQ-{index:03d}",
            "kind": "stated",
            "text": f"Confirmed capability {index}",
            "source": "user",
            "status": "confirmed",
        }
        for index in range(1, 15)
    ]
    model_modules = []
    for index, requirement in enumerate(requirements, start=1):
        model_modules.append(
            {
                **deepcopy(_outputs()[2]["items"][0]),
                "temp_id": f"MOD-{index:03d}",
                "name": f"Capability area {index}",
                "description": (
                    f"Deliver the confirmed capability area {index} as a reviewable module."
                ),
                "objective": f"Complete and verify confirmed capability area {index}.",
                "deliverables": [f"Verified capability {index}"],
                "requirement_refs": [requirement["fact_ref"]],
            }
        )
    provider = FakeStructuredModelProvider([{"items": model_modules}])
    settings = get_settings().model_copy(
        update={"ai_provider": "ollama", "ollama_fast_planning": True}
    )

    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        project = session.get(Project, run.project_id)
        assert project is not None
        facts = build_planning_facts(project)
        facts = replace(
            facts,
            requirements=requirements,
            allowed_refs=frozenset(
                [*(item["fact_ref"] for item in requirements), "CONSTRAINT-001"]
            ),
            excluded_refs=frozenset(),
        )
        result = asyncio.run(
            PlanningSemanticNodes(session, provider, settings).modules(
                run,
                facts,
                ProjectAnalysisOutput.model_validate(_outputs()[1]),
            )
        )

    assert len(provider.requests) == 1
    assert len(result.output.items) == 4
    assert result.repaired is True
    assert {
        reference for module in result.output.items for reference in module.requirement_refs
    } == {item["fact_ref"] for item in requirements}


def test_evaluation_tier_planning_latency_meets_the_nfr_009_bounds() -> None:
    run_ids: list[UUID] = []
    progress_latencies: list[float] = []

    for index in range(8):
        _, client, csrf = create_user_and_client(f"latency-owner-{index}@example.com")
        with client:
            project_id = UUID(
                client.post(
                    "/api/v1/projects",
                    json=project_payload(f"Evaluation-size planning fixture {index + 1}"),
                    headers=write_headers(csrf),
                ).json()["id"]
            )
            started = time.perf_counter()
            response = client.post(
                f"/api/v1/projects/{project_id}/planning-runs",
                json={"token_budget": 50000},
                headers={
                    **write_headers(csrf),
                    "Idempotency-Key": f"nfr-009-latency-{index}",
                },
            )
            progress_latencies.append(time.perf_counter() - started)
            assert response.status_code == 201
            assert response.json()["status"] == "queued"
            run_ids.append(UUID(response.json()["id"]))

    completion_latencies: list[float] = []
    for run_id in run_ids:
        provider = FakeStructuredModelProvider(_outputs())
        with SessionLocal() as session:
            started = time.perf_counter()
            run = asyncio.run(
                PlanningWorkflow(
                    session,
                    provider,
                    get_settings(),
                    sleeper=_no_sleep,
                ).execute(run_id)
            )
            completion_latencies.append(time.perf_counter() - started)
            assert run.status == "completed"
            assert run.proposed_plan_version_id is not None

    p95_index = math.ceil(len(completion_latencies) * 0.95) - 1
    assert max(progress_latencies) < 2
    assert sorted(completion_latencies)[p95_index] < 5 * 60


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
        assert '"validation_constraints"' in repair_request.input_text
        assert '"original_context"' in repair_request.input_text
        assert '"allowed_refs"' in repair_request.input_text
        assert '"milestones"' in repair_request.input_text
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
    invalid_outputs[1]["excluded_scope"] = deepcopy(invalid_outputs[1]["mvp_boundary"])
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
