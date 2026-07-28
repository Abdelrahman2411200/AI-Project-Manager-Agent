import asyncio
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.ai.fake_provider import FakeStructuredModelProvider
from app.ai.provider import ModelRefusalError
from app.api.v1 import insights as insights_api
from app.core.config import get_settings
from app.db.models.audit import AuditEvent
from app.db.models.execution import MonitoringSnapshot
from app.db.models.insight import (
    ProductMetricEvent,
    Recommendation,
    RecommendationDecision,
    RecommendationEvidence,
    Report,
)
from app.db.models.plan import PlanVersion
from app.db.models.run import AgentRun
from app.db.session import SessionLocal
from app.reports.pdf import PdfRenderError
from app.schemas.insight import FactualReportData, ReportCreateRequest
from app.services.recommendations import (
    RecommendationGroundingError,
    RecommendationService,
)
from app.services.reports import ReportService
from app.workflows.reporting import ReportingWorkflow
from tests.api.test_execution import _active_fixture, _execution_headers
from tests.api.test_projects import ORIGIN, write_headers


def _project_today() -> date:
    return datetime.now(ZoneInfo("Africa/Cairo")).date()


def test_grounded_recommendation_decisions_are_deduplicated_and_never_mutate_plan() -> None:
    user, client, csrf, project_id, plan_id = _active_fixture("insight-owner@example.com")
    _, other, _, _, _ = _active_fixture("insight-other@example.com")
    with client, other:
        board = client.get(f"/api/v1/projects/{project_id}/execution").json()
        task = next(item for item in board["tasks"] if item["status"] == "ready")
        blocked = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={
                "to_status": "blocked",
                "reason": "A persisted external approval is unavailable.",
            },
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "phase9-block-ready-task",
            ),
        )
        assert blocked.status_code == 200
        recommendations = client.get(f"/api/v1/projects/{project_id}/recommendations")
        assert recommendations.status_code == 200
        items = recommendations.json()
        recommendation = next(item for item in items if item["detection_code"] == "BLOCKED_TASKS")
        assert recommendation["evidence"]
        assert any(item["entity_ref"] == task["stable_key"] for item in recommendation["evidence"])
        before = client.get(f"/api/v1/plan-versions/{plan_id}").json()["content_hash"]
        headers = {
            **write_headers(csrf),
            "If-Match": str(recommendation["row_version"]),
            "Idempotency-Key": "phase9-defer-blocker",
        }
        payload = {
            "reason": "Review after the external approval checkpoint.",
            "defer_until": (date.today() + timedelta(days=7)).isoformat(),
        }
        deferred = client.post(
            f"/api/v1/recommendations/{recommendation['id']}/decisions/defer",
            json=payload,
            headers=headers,
        )
        assert deferred.status_code == 200
        assert deferred.json()["state"] == "deferred"
        assert deferred.json()["latest_decision"]["decision"] == "defer"
        duplicate = client.post(
            f"/api/v1/recommendations/{recommendation['id']}/decisions/defer",
            json=payload,
            headers=headers,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["latest_decision"]["id"] == deferred.json()["latest_decision"]["id"]
        after = client.get(f"/api/v1/plan-versions/{plan_id}").json()["content_hash"]
        assert after == before
        assert other.get(f"/api/v1/recommendations/{recommendation['id']}").status_code == 404

    with SessionLocal() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(RecommendationDecision).where(
                            RecommendationDecision.recommendation_id == UUID(recommendation["id"])
                        )
                    )
                )
            )
            == 1
        )
        audits = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.project_id == project_id,
                    AuditEvent.action == "RecommendationDecision",
                )
            )
        )
        assert audits[-1].after_ref["active_plan_mutated"] is False
        snapshot = session.get(MonitoringSnapshot, UUID(recommendation["snapshot_id"]))
        assert snapshot is not None
        before_count = len(
            list(
                session.scalars(
                    select(Recommendation).where(Recommendation.project_id == project_id)
                )
            )
        )
        service = RecommendationService(session, user.id, "dedup-recommendation")
        assert service.sync_for_snapshot(snapshot)
        assert service.sync_for_snapshot(snapshot)
        after_count = len(
            list(
                session.scalars(
                    select(Recommendation).where(Recommendation.project_id == project_id)
                )
            )
        )
        assert after_count == before_count


