from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.insight import ProductMetricEvent
from app.db.session import SessionLocal
from app.services.telemetry import TelemetryRecorder


def test_product_telemetry_is_correlated_redacted_and_stably_pseudonymous() -> None:
    owner_id = uuid4()
    project_id = uuid4()
    with SessionLocal() as session:
        recorder = TelemetryRecorder(session)
        first = recorder.append(
            name="recommendation.created",
            owner_id=owner_id,
            request_id="request-123",
            attributes={"detection_code": "BLOCKED_TASKS", "evidence_count": 2},
        )
        second = recorder.append(
            name="report.completed",
            owner_id=owner_id,
            request_id="request-456",
            attributes={"report_type": "weekly", "evidence_count": 8},
        )
        recorder.append(
            name="plan.approved",
            owner_id=owner_id,
            request_id="request-789",
            attributes={"version_number": 1, "superseded_previous": False},
        )
        session.commit()
        assert first.user_hash == second.user_hash
        assert str(owner_id) not in first.user_hash
        stored = list(
            session.scalars(select(ProductMetricEvent).order_by(ProductMetricEvent.occurred_at))
        )
        assert [item.request_id for item in stored] == [
            "request-123",
            "request-456",
            "request-789",
        ]
        assert stored[0].safe_attributes == {
            "detection_code": "BLOCKED_TASKS",
            "evidence_count": 2,
        }

        with pytest.raises(ValueError, match="not allowlisted"):
            recorder.append(
                name="report.completed",
                owner_id=owner_id,
                project_id=project_id,
                request_id="request-sensitive",
                attributes={"prompt_text": "must never be persisted"},
            )

        with pytest.raises(ValueError, match="Unsupported product metric"):
            recorder.append(
                name="arbitrary.event",
                owner_id=owner_id,
                request_id="request-arbitrary",
            )
