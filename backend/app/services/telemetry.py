"""Redacted, correlated product-outcome telemetry persisted with application work."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.provider import make_safety_identifier
from app.core.config import get_settings
from app.db.models.insight import ProductMetricEvent

logger = logging.getLogger(__name__)

ALLOWED_METRICS = frozenset(
    {
        "recommendation.created",
        "recommendation.decision",
        "plan.approved",
        "plan.edit_saved",
        "report.started",
        "report.completed",
        "report.partial",
        "report.exported",
        "narrative.validation_failed",
        "narrative.provider_failed",
    }
)
FORBIDDEN_ATTRIBUTE_PARTS = (
    "email",
    "name",
    "text",
    "content",
    "prompt",
    "response",
    "reason",
    "token",
    "secret",
    "password",
)


class TelemetryRecorder:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        *,
        name: str,
        owner_id: UUID,
        request_id: str,
        project_id: UUID | None = None,
        run_id: UUID | None = None,
        attributes: dict[str, str | int | float | bool | None] | None = None,
        duration_ms: int | None = None,
    ) -> ProductMetricEvent:
        if name not in ALLOWED_METRICS:
            raise ValueError(f"Unsupported product metric: {name}")
        safe_attributes = attributes or {}
        for key in safe_attributes:
            lowered = key.casefold()
            if any(part in lowered for part in FORBIDDEN_ATTRIBUTE_PARTS):
                raise ValueError(f"Telemetry attribute is not allowlisted: {key}")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("Telemetry duration cannot be negative.")
        settings = get_settings()
        metric = ProductMetricEvent(
            name=name,
            project_id=project_id,
            run_id=run_id,
            request_id=request_id[:128],
            user_hash=make_safety_identifier(
                owner_id,
                settings.session_hash_secret.get_secret_value(),
            ),
            safe_attributes=safe_attributes,
            duration_ms=duration_ms,
        )
        self.session.add(metric)
        logger.info(
            "product_metric",
            extra={
                "metric_name": name,
                "request_id": request_id,
                "project_id": str(project_id) if project_id else None,
                "run_id": str(run_id) if run_id else None,
                "user_hash": metric.user_hash,
                "duration_ms": duration_ms,
                "safe_attributes": safe_attributes,
            },
        )
        return metric