def test_ai_can_reword_grounded_recommendations_but_cannot_change_policy() -> None:
    user, client, csrf, project_id, _ = _active_fixture("recommendation-ai@example.com")
    with client:
        board = client.get(f"/api/v1/projects/{project_id}/execution").json()
        task = next(item for item in board["tasks"] if item["status"] == "ready")
        response = client.post(
            f"/api/v1/tasks/{task['task_id']}/status",
            json={"to_status": "blocked", "reason": "A recorded external decision is pending."},
            headers=_execution_headers(
                csrf,
                task["row_version"],
                "phase9-ai-blocked-task",
            ),
        )
        assert response.status_code == 200

    with SessionLocal() as session:
        snapshot = session.scalar(
            select(MonitoringSnapshot)
            .where(MonitoringSnapshot.project_id == project_id)
            .order_by(
                MonitoringSnapshot.calculated_at.desc(),
                MonitoringSnapshot.id.desc(),
            )
        )
        assert snapshot is not None
        service = RecommendationService(session, user.id, "recommendation-ai-valid")
        recommendations = service.sync_for_snapshot(snapshot)
        assert recommendations
        outputs = []
        for index, recommendation in enumerate(recommendations, start=1):
            evidence_refs = list(
                session.scalars(
                    select(RecommendationEvidence.entity_ref).where(
                        RecommendationEvidence.recommendation_id == recommendation.id
                    )
                )
            )
            outputs.append(
                {
                    "temp_id": f"REC-{index:03d}",
                    "type": recommendation.recommendation_type,
                    "detection_code": recommendation.detection_code,
                    "evidence_refs": evidence_refs,
                    "why_it_matters": "This recorded condition requires owner attention.",
                    "suggested_action": (
                        "Review the cited facts and choose an explicit owner action."
                    ),
                    "expected_impact": (
                        "The execution projection can be recalculated from persisted facts."
                    ),
                    "urgency": recommendation.urgency,
                    "risk": "Ignoring the cited condition can delay approved delivery.",
                    "approval_required": recommendation.approval_required,
                    "verification_step": (
                        "Recalculate monitoring and verify the cited condition is resolved."
                    ),
                    "alternatives": ["Continue monitoring without changing the active plan."],
                }
            )
        enriched, _ = asyncio.run(
            service.enrich_with_ai(
                snapshot,
                recommendations,
                FakeStructuredModelProvider([{"items": outputs}]),
                get_settings(),
                run_id=UUID(int=1),
            )
        )
        assert all(item.explanation_source == "ai" for item in enriched)
        original_type = enriched[0].recommendation_type
        original_approval = enriched[0].approval_required

        invalid = [dict(item) for item in outputs]
        invalid[0] = {
            **invalid[0],
            "type": (
                "next_action" if invalid[0]["type"] != "next_action" else "dependency_warning"
            ),
            "approval_required": not bool(invalid[0]["approval_required"]),
        }
        with pytest.raises(RecommendationGroundingError, match="grounding"):
            asyncio.run(
                RecommendationService(
                    session,
                    user.id,
                    "recommendation-ai-invalid",
                ).enrich_with_ai(
                    snapshot,
                    enriched,
                    FakeStructuredModelProvider([{"items": invalid}]),
                    get_settings(),
                    run_id=UUID(int=2),
                )
            )
        assert enriched[0].recommendation_type == original_type
        assert enriched[0].approval_required is original_approval


