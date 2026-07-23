"""Complete resumable planning workflow from intake to validated draft."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import StructuredModelProvider
from app.ai.schemas.outputs import (
    ClarificationQuestionBatch,
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    RiskDraftBatch,
    TaskDraftBatch,
)
from app.core.config import Settings
from app.core.hashing import canonical_hash
from app.db.base import utc_now
from app.db.models.plan import ClarificationQuestion, PlanningDecision
from app.db.models.project import Project
from app.db.models.run import AgentRun, AgentRunStep
from app.domain.graph import DependencyEdge, GraphTask, GraphValidationError, validate_graph
from app.services.plan_quality import (
    PlanningCalculations,
    PlanningCandidates,
    QualityReport,
    calculate_plan,
)
from app.services.planning import persist_validated_draft
from app.services.planning_context import PlanningFacts, build_planning_facts
from app.workflows.engine import (
    DurableNodeRunner,
    NodeDefinition,
    NodeFailure,
    NodeResult,
    Sleeper,
    WorkflowCancelled,
)
from app.workflows.planning_nodes import PlanningSemanticNodes, usage_dict
from app.workflows.state import EntityReference, PlanningAgentState

PLANNING_SEQUENCE = (
    NodeDefinition(
        "validate_request",
        "Validate and normalize persisted project intake.",
        "deterministic",
    ),
    NodeDefinition(
        "detect_gaps",
        "Identify only material missing project facts.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "wait_or_assume",
        "Resolve answered questions and safe optional assumptions.",
        "human",
    ),
    NodeDefinition(
        "analyze_project",
        "Produce a grounded project analysis from confirmed facts.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "draft_modules",
        "Create requirement-covered project modules.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "draft_milestones",
        "Create ordered milestones with one deliverable each.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "draft_tasks",
        "Create actionable, sized tasks for each milestone.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "strengthen_acceptance",
        "Make task acceptance and completion criteria observable.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "suggest_dependencies",
        "Suggest evidence-backed finish-to-start task dependencies.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "validate_graph",
        "Validate task references and prove the dependency graph is acyclic.",
        "deterministic",
    ),
    NodeDefinition(
        "normalize_effort",
        "Normalize and summarize task effort ranges.",
        "deterministic",
    ),
    NodeDefinition(
        "score_priority",
        "Calculate explainable deterministic task priorities.",
        "deterministic",
    ),
    NodeDefinition(
        "schedule",
        "Calculate capacity- and dependency-aware planned dates.",
        "deterministic",
    ),
    NodeDefinition(
        "identify_risks",
        "Identify grounded project and schedule risks.",
        "llm",
        max_attempts=3,
    ),
    NodeDefinition(
        "quality_gate",
        "Verify coverage, specificity, graph, schedule, scope, and assumptions.",
        "deterministic",
    ),
    NodeDefinition(
        "persist_draft",
        "Atomically map temporary references and persist the complete draft graph.",
        "transactional",
    ),
    NodeDefinition(
        "await_approval",
        "Stop after producing a draft that requires explicit owner approval.",
        "human",
    ),
)


class PlanningWorkflow:
    def __init__(
        self,
        session: Session,
        provider: StructuredModelProvider,
        settings: Settings,
        *,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings
        self.runner = DurableNodeRunner(session, sleeper=sleeper)
        self.semantic = PlanningSemanticNodes(session, provider, settings)

    async def execute(self, run_id: UUID) -> AgentRun:
        run = self.session.get(AgentRun, run_id)
        if run is None or run.workflow != "planning":
            raise LookupError("Planning run not found.")
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        for definition in PLANNING_SEQUENCE:
            self.session.refresh(run)
            if run.cancel_requested:
                try:
                    await self.runner.run_node(
                        run,
                        definition,
                        {"cancel_requested": True},
                        self._empty,
                    )
                except WorkflowCancelled:
                    return run
            project = self._project(run)
            facts = self._facts(project, run)
            input_payload = self._input_payload(definition.name, run, facts)
            handler = self._handler(definition.name, run, project, facts)
            try:
                result, step = await self.runner.run_node(
                    run,
                    definition,
                    input_payload,
                    handler,
                )
            except WorkflowCancelled:
                return run
            except NodeFailure:
                raise
            if definition.name in {
                "detect_gaps",
                "analyze_project",
            } and self._required_questions_open(run):
                self._wait_for_user(run)
                return run
            if definition.name == "persist_draft" and step is not None:
                state = PlanningAgentState.model_validate(run.state_snapshot)
                quality_step = self.session.scalar(
                    select(AgentRunStep).where(
                        AgentRunStep.run_id == run.id,
                        AgentRunStep.name == "quality_gate",
                        AgentRunStep.status == "completed",
                    )
                )
                if run.proposed_plan_version_id is None or quality_step is None:
                    raise RuntimeError("Persisted draft checkpoint is incomplete.")
                state.proposed_plan_version_id = run.proposed_plan_version_id
                state.validation_report_ref = EntityReference(
                    entity_type="quality_report",
                    entity_id=quality_step.id,
                    version_or_hash="v1",
                )
                run.state_snapshot = state.model_dump(mode="json")
                self.session.commit()
            if definition.name == "await_approval":
                self._complete(run)
                return run
            if result is None:
                continue
        raise RuntimeError("Planning workflow ended without a terminal node.")

    def _handler(
        self,
        node_name: str,
        run: AgentRun,
        project: Project,
        facts: PlanningFacts,
    ) -> Callable[[], Awaitable[NodeResult]]:
        handlers: dict[str, Callable[[], Awaitable[NodeResult]]] = {
            "validate_request": lambda: self._validate_request(project),
            "detect_gaps": lambda: self._detect_gaps(run, facts),
            "wait_or_assume": lambda: self._wait_or_assume(run),
            "analyze_project": lambda: self._analyze(run, facts),
            "draft_modules": lambda: self._modules(run, facts),
            "draft_milestones": lambda: self._milestones(run, facts),
            "draft_tasks": lambda: self._tasks(run, facts),
            "strengthen_acceptance": lambda: self._acceptance(run, facts),
            "suggest_dependencies": lambda: self._dependencies(run),
            "validate_graph": lambda: self._validate_graph(run, project),
            "normalize_effort": lambda: self._normalize_effort(run),
            "score_priority": lambda: self._priority(run, project, facts),
            "schedule": lambda: self._schedule(run, project, facts),
            "identify_risks": lambda: self._risks(run, facts),
            "quality_gate": lambda: self._quality(run, project, facts),
            "persist_draft": lambda: self._persist(run, project, facts),
            "await_approval": self._empty,
        }
        return handlers[node_name]

    async def _validate_request(self, project: Project) -> NodeResult:
        if project.start_date and project.deadline and project.deadline < project.start_date:
            raise NodeFailure("INVALID_PROJECT_DATES", "Project deadline precedes start date.")
        if project.capacity_hours_per_week <= 0 or project.team_size < 1:
            raise NodeFailure("INVALID_PROJECT_CAPACITY", "Project capacity is invalid.")
        return NodeResult(
            candidate_updates={
                "validated_intake": {
                    "project_id": str(project.id),
                    "row_version": project.row_version,
                }
            },
            input_refs=[_ref("Project", project.id, f"v{project.row_version}")],
        )

    async def _detect_gaps(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.detect_gaps(run, facts)
        self._persist_questions(run, generated.output, prefix="detect")
        return _generated_result(
            "clarifications", generated.output, generated.usage, generated.repaired
        )

    async def _wait_or_assume(self, run: AgentRun) -> NodeResult:
        questions = list(
            self.session.scalars(
                select(ClarificationQuestion)
                .where(ClarificationQuestion.run_id == run.id)
                .order_by(ClarificationQuestion.stable_key)
            )
        )
        if any(item.required and item.status == "open" for item in questions):
            raise NodeFailure(
                "REQUIRED_CLARIFICATION_UNANSWERED",
                "Required clarification remains unanswered.",
            )
        decision_count = int(
            self.session.scalar(
                select(func.count(PlanningDecision.id)).where(
                    PlanningDecision.project_id == run.project_id
                )
            )
            or 0
        )
        decision_ids: list[UUID] = []
        for question in questions:
            existing = self.session.scalar(
                select(PlanningDecision).where(PlanningDecision.source_question_id == question.id)
            )
            if existing is not None:
                decision_ids.append(existing.id)
                continue
            if question.status == "answered":
                decision_type = "answer"
                text = str(question.answer_json)
            elif question.status == "open" and question.default_assumption:
                question.status = "assumed"
                decision_type = "assumption"
                text = question.default_assumption
            else:
                if question.status == "open":
                    question.status = "dismissed"
                continue
            decision_count += 1
            decision = PlanningDecision(
                project_id=run.project_id,
                run_id=run.id,
                stable_key=f"DEC-{decision_count:03d}",
                decision_type=decision_type,
                text=text,
                rationale=question.reason,
                source_question_id=question.id,
                source_fact_refs=question.source_fact_refs,
            )
            self.session.add(decision)
            self.session.flush()
            decision_ids.append(decision.id)
        state = PlanningAgentState.model_validate(run.state_snapshot)
        state.decision_ids = decision_ids
        run.state_snapshot = state.model_dump(mode="json")
        return NodeResult(
            candidate_updates={
                "decision_refs": [
                    item.stable_key
                    for item in self.session.scalars(
                        select(PlanningDecision).where(PlanningDecision.run_id == run.id)
                    )
                ]
            },
            output_refs=[_ref("PlanningDecision", item, "v1") for item in decision_ids],
        )

    async def _analyze(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        refreshed = self._facts(self._project(run), run)
        generated = await self.semantic.analyze(run, refreshed)
        question_batch = ClarificationQuestionBatch(items=generated.output.open_questions)
        self._persist_questions(run, question_batch, prefix="analysis")
        return _generated_result("analysis", generated.output, generated.usage, generated.repaired)

    async def _modules(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.modules(run, facts, self._analysis(run))
        return _generated_result("modules", generated.output, generated.usage, generated.repaired)

    async def _milestones(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.milestones(run, facts, self._modules_value(run))
        return _generated_result(
            "milestones", generated.output, generated.usage, generated.repaired
        )

    async def _tasks(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.tasks(run, facts, self._milestones_value(run))
        return _generated_result("tasks", generated.output, generated.usage, generated.repaired)

    async def _acceptance(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.acceptance(run, facts, self._tasks_value(run))
        return _generated_result("tasks", generated.output, generated.usage, generated.repaired)

    async def _dependencies(self, run: AgentRun) -> NodeResult:
        generated = await self.semantic.dependencies(run, self._tasks_value(run))
        return _generated_result(
            "dependencies", generated.output, generated.usage, generated.repaired
        )

    async def _validate_graph(self, run: AgentRun, project: Project) -> NodeResult:
        tasks = self._tasks_value(run)
        dependencies = self._dependencies_value(run)
        version_id = UUID(canonical_hash({"run": run.id, "kind": "graph"})[7:39])
        task_ids = {
            item.temp_id: UUID(canonical_hash({"run": run.id, "task": item.temp_id})[7:39])
            for item in tasks.items
        }
        try:
            graph = validate_graph(
                [
                    GraphTask(
                        id=task_ids[item.temp_id],
                        stable_key=item.temp_id,
                        version_id=version_id,
                    )
                    for item in tasks.items
                ],
                [
                    DependencyEdge(
                        predecessor_id=task_ids[item.predecessor_ref],
                        successor_id=task_ids[item.successor_ref],
                        version_id=version_id,
                    )
                    for item in dependencies.items
                ],
                version_id,
            )
        except (GraphValidationError, KeyError) as error:
            code = (
                error.code if isinstance(error, GraphValidationError) else "MISSING_TASK_REFERENCE"
            )
            detail = error.detail if isinstance(error, GraphValidationError) else str(error)
            raise NodeFailure(
                code,
                detail,
                validation=[
                    {
                        "stage": "deterministic",
                        "code": code,
                        "path": "$.dependencies",
                        "message": detail,
                    }
                ],
            ) from error
        order_by_id = {value: key for key, value in task_ids.items()}
        return NodeResult(
            candidate_updates={
                "graph": {
                    "topological_order": [order_by_id[item] for item in graph.topological_order],
                    "edge_count": len(dependencies.items),
                }
            },
            validation=[],
        )

    async def _normalize_effort(self, run: AgentRun) -> NodeResult:
        tasks = self._tasks_value(run)
        normalized = {
            item.temp_id: {
                "min": str(Decimal(str(item.effort_min_hours)).quantize(Decimal("0.01"))),
                "likely": str(Decimal(str(item.effort_likely_hours)).quantize(Decimal("0.01"))),
                "max": str(Decimal(str(item.effort_max_hours)).quantize(Decimal("0.01"))),
            }
            for item in tasks.items
        }
        return NodeResult(candidate_updates={"normalized_effort": normalized})

    async def _priority(self, run: AgentRun, project: Project, facts: PlanningFacts) -> NodeResult:
        report, calculations = self._calculate(run, project, facts, risks=RiskDraftBatch(items=[]))
        if calculations is None:
            raise _quality_failure(report)
        return NodeResult(candidate_updates={"priorities": calculations.priorities})

    async def _schedule(self, run: AgentRun, project: Project, facts: PlanningFacts) -> NodeResult:
        report, calculations = self._calculate(run, project, facts, risks=RiskDraftBatch(items=[]))
        if calculations is None:
            raise _quality_failure(report)
        serialized = calculations.as_dict()
        return NodeResult(
            candidate_updates={
                "schedule": {
                    "tasks": serialized["task_schedule"],
                    "milestones": serialized["milestone_schedule"],
                    "summary": serialized["schedule_summary"],
                }
            }
        )

    async def _risks(self, run: AgentRun, facts: PlanningFacts) -> NodeResult:
        generated = await self.semantic.risks(
            run,
            facts,
            self._analysis(run),
            self._modules_value(run),
            self._milestones_value(run),
            self._tasks_value(run),
            self._dependencies_value(run),
            run.candidate_data["schedule"],
        )
        return _generated_result("risks", generated.output, generated.usage, generated.repaired)

    async def _quality(self, run: AgentRun, project: Project, facts: PlanningFacts) -> NodeResult:
        report, calculations = self._calculate(run, project, facts, risks=self._risks_value(run))
        run.candidate_data = {
            **run.candidate_data,
            "quality_report": report.model_dump(mode="json"),
            "calculations": calculations.as_dict() if calculations else None,
        }
        if not report.passed or calculations is None:
            raise _quality_failure(report)
        return NodeResult(
            candidate_updates={
                "quality_report": report.model_dump(mode="json"),
                "calculations": calculations.as_dict(),
            },
            validation=[item.model_dump(mode="json") for item in report.issues],
        )

    async def _persist(self, run: AgentRun, project: Project, facts: PlanningFacts) -> NodeResult:
        report, calculations = self._calculate(run, project, facts, risks=self._risks_value(run))
        if not report.passed or calculations is None:
            raise _quality_failure(report)
        plan = persist_validated_draft(
            self.session,
            owner_id=run.initiator_id,
            request_id=f"run:{run.id}",
            project=project,
            run=run,
            candidates=self._candidates(run, self._risks_value(run)),
            report=report,
            calculations=calculations,
        )
        run.proposed_plan_version_id = plan.id
        return NodeResult(
            candidate_updates={
                "persisted_draft": {
                    "plan_version_id": str(plan.id),
                    "content_hash": plan.content_hash,
                }
            },
            output_refs=[_ref("PlanVersion", plan.id, plan.content_hash)],
        )

    async def _empty(self) -> NodeResult:
        return NodeResult()

    def _calculate(
        self,
        run: AgentRun,
        project: Project,
        facts: PlanningFacts,
        *,
        risks: RiskDraftBatch,
    ) -> tuple[QualityReport, PlanningCalculations | None]:
        fallback = (
            run.started_at.astimezone(UTC).date()
            if run.started_at and run.started_at.tzinfo
            else (run.started_at.date() if run.started_at else datetime.now(UTC).date())
        )
        return calculate_plan(
            project=project,
            run_id=run.id,
            facts=facts,
            candidates=self._candidates(run, risks),
            fallback_start=fallback,
        )

    def _candidates(self, run: AgentRun, risks: RiskDraftBatch) -> PlanningCandidates:
        return PlanningCandidates(
            analysis=self._analysis(run),
            modules=self._modules_value(run),
            milestones=self._milestones_value(run),
            tasks=self._tasks_value(run),
            dependencies=self._dependencies_value(run),
            risks=risks,
        )

    def _persist_questions(
        self,
        run: AgentRun,
        batch: ClarificationQuestionBatch,
        *,
        prefix: str,
    ) -> None:
        count = int(
            self.session.scalar(
                select(func.count(ClarificationQuestion.id)).where(
                    ClarificationQuestion.project_id == run.project_id
                )
            )
            or 0
        )
        for item in batch.items:
            source_temp_id = f"{prefix}:{item.temp_id}"
            existing = self.session.scalar(
                select(ClarificationQuestion).where(
                    ClarificationQuestion.run_id == run.id,
                    ClarificationQuestion.source_temp_id == source_temp_id,
                )
            )
            if existing is not None:
                continue
            count += 1
            self.session.add(
                ClarificationQuestion(
                    project_id=run.project_id,
                    run_id=run.id,
                    stable_key=f"Q-{count:03d}",
                    source_temp_id=source_temp_id,
                    question=item.question,
                    reason=item.reason,
                    affects=item.affects,
                    required=item.required,
                    answer_type=item.answer_type,
                    options=item.options,
                    default_assumption=item.default_assumption,
                    source_fact_refs=item.source_fact_refs,
                    status="open",
                )
            )
        self.session.flush()
        question_ids = list(
            self.session.scalars(
                select(ClarificationQuestion.id).where(ClarificationQuestion.run_id == run.id)
            )
        )
        state = PlanningAgentState.model_validate(run.state_snapshot)
        state.clarification_ids = question_ids
        run.state_snapshot = state.model_dump(mode="json")

    def _required_questions_open(self, run: AgentRun) -> bool:
        return (
            self.session.scalar(
                select(func.count(ClarificationQuestion.id)).where(
                    ClarificationQuestion.run_id == run.id,
                    ClarificationQuestion.required.is_(True),
                    ClarificationQuestion.status == "open",
                )
            )
            or 0
        ) > 0

    def _wait_for_user(self, run: AgentRun) -> None:
        run.status = "waiting_for_user"
        run.current_step = "wait_or_assume"
        state = PlanningAgentState.model_validate(run.state_snapshot)
        state.status = "waiting_for_user"
        state.current_step = "wait_or_assume"
        state.updated_at = utc_now()
        run.state_snapshot = state.model_dump(mode="json")
        self.session.commit()

    def _complete(self, run: AgentRun) -> None:
        run.status = "completed"
        run.current_step = "await_approval"
        run.completed_at = utc_now()
        run.outcome = {
            "plan_version_id": str(run.proposed_plan_version_id),
            "approval_required": True,
            "quality_gate": "passed",
        }
        state = PlanningAgentState.model_validate(run.state_snapshot)
        state.status = "completed"
        state.current_step = "await_approval"
        state.proposed_plan_version_id = run.proposed_plan_version_id
        state.approval_required = True
        state.updated_at = utc_now()
        run.state_snapshot = state.model_dump(mode="json")
        self.session.commit()

    def _input_payload(self, name: str, run: AgentRun, facts: PlanningFacts) -> dict[str, Any]:
        data = run.candidate_data
        mapping: dict[str, Any] = {
            "validate_request": {"input_hash": run.input_hash},
            "detect_gaps": {
                "input_hash": run.input_hash,
                "requirements": facts.requirements,
                "constraints": facts.constraints,
            },
            "wait_or_assume": {
                "questions": self._question_snapshot(run),
            },
            "analyze_project": {
                "input_hash": run.input_hash,
                "decisions": facts.decisions,
            },
            "draft_modules": {"analysis": data.get("analysis")},
            "draft_milestones": {
                "modules": data.get("modules"),
                "constraints": facts.constraints,
            },
            "draft_tasks": {
                "milestones": data.get("milestones"),
                "requirements": facts.requirements,
            },
            "strengthen_acceptance": {"tasks": data.get("tasks")},
            "suggest_dependencies": {"tasks": data.get("tasks")},
            "validate_graph": {
                "tasks": data.get("tasks"),
                "dependencies": data.get("dependencies"),
            },
            "normalize_effort": {"tasks": data.get("tasks")},
            "score_priority": {
                "tasks": data.get("tasks"),
                "graph": data.get("graph"),
            },
            "schedule": {
                "tasks": data.get("tasks"),
                "dependencies": data.get("dependencies"),
                "priorities": data.get("priorities"),
                "project_version": facts.intake["row_version"],
            },
            "identify_risks": {
                "analysis": data.get("analysis"),
                "tasks": data.get("tasks"),
                "schedule": data.get("schedule"),
            },
            "quality_gate": {
                key: data.get(key)
                for key in (
                    "analysis",
                    "modules",
                    "milestones",
                    "tasks",
                    "dependencies",
                    "risks",
                    "schedule",
                )
            },
            "persist_draft": {
                "quality_report": data.get("quality_report"),
                "calculations": data.get("calculations"),
            },
            "await_approval": {
                "plan_version_id": str(run.proposed_plan_version_id),
            },
        }
        return {"node": name, "input": mapping[name]}

    def _question_snapshot(self, run: AgentRun) -> list[dict[str, Any]]:
        return [
            {
                "id": str(item.id),
                "status": item.status,
                "answer": item.answer_json,
                "default_assumption": item.default_assumption,
            }
            for item in self.session.scalars(
                select(ClarificationQuestion)
                .where(ClarificationQuestion.run_id == run.id)
                .order_by(ClarificationQuestion.stable_key)
            )
        ]

    def _project(self, run: AgentRun) -> Project:
        project = self.session.get(Project, run.project_id)
        if project is None:
            raise NodeFailure("PROJECT_NOT_FOUND", "Planning project no longer exists.")
        return project

    def _facts(self, project: Project, run: AgentRun) -> PlanningFacts:
        decisions = list(
            self.session.scalars(
                select(PlanningDecision)
                .where(PlanningDecision.run_id == run.id)
                .order_by(PlanningDecision.stable_key)
            )
        )
        return build_planning_facts(project, decisions)

    @staticmethod
    def _analysis(run: AgentRun) -> ProjectAnalysisOutput:
        return ProjectAnalysisOutput.model_validate(run.candidate_data["analysis"])

    @staticmethod
    def _modules_value(run: AgentRun) -> ModuleDraftBatch:
        return ModuleDraftBatch.model_validate(run.candidate_data["modules"])

    @staticmethod
    def _milestones_value(run: AgentRun) -> MilestoneDraftBatch:
        return MilestoneDraftBatch.model_validate(run.candidate_data["milestones"])

    @staticmethod
    def _tasks_value(run: AgentRun) -> TaskDraftBatch:
        return TaskDraftBatch.model_validate(run.candidate_data["tasks"])

    @staticmethod
    def _dependencies_value(run: AgentRun) -> DependencySuggestionBatch:
        return DependencySuggestionBatch.model_validate(run.candidate_data["dependencies"])

    @staticmethod
    def _risks_value(run: AgentRun) -> RiskDraftBatch:
        return RiskDraftBatch.model_validate(run.candidate_data["risks"])


def _generated_result(
    key: str,
    output: Any,
    usage: Any,
    repaired: bool,
) -> NodeResult:
    dumped = output.model_dump(mode="json")
    return NodeResult(
        candidate_updates={key: dumped},
        output_refs=[
            {
                "entity_type": "candidate",
                "key": key,
                "content_hash": canonical_hash(dumped),
            }
        ],
        usage=usage_dict(usage, repaired=repaired),
    )


def _ref(entity_type: str, entity_id: UUID, version_or_hash: str) -> dict[str, str]:
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "version_or_hash": version_or_hash,
    }


def _quality_failure(report: QualityReport) -> NodeFailure:
    return NodeFailure(
        "QUALITY_GATE_FAILED",
        "Planning quality gate rejected the candidate draft.",
        validation=[item.model_dump(mode="json") for item in report.issues],
    )
