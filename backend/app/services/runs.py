"""Owner-scoped planning run lifecycle and clarification resume service."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.prompts.persistence import sync_prompt_catalog
from app.core.hashing import canonical_hash
from app.db.base import utc_now
from app.db.models.plan import ClarificationQuestion
from app.db.models.project import Project
from app.db.models.run import AgentRun, AgentRunStep
from app.schemas.run import ClarificationAnswer, PlanningRunRequest
from app.services.audit import AuditRecorder
from app.services.jobs import JobQueue
from app.workflows.state import EntityReference, PlanningAgentState


class RunNotFoundError(LookupError):
    pass


class RunConflictError(RuntimeError):
    pass


class ClarificationValidationError(ValueError):
    pass


class PlanningRunService:
    def __init__(self, session: Session, owner_id: UUID, request_id: str) -> None:
        self.session = session
        self.owner_id = owner_id
        self.request_id = request_id
        self.audit = AuditRecorder(session)
        self.jobs = JobQueue(session)

    def start(
        self,
        project_id: UUID,
        idempotency_key: str,
        payload: PlanningRunRequest,
    ) -> AgentRun:
        project = self._project(project_id, lock=True)
        input_hash = canonical_hash(
            {
                "project_id": project.id,
                "row_version": project.row_version,
                "token_budget": payload.token_budget,
            }
        )
        existing = self.session.scalar(
            select(AgentRun).where(
                AgentRun.initiator_id == self.owner_id,
                AgentRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.input_hash != input_hash or existing.project_id != project_id:
                raise RunConflictError(
                    "Idempotency key was already used with a different planning request."
                )
            return existing
        conflict = self.session.scalar(
            select(AgentRun.id).where(
                AgentRun.project_id == project_id,
                AgentRun.status.in_(("queued", "running", "waiting_for_user", "partial")),
            )
        )
        if conflict is not None:
            raise RunConflictError("Another planning run is already active for this project.")

        sync_prompt_catalog(self.session)
        run = AgentRun(
            project_id=project.id,
            initiator_id=self.owner_id,
            workflow="planning",
            status="queued",
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            token_budget=payload.token_budget,
            current_step="validate_request",
            candidate_data={},
        )
        self.session.add(run)
        self.session.flush()
        state = PlanningAgentState(
            run_id=run.id,
            project_id=project.id,
            status="queued",
            current_step="validate_request",
            project_version=project.row_version,
            intake_ref=EntityReference(
                entity_type="project_intake",
                entity_id=project.id,
                version_or_hash=f"v{project.row_version}",
            ),
        )
        run.state_snapshot = state.model_dump(mode="json")
        self.jobs.enqueue(
            run_id=run.id,
            idempotency_key=f"planning:{run.id}:initial",
            payload_ref={"run_id": str(run.id)},
        )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=project.id,
            action="PlanningStarted",
            entity_type="AgentRun",
            entity_id=run.id,
            request_id=self.request_id,
            after_ref={"status": run.status, "input_hash": run.input_hash},
        )
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise RunConflictError("Planning run conflicts with persisted state.") from error
        return self.get(run.id)

    def get(self, run_id: UUID) -> AgentRun:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.initiator_id == self.owner_id,
            )
        )
        if run is None:
            raise RunNotFoundError
        return run

    def steps(self, run_id: UUID) -> list[AgentRunStep]:
        self.get(run_id)
        return list(
            self.session.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == run_id)
                .order_by(AgentRunStep.started_at, AgentRunStep.attempt)
            )
        )

    def cancel(self, run_id: UUID) -> AgentRun:
        run = self.get(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        run.cancel_requested = True
        if run.status in {"queued", "waiting_for_user", "partial"}:
            run.status = "cancelled"
            run.completed_at = utc_now()
            self.jobs.cancel_run_jobs(run.id)
            state = dict(run.state_snapshot)
            state["status"] = "cancelled"
            state["updated_at"] = utc_now().isoformat()
            run.state_snapshot = state
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=run.project_id,
            action="PlanningCancellationRequested",
            entity_type="AgentRun",
            entity_id=run.id,
            request_id=self.request_id,
            after_ref={"status": run.status},
        )
        self.session.commit()
        return self.get(run.id)

    def list_clarifications(
        self, project_id: UUID, *, run_id: UUID | None = None
    ) -> list[ClarificationQuestion]:
        self._project(project_id)
        query = select(ClarificationQuestion).where(ClarificationQuestion.project_id == project_id)
        if run_id is not None:
            run = self.get(run_id)
            if run.project_id != project_id:
                raise RunNotFoundError
            query = query.where(ClarificationQuestion.run_id == run_id)
        return list(self.session.scalars(query.order_by(ClarificationQuestion.stable_key)))

    def answer_clarifications(
        self,
        project_id: UUID,
        run_id: UUID,
        answers: list[ClarificationAnswer],
    ) -> tuple[AgentRun, list[ClarificationQuestion], bool]:
        self._project(project_id, lock=True)
        run = self.get(run_id)
        if run.project_id != project_id:
            raise RunNotFoundError
        if run.status not in {"waiting_for_user", "queued"}:
            raise RunConflictError("This planning run is not waiting for clarification.")
        questions = list(
            self.session.scalars(
                select(ClarificationQuestion)
                .where(ClarificationQuestion.run_id == run.id)
                .order_by(ClarificationQuestion.stable_key)
            )
        )
        by_id = {question.id: question for question in questions}
        if len({item.question_id for item in answers}) != len(answers):
            raise ClarificationValidationError("Each question may be answered only once.")
        now = datetime.now(UTC)
        for item in answers:
            question = by_id.get(item.question_id)
            if question is None:
                raise ClarificationValidationError(
                    "Clarification question does not belong to this run."
                )
            self._validate_answer(question, item.answer)
            question.answer_json = item.answer
            question.status = "answered"
            question.answered_by_id = self.owner_id
            question.answered_at = now

        required_open = [item for item in questions if item.required and item.status == "open"]
        resumed = not required_open
        if resumed:
            answer_hash = canonical_hash(
                {str(item.id): item.answer_json for item in questions if item.status == "answered"}
            )
            run.status = "queued"
            run.current_step = "wait_or_assume"
            state = dict(run.state_snapshot)
            state["status"] = "queued"
            state["current_step"] = "wait_or_assume"
            state["updated_at"] = utc_now().isoformat()
            run.state_snapshot = state
            self.jobs.enqueue(
                run_id=run.id,
                idempotency_key=f"planning:{run.id}:resume:{answer_hash[7:23]}",
                payload_ref={"run_id": str(run.id)},
            )
        self.audit.append(
            owner_id=self.owner_id,
            actor_id=self.owner_id,
            project_id=project_id,
            action="ClarificationAnswered",
            entity_type="AgentRun",
            entity_id=run.id,
            request_id=self.request_id,
            after_ref={
                "answered_count": len(answers),
                "required_remaining": len(required_open),
                "resumed": resumed,
            },
        )
        self.session.commit()
        return self.get(run.id), self.list_clarifications(project_id, run_id=run.id), resumed

    def _project(self, project_id: UUID, *, lock: bool = False) -> Project:
        query = select(Project).where(
            Project.id == project_id,
            Project.owner_id == self.owner_id,
            Project.status == "active",
        )
        if lock:
            query = query.with_for_update()
        project = self.session.scalar(query)
        if project is None:
            raise RunNotFoundError
        return project

    @staticmethod
    def _validate_answer(question: ClarificationQuestion, answer: Any) -> None:
        kind = question.answer_type
        valid = True
        if kind == "text":
            valid = isinstance(answer, str) and bool(answer.strip())
        elif kind == "single_choice":
            valid = isinstance(answer, str) and answer in question.options
        elif kind == "multi_choice":
            valid = (
                isinstance(answer, list)
                and bool(answer)
                and all(isinstance(item, str) and item in question.options for item in answer)
            )
        elif kind == "boolean":
            valid = isinstance(answer, bool)
        elif kind == "date":
            try:
                valid = isinstance(answer, str) and date.fromisoformat(answer) is not None
            except ValueError:
                valid = False
        elif kind == "number":
            valid = isinstance(answer, (int, float, Decimal)) and not isinstance(answer, bool)
        if not valid:
            raise ClarificationValidationError(
                f"Answer for {question.stable_key} does not match {question.answer_type}."
            )