def test_report_workflow_persists_factual_fallback_exports_and_is_owner_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePdfRenderer:
        def render(self, html: str) -> bytes:
            assert "METRIC-PROGRESS" in html
            assert "Report content hash" in html
            return b"%PDF-1.7\nphase-12-factual-report\n%%EOF"

    monkeypatch.setattr(insights_api, "_pdf_renderer", lambda: FakePdfRenderer())
    _, client, csrf, project_id, _ = _active_fixture("report-owner@example.com")
    _, other, _, _, _ = _active_fixture("report-other@example.com")
    period_end = _project_today()
    period_start = period_end - timedelta(days=6)
    with client:
        started = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json={
                "report_type": "weekly",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
            headers={
                **write_headers(csrf),
                "Idempotency-Key": "phase9-weekly-report",
            },
        )
        assert started.status_code == 202
        run_id = UUID(started.json()["run_id"])
    with SessionLocal() as session:
        run = asyncio.run(ReportingWorkflow(session, None, get_settings()).execute(run_id))
        assert run.status == "partial"
        assert run.outcome is not None
        report_id = UUID(run.outcome["report_id"])
    with client, other:
        run_view = client.get(f"/api/v1/agent-runs/{run_id}")
        assert run_view.status_code == 200
        assert run_view.json()["workflow"] == "reporting"
        reports = client.get(f"/api/v1/projects/{project_id}/reports")
        assert reports.status_code == 200
        assert reports.json()[0]["status"] == "partial"
        detail = client.get(f"/api/v1/reports/{report_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["narrative"] is None
        assert body["data"]["project_id"] == str(project_id)
        assert body["data"]["evidence"]["METRIC-PROGRESS"]
        assert "AI narrative was unavailable or rejected" in body["markdown"]
        export = client.get(f"/api/v1/reports/{report_id}/export.md")
        assert export.status_code == 200
        assert export.headers["x-content-type-options"] == "nosniff"
        assert export.headers["content-disposition"].endswith(
            f'weekly-report-{period_end.isoformat()}.md"'
        )
        assert export.text.rstrip() == body["markdown"].rstrip()
        pdf = client.get(f"/api/v1/reports/{report_id}/export.pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.headers["x-content-type-options"] == "nosniff"
        assert pdf.headers["cache-control"] == "private, no-store"
        assert pdf.headers["content-security-policy"] == "sandbox"
        assert pdf.headers["x-report-content-hash"] == body["content_hash"]
        assert pdf.headers["x-pdf-sha256"].startswith("sha256:")
        assert pdf.headers["content-disposition"].endswith(
            f'weekly-report-{period_end.isoformat()}.pdf"'
        )
        assert other.get(f"/api/v1/reports/{report_id}").status_code == 404
        assert other.get(f"/api/v1/reports/{report_id}/export.pdf").status_code == 404

        class UnavailablePdfRenderer:
            def render(self, _: str) -> bytes:
                raise PdfRenderError("PDF_TIMEOUT", "internal timeout detail")

        monkeypatch.setattr(
            insights_api,
            "_pdf_renderer",
            lambda: UnavailablePdfRenderer(),
        )
        unavailable = client.get(f"/api/v1/reports/{report_id}/export.pdf")
        assert unavailable.status_code == 503
        assert unavailable.headers["x-error-code"] == "PDF_TIMEOUT"
        assert "internal timeout detail" not in unavailable.text
        assert client.get(f"/api/v1/reports/{report_id}/export.md").status_code == 200

    with SessionLocal() as session:
        report = session.get(Report, report_id)
        assert report is not None
        report.markdown = "mutation"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
        metrics = set(
            session.scalars(
                select(ProductMetricEvent.name).where(ProductMetricEvent.project_id == project_id)
            )
        )
        assert {"report.started", "report.partial", "report.exported"} <= metrics
        plan = session.scalar(
            select(PlanVersion).where(
                PlanVersion.project_id == project_id,
                PlanVersion.state == "active",
            )
        )
        assert plan is not None


def test_report_start_requires_csrf_valid_period_and_idempotent_payload() -> None:
    _, client, csrf, project_id, _ = _active_fixture("report-policy@example.com")
    today = _project_today()
    payload = {
        "report_type": "risk",
        "period_start": (today - timedelta(days=1)).isoformat(),
        "period_end": today.isoformat(),
    }
    with client:
        no_csrf = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json=payload,
            headers={"Origin": ORIGIN, "Idempotency-Key": "report-no-csrf"},
        )
        assert no_csrf.status_code == 403
        headers = {
            **write_headers(csrf),
            "Idempotency-Key": "phase9-idempotent-report",
        }
        first = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json=payload,
            headers=headers,
        )
        duplicate = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json=payload,
            headers=headers,
        )
        assert first.status_code == duplicate.status_code == 202
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["run_id"] == first.json()["run_id"]
        changed = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json={**payload, "report_type": "project"},
            headers=headers,
        )
        assert changed.status_code == 409
        future = client.post(
            f"/api/v1/projects/{project_id}/reports",
            json={
                **payload,
                "period_end": (today + timedelta(days=1)).isoformat(),
            },
            headers={
                **write_headers(csrf),
                "Idempotency-Key": "phase9-future-report",
            },
        )
        assert future.status_code == 409


