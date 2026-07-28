import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.ai.fake_provider import FakeModelResponse, FakeStructuredModelProvider
from app.ai.openai_provider import OpenAIResponsesProvider
from app.ai.provider import (
    ModelFailureCode,
    ModelRefusalError,
    ModelTruncatedError,
    ModelUsage,
    StructuredModelError,
    StructuredModelRequest,
    make_safety_identifier,
    public_error_details,
)
from app.ai.schemas.outputs import ModuleDraft
from app.core.config import Settings
from tests.ai.fixtures import MODULE


def request() -> StructuredModelRequest[ModuleDraft]:
    return StructuredModelRequest(
        prompt_key="modules",
        prompt_version="v2",
        instructions="Return a module.",
        input_text="<UNTRUSTED_PROJECT_DATA>{}</UNTRUSTED_PROJECT_DATA>",
        output_type=ModuleDraft,
        token_budget=3000,
        safety_identifier="safety_8e17f1",
    )


class FakeResponses:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def response(**overrides: Any) -> SimpleNamespace:
    defaults = {
        "id": "resp_test",
        "status": "completed",
        "output": [],
        "output_parsed": ModuleDraft.model_validate(MODULE),
        "model": "gpt-5.6-terra-2026-07-01",
        "usage": SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_tokens_details=SimpleNamespace(cached_tokens=20, cache_write_tokens=10),
            output_tokens_details=SimpleNamespace(reasoning_tokens=5),
        ),
    }
    return SimpleNamespace(**(defaults | overrides))


def provider(fake_responses: FakeResponses) -> OpenAIResponsesProvider:
    settings = Settings(
        openai_model="gpt-5.6-terra",
        openai_timeout_seconds=30,
        _env_file=None,
    )
    return OpenAIResponsesProvider(
        settings,
        client=cast(AsyncOpenAI, FakeClient(fake_responses)),
    )


def test_fake_provider_enforces_the_same_schema_contract_offline() -> None:
    fake = FakeStructuredModelProvider([MODULE])
    result = asyncio.run(fake.generate(request()))
    assert result.output.temp_id == "MOD-001"
    assert result.provider == "fake"
    assert fake.requests == [request()]

    invalid = FakeStructuredModelProvider([{**MODULE, "unexpected": True}])
    with pytest.raises(ValidationError):
        asyncio.run(invalid.generate(request()))

    queued_error = StructuredModelError(
        ModelFailureCode.UNAVAILABLE,
        "offline",
        retryable=True,
    )
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(FakeStructuredModelProvider([queued_error]).generate(request()))
    assert caught.value is queued_error

    with pytest.raises(RuntimeError, match="no queued output"):
        asyncio.run(FakeStructuredModelProvider([]).generate(request()))


def test_fake_provider_captures_scripted_usage_and_metadata() -> None:
    scripted = FakeModelResponse(
        output=MODULE,
        usage=ModelUsage(input_tokens=12, output_tokens=8, total_tokens=20),
        model="fake-pinned",
        response_id="fake-response",
        duration_ms=25,
    )
    result = asyncio.run(FakeStructuredModelProvider([scripted]).generate(request()))
    assert result.usage.total_tokens == 20
    assert result.model == "fake-pinned"
    assert result.response_id == "fake-response"
    assert result.duration_ms == 25


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"prompt_key": "INVALID"}, "prompt_key"),
        ({"prompt_version": "latest"}, "prompt_version"),
        ({"token_budget": 0}, "token_budget"),
        ({"safety_identifier": "short"}, "safety_identifier"),
        ({"safety_identifier": "x" * 65}, "safety_identifier"),
        ({"reasoning_effort": "extreme"}, "reasoning_effort"),
    ],
)
def test_model_request_rejects_invalid_boundary_values(
    overrides: dict[str, Any], message: str
) -> None:
    values = {
        "prompt_key": "modules",
        "prompt_version": "v2",
        "instructions": "Return a module.",
        "input_text": "<UNTRUSTED_PROJECT_DATA>{}</UNTRUSTED_PROJECT_DATA>",
        "output_type": ModuleDraft,
        "token_budget": 3000,
        "safety_identifier": "safety_8e17f1",
    }
    with pytest.raises(ValueError, match=message):
        StructuredModelRequest(**(values | overrides))


def test_model_usage_rejects_impossible_accounting() -> None:
    with pytest.raises(ValueError, match="negative"):
        ModelUsage(input_tokens=-1)
    with pytest.raises(ValueError, match="lower"):
        ModelUsage(input_tokens=10, output_tokens=5, total_tokens=14)


def test_safety_identifier_is_stable_and_pseudonymous() -> None:
    owner_id = uuid4()
    secret = "test-safety-secret-that-is-longer-than-32-characters"
    identifier = make_safety_identifier(owner_id, secret)
    assert identifier == make_safety_identifier(owner_id, secret)
    assert str(owner_id) not in identifier
    assert identifier.startswith("apm_")
    assert len(identifier) == 64
    with pytest.raises(ValueError, match="at least 32"):
        make_safety_identifier(owner_id, "too-short")


