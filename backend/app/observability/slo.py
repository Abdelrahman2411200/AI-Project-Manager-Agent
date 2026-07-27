"""Deterministic SLO snapshots and alert evaluation from redacted measurements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.ai.provider import ModelUsage
from app.core.config import Settings


class AlertCode(StrEnum):
    API_P95_HIGH = "API_P95_HIGH"
    QUEUE_AGE_HIGH = "QUEUE_AGE_HIGH"
    PROVIDER_FAILURE_RATE_HIGH = "PROVIDER_FAILURE_RATE_HIGH"
    DAILY_COST_BUDGET_HIGH = "DAILY_COST_BUDGET_HIGH"
    DUPLICATE_JOB_CLAIM = "DUPLICATE_JOB_CLAIM"
    BACKUP_FAILED = "BACKUP_FAILED"


@dataclass(frozen=True, slots=True)
class SloInputs:
    api_read_p95_ms: float = 0
    api_write_p95_ms: float = 0
    oldest_queued_job_seconds: float = 0
    provider_calls: int = 0
    provider_failures: int = 0
    daily_estimated_cost_usd: float = 0
    duplicate_job_claims: int = 0
    last_backup_succeeded: bool = True


@dataclass(frozen=True, slots=True)
class SloAlert:
    code: AlertCode
    measured: float | int | bool
    threshold: float | int | bool
    action: str


def estimate_model_cost(usage: ModelUsage, settings: Settings) -> float:
    uncached_input = max(0, usage.input_tokens - usage.cached_input_tokens)
    total = (
        uncached_input * settings.model_input_price_per_million
        + usage.cached_input_tokens * settings.model_cached_input_price_per_million
        + usage.output_tokens * settings.model_output_price_per_million
    ) / 1_000_000
    return round(total, 6)


def evaluate_slos(inputs: SloInputs, settings: Settings) -> tuple[SloAlert, ...]:
    alerts: list[SloAlert] = []
    if inputs.api_read_p95_ms > 300 or inputs.api_write_p95_ms > 600:
        alerts.append(
            SloAlert(
                AlertCode.API_P95_HIGH,
                max(inputs.api_read_p95_ms / 300, inputs.api_write_p95_ms / 600),
                1.0,
                "Inspect the slow route, database span, and current deployment saturation.",
            )
        )
    if inputs.oldest_queued_job_seconds > settings.queue_age_alert_seconds:
        alerts.append(
            SloAlert(
                AlertCode.QUEUE_AGE_HIGH,
                inputs.oldest_queued_job_seconds,
                settings.queue_age_alert_seconds,
                "Check worker health, job leases, and provider availability.",
            )
        )
    failure_ratio = (
        inputs.provider_failures / inputs.provider_calls if inputs.provider_calls else 0.0
    )
    if failure_ratio > settings.provider_failure_alert_ratio:
        alerts.append(
            SloAlert(
                AlertCode.PROVIDER_FAILURE_RATE_HIGH,
                failure_ratio,
                settings.provider_failure_alert_ratio,
                "Inspect typed provider failure codes and keep deterministic features available.",
            )
        )
    cost_ratio = inputs.daily_estimated_cost_usd / settings.daily_model_cost_budget_usd
    if cost_ratio >= settings.daily_cost_alert_ratio:
        alerts.append(
            SloAlert(
                AlertCode.DAILY_COST_BUDGET_HIGH,
                cost_ratio,
                settings.daily_cost_alert_ratio,
                "Pause nonessential AI starts and inspect per-run usage before raising limits.",
            )
        )
    if inputs.duplicate_job_claims:
        alerts.append(
            SloAlert(
                AlertCode.DUPLICATE_JOB_CLAIM,
                inputs.duplicate_job_claims,
                0,
                "Inspect lease expiry, claim-token validation, and worker clock health.",
            )
        )
    if not inputs.last_backup_succeeded:
        alerts.append(
            SloAlert(
                AlertCode.BACKUP_FAILED,
                False,
                True,
                "Run the backup job again and complete a restore verification before release.",
            )
        )
    return tuple(alerts)
