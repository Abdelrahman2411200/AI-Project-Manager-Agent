from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.workflows.state import (
    EntityReference,
    MonitoringAgentState,
    PlanningAgentState,
    ReportingAgentState,
)


def ref(entity_type: str = "artifact") -> EntityReference:
    return EntityReference(entity_type=entity_type, entity_id=uuid4(), version_or_hash="v1")


def test_planning_waiting_state_round_trips() -> None:
    state = PlanningAgentState(
        run_id=uuid4(),
        project_id=uuid4(),
        status="waiting_for_user",
        current_step="wait_or_assume",
        project_version=1,
        intake_ref=ref("project_intake"),
        clarification_ids=[uuid4()],
    )
    assert PlanningAgentState.model_validate_json(state.model_dump_json()) == state


def test_completed_planning_requires_persisted_draft_and_quality_report() -> None:
    with pytest.raises(ValidationError, match="persisted draft and quality report"):
        PlanningAgentState(
            run_id=uuid4(),
            project_id=uuid4(),
            status="completed",
            current_step="complete",
            project_version=1,
            intake_ref=ref("project_intake"),
        )


def test_monitoring_completed_state_must_be_current_or_requeued() -> None:
    with pytest.raises(ValidationError, match="current or marked stale"):
        MonitoringAgentState(
            run_id=uuid4(),
            project_id=uuid4(),
            status="completed",
            current_step="complete",
            active_plan_version_id=uuid4(),
            event_cursor="event:10",
            state_hash=f"sha256:{'a' * 64}",
            state_is_current=False,
            stale_requeued=False,
        )


def test_monitoring_state_round_trips() -> None:
    state = MonitoringAgentState(
        run_id=uuid4(),
        project_id=uuid4(),
        status="completed",
        current_step="complete",
        active_plan_version_id=uuid4(),
        event_cursor="event:10",
        state_hash=f"sha256:{'a' * 64}",
    )
    assert MonitoringAgentState.model_validate_json(state.model_dump_json()) == state


def test_reporting_completed_state_requires_markdown_and_stored_data() -> None:
    with pytest.raises(ValidationError, match="stored data, report, and Markdown"):
        ReportingAgentState(
            run_id=uuid4(),
            project_id=uuid4(),
            status="completed",
            current_step="complete",
            active_plan_version_id=uuid4(),
            report_type="weekly",
            period_start=date(2026, 7, 13),
            period_end=date(2026, 7, 19),
            event_cursor="event:20",
            export_format="markdown",
        )


def test_pdf_render_failure_is_partial_and_round_trips() -> None:
    now = datetime.now(UTC)
    state = ReportingAgentState(
        run_id=uuid4(),
        project_id=uuid4(),
        status="partial",
        current_step="render_pdf",
        failed_steps=["render_pdf"],
        active_plan_version_id=uuid4(),
        report_type="weekly",
        period_start=date(2026, 7, 13),
        period_end=date(2026, 7, 19),
        event_cursor="event:20",
        export_format="pdf",
        report_data_ref=ref("report_data"),
        report_id=uuid4(),
        markdown_export_ref=ref("markdown_export"),
        started_at=now,
        updated_at=now,
    )
    assert ReportingAgentState.model_validate_json(state.model_dump_json()) == state
