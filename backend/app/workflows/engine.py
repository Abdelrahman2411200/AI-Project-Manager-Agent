"""Durable node runner with checkpoint, retry, resume, and cancellation semantics."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.hashing import canonical_hash
from app.db.base import utc_now
from app.db.models.run import AgentRun, AgentRunStep

NodeMode = Literal["deterministic", "llm", "human", "transactional"]
NodeHandler = Callable[[], Awaitable["NodeResult"]]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    name: str
    purpose: str
    mode: NodeMode
    max_attempts: int = 1
    required: bool = True


@dataclass(frozen=True, slots=True)
class NodeResult:
    candidate_updates: dict[str, Any] = field(default_factory=dict)
    input_refs: list[dict[str, Any]] = field(default_factory=list)
    output_refs: list[dict[str, Any]] = field(default_factory=list)
    validation: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


class NodeFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        partial: bool = False,
        validation: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.partial = partial
        self.validation = validation or []


class WorkflowCancelled(RuntimeError):
    pass


class DurableNodeRunner:
    def __init__(self, session: Session, *, sleeper: Sleeper = asyncio.sleep) -> None:
        self.session = session
        self.sleeper = sleeper

    async def run_node(
        self,
        run: AgentRun,
        definition: NodeDefinition,
        input_payload: Any,
        handler: NodeHandler,
    ) -> tuple[NodeResult | None, AgentRunStep | None]:
        if run.cancel_requested:
            self._cancel(run)
            raise WorkflowCancelled("Planning run was cancelled.")
        input_hash = canonical_hash(input_payload)
        completed = self.session.scalar(
            select(AgentRunStep).where(
                AgentRunStep.run_id == run.id,
                AgentRunStep.name == definition.name,
                AgentRunStep.input_hash == input_hash,
                AgentRunStep.status == "completed",
            )
        )
        if completed is not None:
            return None, completed

        self._close_interrupted_attempts(run.id, definition.name)
        previous_attempt = self.session.scalar(
            select(func.max(AgentRunStep.attempt)).where(
                AgentRunStep.run_id == run.id,
                AgentRunStep.name == definition.name,
            )
        )
        attempt = int(previous_attempt or 0)
        while attempt < int(previous_attempt or 0) + definition.max_attempts:
            attempt += 1
            if bool(run.cancel_requested):
                self._cancel(run)
                raise WorkflowCancelled("Planning run was cancelled.")
            step = AgentRunStep(
                run_id=run.id,
                name=definition.name,
                mode=definition.mode,
                purpose=definition.purpose,
                attempt=attempt,
                status="running",
                input_hash=input_hash,
                idempotency_key=(
                    f"{run.id}:{definition.name}:{attempt}:{input_hash.removeprefix('sha256:')[:16]}"
                ),
            )
            run.status = "running"
            run.current_step = definition.name
            run.started_at = run.started_at or utc_now()
            self.session.add(step)
            self.session.commit()
            started = monotonic_ns()
            try:
                result = await handler()
            except NodeFailure as error:
                self._fail_step(step, error, started)
                terminal = (
                    not error.retryable
                    or attempt >= int(previous_attempt or 0) + definition.max_attempts
                )
                if terminal:
                    run.status = "partial" if error.partial else "failed"
                    run.outcome = {
                        "failure_code": error.code,
                        "failed_step": definition.name,
                        "recoverable": error.partial,
                    }
                    run.completed_at = utc_now() if not error.partial else None
                    self._record_failed_state(run, definition.name)
                self.session.commit()
                if terminal:
                    raise
                jitter = int(run.id.hex[:2], 16) / 1020
                await self.sleeper(min(4.0, 2.0 ** (attempt - 1)) + jitter)
                continue
            except Exception:
                unexpected_error = NodeFailure(
                    "UNEXPECTED_NODE_ERROR",
                    "The workflow node failed unexpectedly.",
                    retryable=False,
                )
                self._fail_step(step, unexpected_error, started)
                run.status = "failed"
                run.outcome = {
                    "failure_code": unexpected_error.code,
                    "failed_step": definition.name,
                    "recoverable": False,
                }
                run.completed_at = utc_now()
                self._record_failed_state(run, definition.name)
                self.session.commit()
                raise

            step.status = "completed"
            step.completed_at = utc_now()
            step.duration_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            step.input_refs = result.input_refs
            step.output_refs = result.output_refs
            step.validation = result.validation
            step.usage = result.usage
            if result.candidate_updates:
                run.candidate_data = {**run.candidate_data, **result.candidate_updates}
            self._record_completed_state(run, definition.name)
            self.session.commit()
            return result, step
        raise RuntimeError("Node retry loop exited without a terminal result.")

    def _close_interrupted_attempts(self, run_id: UUID, node_name: str) -> None:
        interrupted = list(
            self.session.scalars(
                select(AgentRunStep).where(
                    AgentRunStep.run_id == run_id,
                    AgentRunStep.name == node_name,
                    AgentRunStep.status == "running",
                )
            )
        )
        for step in interrupted:
            step.status = "failed"
            step.failure_code = "STALE_INTERRUPTED_ATTEMPT"
            step.retryable = True
            step.completed_at = utc_now()
            if step.started_at is not None:
                started = step.started_at
                now = step.completed_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=now.tzinfo)
                step.duration_ms = max(0, int((now - started).total_seconds() * 1000))
        if interrupted:
            self.session.commit()

    @staticmethod
    def _fail_step(step: AgentRunStep, error: NodeFailure, started: int) -> None:
        step.status = "failed"
        step.failure_code = error.code
        step.retryable = error.retryable
        step.validation = error.validation
        step.completed_at = utc_now()
        step.duration_ms = max(0, (monotonic_ns() - started) // 1_000_000)

    @staticmethod
    def _record_completed_state(run: AgentRun, node_name: str) -> None:
        state = dict(run.state_snapshot)
        completed = list(state.get("completed_steps", []))
        if node_name not in completed:
            completed.append(node_name)
        state["completed_steps"] = completed
        state["current_step"] = node_name
        state["status"] = run.status
        state["updated_at"] = utc_now().isoformat()
        run.state_snapshot = state

    @staticmethod
    def _record_failed_state(run: AgentRun, node_name: str) -> None:
        state = dict(run.state_snapshot)
        failed = list(state.get("failed_steps", []))
        if node_name not in failed:
            failed.append(node_name)
        state["failed_steps"] = failed
        state["current_step"] = node_name
        state["status"] = run.status
        state["updated_at"] = utc_now().isoformat()
        run.state_snapshot = state

    def _cancel(self, run: AgentRun) -> None:
        run.status = "cancelled"
        run.completed_at = utc_now()
        state = dict(run.state_snapshot)
        state["status"] = "cancelled"
        state["updated_at"] = utc_now().isoformat()
        run.state_snapshot = state
        self.session.commit()