def test_pdf_export_rejects_a_report_hash_mismatch_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, client, _, project_id, _ = _active_fixture("pdf-hash-owner@example.com")
    today = _project_today()
    with SessionLocal() as session:
        started = ReportService(session, user.id, "pdf-hash-start").start(
            project_id,
            ReportCreateRequest(
                report_type="weekly",
                period_start=today - timedelta(days=1),
                period_end=today,
            ),
            idempotency_key="pdf-hash-mismatch-report",
        )
        run = asyncio.run(ReportingWorkflow(session, None, get_settings()).execute(started.run_id))
        assert run.outcome is not None
        report_id = UUID(run.outcome["report_id"])
        session.execute(
            update(Report).where(Report.id == report_id).values(content_hash=f"sha256:{'0' * 64}")
        )
        session.commit()

    class MustNotRender:
        def render(self, _: str) -> bytes:
            raise AssertionError("Renderer must not run for a mismatched report hash.")

    monkeypatch.setattr(insights_api, "_pdf_renderer", lambda: MustNotRender())
    with client:
        response = client.get(f"/api/v1/reports/{report_id}/export.pdf")
        assert response.status_code == 409
        assert "immutable content hash" in response.json()["detail"]


def test_report_narrative_acceptance_rejection_and_refusal_are_deterministic() -> None:
    user, _, _, project_id, _ = _active_fixture("report-grounding@example.com")
    today = _project_today()
    with SessionLocal() as session:
        service = ReportService(session, user.id, "report-grounding")
        accepted_start = service.start(
            project_id,
            ReportCreateRequest(
                report_type="project",
                period_start=today - timedelta(days=2),
                period_end=today,
            ),
            idempotency_key="grounded-report-accepted",
        )
        accepted_run = session.get(AgentRun, accepted_start.run_id)
        assert accepted_run is not None
        data = FactualReportData.model_validate(accepted_run.candidate_data["report_data"])
        progress = str(data.metrics["weighted_progress_display"])
        valid = {
            "title": "Grounded project status",
            "period_summary": "Persisted project state and events form this status summary.",
            "completed_items": [],
            "progress_statement": {
                "text": f"Weighted project progress is {progress}.",
                "evidence_refs": ["METRIC-PROGRESS"],
            },
            "blockers": [],
            "risks": [],
            "next_actions": [],
            "decisions_needed": [],
            "caveats": [],
        }
        completed = asyncio.run(
            ReportingWorkflow(
                session,
                FakeStructuredModelProvider([valid]),
                get_settings(),
            ).execute(accepted_start.run_id)
        )
        assert completed.status == "completed"
        assert completed.outcome is not None
        accepted_report = session.get(Report, UUID(completed.outcome["report_id"]))
        assert accepted_report is not None
        assert accepted_report.narrative_json is not None

        rejected_start = service.start(
            project_id,
            ReportCreateRequest(
                report_type="risk",
                period_start=today - timedelta(days=2),
                period_end=today,
            ),
            idempotency_key="grounded-report-rejected",
        )
        rejected = asyncio.run(
            ReportingWorkflow(
                session,
                FakeStructuredModelProvider(
                    [
                        {
                            **valid,
                            "progress_statement": {
                                "text": "Weighted project progress is 99%.",
                                "evidence_refs": ["METRIC-PROGRESS"],
                            },
                        }
                    ]
                ),
                get_settings(),
            ).execute(rejected_start.run_id)
        )
        assert rejected.status == "partial"
        assert rejected.outcome is not None
        assert rejected.outcome["narrative_failure_code"] == "UNSUPPORTED_CLAIMS"
        rejected_report = session.get(Report, UUID(rejected.outcome["report_id"]))
        assert rejected_report is not None and rejected_report.narrative_json is None

        refused_start = service.start(
            project_id,
            ReportCreateRequest(
                report_type="milestone",
                period_start=today - timedelta(days=2),
                period_end=today,
            ),
            idempotency_key="grounded-report-refused",
        )
        refused = asyncio.run(
            ReportingWorkflow(
                session,
                FakeStructuredModelProvider([ModelRefusalError(response_id="refused")]),
                get_settings(),
            ).execute(refused_start.run_id)
        )
        assert refused.status == "partial"
        assert refused.outcome is not None
        assert refused.outcome["narrative_failure_code"] == "REFUSED"
