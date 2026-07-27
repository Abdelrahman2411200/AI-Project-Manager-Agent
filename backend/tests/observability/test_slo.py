from app.ai.provider import ModelUsage
from app.core.config import Settings
from app.observability.slo import AlertCode, SloInputs, estimate_model_cost, evaluate_slos


def settings() -> Settings:
    return Settings(_env_file=None)


def test_model_cost_uses_versioned_configured_price_classes() -> None:
    cost = estimate_model_cost(
        ModelUsage(
            input_tokens=1_000_000,
            cached_input_tokens=400_000,
            output_tokens=100_000,
            total_tokens=1_100_000,
        ),
        settings(),
    )
    assert cost == 3.1


def test_every_phase_ten_alert_fires_in_controlled_input() -> None:
    alerts = evaluate_slos(
        SloInputs(
            api_read_p95_ms=301,
            api_write_p95_ms=601,
            oldest_queued_job_seconds=301,
            provider_calls=10,
            provider_failures=3,
            daily_estimated_cost_usd=40,
            duplicate_job_claims=1,
            last_backup_succeeded=False,
        ),
        settings(),
    )
    assert {alert.code for alert in alerts} == set(AlertCode)
    assert all(alert.action for alert in alerts)


def test_healthy_measurements_produce_no_alerts() -> None:
    assert evaluate_slos(SloInputs(), settings()) == ()