def test_openai_provider_requires_credentials_only_for_real_client() -> None:
    settings = Settings(openai_api_key=None, _env_file=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIResponsesProvider(settings)


def test_openai_provider_leaves_retries_to_the_durable_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_client = cast(AsyncOpenAI, FakeClient(FakeResponses(response())))

    def create_client(**kwargs: Any) -> AsyncOpenAI:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr("app.ai.openai_provider.AsyncOpenAI", create_client)
    settings = Settings(openai_api_key="test-provider-key", _env_file=None)
    OpenAIResponsesProvider(settings)

    assert captured["max_retries"] == 0


def test_openai_adapter_sends_private_strict_request_and_captures_usage() -> None:
    fake_responses = FakeResponses(response())
    result = asyncio.run(provider(fake_responses).generate(request()))

    assert result.output.temp_id == "MOD-001"
    assert result.model == "gpt-5.6-terra-2026-07-01"
    assert result.usage.input_tokens == 100
    assert result.usage.reasoning_tokens == 5
    assert result.usage.cached_input_tokens == 20
    assert result.usage.cache_write_input_tokens == 10
    assert fake_responses.kwargs["store"] is False
    assert fake_responses.kwargs["safety_identifier"] == "safety_8e17f1"
    assert fake_responses.kwargs["text_format"] is ModuleDraft
    assert fake_responses.kwargs["text"] == {"verbosity": "low"}
    assert "verbosity" not in fake_responses.kwargs
    assert fake_responses.kwargs["reasoning"] == {"effort": "low"}


def test_openai_adapter_handles_refusal_without_exposing_content() -> None:
    refusal = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="refusal", refusal="sensitive refusal text")],
    )
    with pytest.raises(ModelRefusalError) as caught:
        asyncio.run(provider(FakeResponses(response(output=[refusal]))).generate(request()))
    assert caught.value.code == ModelFailureCode.REFUSED
    assert "sensitive refusal text" not in str(caught.value)
    assert public_error_details(caught.value) == {
        "code": "refused",
        "retryable": False,
        "response_id": "resp_test",
    }


def test_openai_adapter_handles_truncation() -> None:
    with pytest.raises(ModelTruncatedError) as caught:
        asyncio.run(provider(FakeResponses(response(status="incomplete"))).generate(request()))
    assert caught.value.retryable is True
    assert caught.value.response_id == "resp_test"


def test_openai_adapter_handles_missing_parsed_output() -> None:
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider(FakeResponses(response(output_parsed=None))).generate(request()))
    assert caught.value.code == ModelFailureCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("error", "expected_code", "retryable"),
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            ModelFailureCode.TIMED_OUT,
            True,
        ),
        (
            RateLimitError(
                "rate limited",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            ),
            ModelFailureCode.RATE_LIMITED,
            True,
        ),
        (
            RateLimitError(
                "quota exhausted",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body={
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                    "message": "sensitive provider billing detail",
                },
            ),
            ModelFailureCode.QUOTA_EXHAUSTED,
            False,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            ModelFailureCode.UNAVAILABLE,
            True,
        ),
        (
            APIStatusError(
                "invalid request",
                response=httpx.Response(
                    400,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            ),
            ModelFailureCode.INVALID_RESPONSE,
            False,
        ),
        (
            APIStatusError(
                "server error",
                response=httpx.Response(
                    503,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            ),
            ModelFailureCode.UNAVAILABLE,
            True,
        ),
    ],
)
def test_openai_adapter_maps_retryable_provider_errors(
    error: Exception, expected_code: ModelFailureCode, retryable: bool
) -> None:
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider(FakeResponses(error=error)).generate(request()))
    assert caught.value.code == expected_code
    assert caught.value.retryable is retryable


def test_openai_adapter_tolerates_missing_usage() -> None:
    result = asyncio.run(provider(FakeResponses(response(usage=None))).generate(request()))
    assert result.usage.total_tokens == 0


def test_openai_adapter_rejects_non_strict_schema_before_network() -> None:
    class PermissiveOutput(BaseModel):
        value: str

    invalid_request = StructuredModelRequest(
        prompt_key="modules",
        prompt_version="v2",
        instructions="Return a value.",
        input_text="<UNTRUSTED_PROJECT_DATA>{}</UNTRUSTED_PROJECT_DATA>",
        output_type=PermissiveOutput,
        token_budget=100,
        safety_identifier="safety_8e17f1",
    )
    fake_responses = FakeResponses(response())
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider(fake_responses).generate(invalid_request))
    assert caught.value.code == ModelFailureCode.INVALID_REQUEST
    assert caught.value.retryable is False
    assert fake_responses.kwargs == {}
