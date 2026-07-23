"""Deterministic, state-hashed monitoring workflow for queued recomputation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models.run import AgentRun, AgentRunStep
from app.services.monitoring import MonitoringService


class MonitoringWorkflow:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, run_id: UUID) -> AgentRun:
        run = self.session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None or run.workflow != "monitoring":
            raise ValueError("Monitoring run not found.")
        if run.status == "completed":
            return run
        service = MonitoringService(self.session, run.initiator_id)
        project, plan = service.active_plan(run.project_id)
        expected_version = str(run.candidate_data.get("active_plan_version_id", ""))
        expected_hash = str(run.candidate_data.get("state_hash", ""))
        current_hash = service.current_state_hash(project, plan)
        run.started_at = run.started_at or utc_now()
        if str(plan.id) != expected_version or current_hash != expected_hash:
            run.status = "partial"
            run.current_step = "monitor.stale"
            run.completed_at = utc_now()
            run.outcome = {
                "stale": True,
                "expected_state_hash": expected_hash,
                "current_state_hash": current_hash,
            }
            run.state_snapshot = {
                **run.state_snapshot,
                "status": "partial",
                "current_step": "monitor.stale",
                "failed_steps": ["monitor.persist"],
                "warnings": ["STALE_MONITORING_INPUT"],
                "updated_at": utc_now().isoformat(),
            }
            self.session.commit()
            return run

        snapshot = service.recalculate(
            project,
            plan,
            expected_state_hash=expected_hash,
        )
        run.status = "completed"
        run.current_step = "monitor.persist"
        run.completed_at = utc_now()
        run.outcome = {
            "snapshot_id": str(snapshot.id),
            "state_hash": snapshot.state_hash,
            "health_label": snapshot.health_label,
        }
        completed_steps = [
            "monitor.readiness",
            "monitor.progress",
            "monitor.detect",
            "monitor.reschedule",
            "monitor.health",
            "monitor.persist",
        ]
        run.state_snapshot = {
            **run.state_snapshot,
            "status": "completed",
            "current_step": "monitor.persist",
            "completed_steps": completed_steps,
            "updated_at": utc_now().isoformat(),
        }
        existing_step = self.session.scalar(
            select(AgentRunStep).where(
                AgentRunStep.run_id == run.id,
                AgentRunStep.name == "monitor.persist",
                AgentRunStep.status == "completed",
            )
        )
        if existing_step is None:
            self.session.add(
                AgentRunStep(
                    run_id=run.id,
                    name="monitor.persist",
                    mode="deterministic",
                    purpose=(
                        "Persist readiness, progress, schedule, detections, and "
                        "health for one exact active-state hash."
                    ),
                    attempt=1,
                    status="completed",
                    input_hash=run.input_hash,
                    idempotency_key=f"{run.id}:monitor.persist:1",
                    input_refs=[
                        {
                            "entity_type": "PlanVersion",
                            "entity_id": str(plan.id),
                            "content_hash": expected_hash,
                        }
                    ],
                    output_refs=[
                        {
                            "entity_type": "MonitoringSnapshot",
                            "entity_id": str(snapshot.id),
                            "content_hash": snapshot.state_hash,
                        }
                    ],
                    validation=[],
                    usage={"input_tokens": 0, "output_tokens": 0, "cost_usd": "0"},
                    completed_at=utc_now(),
                    duration_ms=0,
                )
            )
        self.session.commit()
        return run
