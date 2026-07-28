import asyncio

from app.ai.fake_provider import FakeModelResponse, FakeStructuredModelProvider
from app.ai.probe import probe_provider
from app.ai.provider import ModelFailureCode, ModelUsage, StructuredModelError


def test_provider_probe_exercises_the_structured_adapter_contract() -> None:
    provider = FakeStructuredModelProvider(
        [
            FakeModelResponse(
                output={"ready": True},
                model="fake-probe-model",
                usage=ModelUsage(input_tokens=12, output_tokens=3, total_tokens=15),
            )
        ]
    )

    result = asyncio.run(probe_provider(provider))

    assert result.status == "ready"
    assert result.model == "fake-probe-model"
    assert result.total_tokens == 15
    request = provider.requests[0]
    assert request.prompt_key == "provider_probe"
    assert request.reasoning_effort == "none"
    assert request.safety_identifier == "local_demo_probe"


def test_provider_probe_reports_exhausted_quota_without_retrying() -> None:
    provider = FakeStructuredModelProvider(
        [
            StructuredModelError(
                ModelFailureCode.QUOTA_EXHAUSTED,
                "sensitive billing detail",
                retryable=False,
            )
        ]
    )

    result = asyncio.run(probe_provider(provider))

    assert result.model_dump() == {
        "status": "quota_exhausted",
        "failure_code": "quota_exhausted",
        "retryable": False,
        "model": None,
        "total_tokens": 0,
    }
    assert len(provider.requests) == 1


def test_provider_probe_returns_safe_typed_provider_failure() -> None:
    provider = FakeStructuredModelProvider(
        [
            StructuredModelError(
                ModelFailureCode.UNAVAILABLE,
                "sensitive provider detail",
                retryable=True,
            )
        ]
    )

    result = asyncio.run(probe_provider(provider))

    assert result.status == "provider_error"
    assert result.failure_code == "unavailable"
    assert result.retryable is True
    assert "sensitive" not in result.model_dump_json()
