import asyncio
import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from app.ai.factory import build_structured_model_provider, provider_is_configured
from app.ai.ollama_provider import OllamaStructuredProvider
from app.ai.openai_provider import OpenAIResponsesProvider
from app.ai.provider import (
    ModelFailureCode,
    ModelTruncatedError,
    StructuredModelError,
    StructuredModelRequest,
)
from app.ai.schemas.outputs import (
    ClarificationQuestionBatch,
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraft,
    ProjectAnalysisOutput,
    TaskDraftBatch,
)
from app.core.config import Settings
from tests.ai.fixtures import ANALYSIS, DEPENDENCY, MILESTONE, MODULE, QUESTION, TASK


def module_request() -> StructuredModelRequest[ModuleDraft]:
    return StructuredModelRequest(
        prompt_key="modules",
        prompt_version="v2",
        instructions="Return one valid module as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"requirements":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=ModuleDraft,
        token_budget=3_000,
        safety_identifier="local_test_user",
    )


def dependency_request() -> StructuredModelRequest[DependencySuggestionBatch]:
    return StructuredModelRequest(
        prompt_key="dependencies",
        prompt_version="v2",
        instructions="Return necessary task dependencies as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"tasks":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=DependencySuggestionBatch,
        token_budget=4_000,
        safety_identifier="local_test_user",
    )


def clarification_request() -> StructuredModelRequest[ClarificationQuestionBatch]:
    return StructuredModelRequest(
        prompt_key="clarification",
        prompt_version="v3",
        instructions="Return material clarification questions as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"requirements":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=ClarificationQuestionBatch,
        token_budget=2_000,
        safety_identifier="local_test_user",
    )


def task_request() -> StructuredModelRequest[TaskDraftBatch]:
    return StructuredModelRequest(
        prompt_key="tasks",
        prompt_version="v4",
        instructions="Return actionable tasks as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"milestones":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=TaskDraftBatch,
        token_budget=8_000,
        safety_identifier="local_test_user",
    )


def milestone_request() -> StructuredModelRequest[MilestoneDraftBatch]:
    return StructuredModelRequest(
        prompt_key="milestones",
        prompt_version="v4",
        instructions="Return deliverable-based milestones as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"modules":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=MilestoneDraftBatch,
        token_budget=4_000,
        safety_identifier="local_test_user",
    )


def analysis_request() -> StructuredModelRequest[ProjectAnalysisOutput]:
    return StructuredModelRequest(
        prompt_key="analysis",
        prompt_version="v2",
        instructions="Return a grounded project analysis as JSON.",
        input_text='<UNTRUSTED_PROJECT_DATA>{"requirements":[]}</UNTRUSTED_PROJECT_DATA>',
        output_type=ProjectAnalysisOutput,
        token_budget=6_000,
        safety_identifier="local_test_user",
    )


def settings(**overrides: Any) -> Settings:
    return Settings(
        ai_provider="ollama",
        ollama_base_url="http://ollama.test:11434",
        ollama_model="gemma3:4b",
        ollama_context_tokens=8_192,
        ollama_max_output_tokens=2_048,
        ollama_schema_retries=1,
        _env_file=None,
        **overrides,
    )


def chat_response(
    output: dict[str, Any],
    *,
    prompt_tokens: int = 10,
    output_tokens: int = 5,
    done: bool = True,
    done_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gemma3:4b",
            "message": {"role": "assistant", "content": json.dumps(output)},
            "done": done,
            "done_reason": done_reason,
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
        },
    )


def test_ollama_adapter_sends_native_structured_request_and_tracks_usage() -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return chat_response(MODULE, prompt_tokens=12, output_tokens=8)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    result = asyncio.run(provider.generate(module_request()))
    asyncio.run(client.aclose())

    assert result.provider == "ollama"
    assert result.model == "gemma3:4b"
    assert result.output.temp_id == "MOD-001"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 8
    assert result.usage.total_tokens == 20
    body = captured[0]
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"] == ModuleDraft.model_json_schema()
    assert body["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "num_ctx": 8_192,
        "num_predict": 2_048,
    }
    assert "local_test_user" not in request_text(captured)


def test_ollama_adapter_repairs_one_schema_error_and_diversifies_seed() -> None:
    calls: list[dict[str, Any]] = []
    invalid = {"items": [{**DEPENDENCY, "reason": "short"}]}
    responses = [chat_response(invalid), chat_response({"items": []}, prompt_tokens=8)]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return responses.pop(0)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    result = asyncio.run(provider.generate(dependency_request()))
    asyncio.run(client.aclose())

    assert result.output.items == []
    assert result.usage.total_tokens == 28
    assert len(calls) == 2
    assert len(calls[1]["messages"]) == 4
    assert "failed local schema validation" in calls[1]["messages"][-1]["content"]
    assert calls[0]["options"]["seed"] == 42
    assert calls[1]["options"]["seed"] == 43
    assert "supplied JSON Schema is the only shape example" in calls[0]["messages"][0]["content"]
    assert "Never copy identifiers" in calls[0]["messages"][0]["content"]


def test_ollama_adapter_removes_domain_bearing_prompt_examples() -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return chat_response(MODULE)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    request = replace(
        module_request(),
        instructions=(
            "Ground the module in current facts.\n"
            "Valid structured-output example:\n"
            '{"name":"Checkout","requirement_refs":["REQ-COMMERCE"]}\n'
            "Adversarial behavior example:\nDo not copy it."
        ),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    asyncio.run(provider.generate(request))
    asyncio.run(client.aclose())

    system_message = captured[0]["messages"][0]["content"]
    assert "Ground the module in current facts." in system_message
    assert "Checkout" not in system_message
    assert "REQ-COMMERCE" not in system_message
    assert "schema is supplied separately" in system_message


def test_ollama_adapter_drops_self_edges_without_a_model_retry() -> None:
    calls: list[dict[str, Any]] = []
    invalid = {"items": [{**DEPENDENCY, "successor_ref": "TASK-001"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return chat_response(invalid)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaStructuredProvider(
        settings().model_copy(update={"ollama_schema_retries": 0}), client=client
    )
    result = asyncio.run(provider.generate(dependency_request()))
    asyncio.run(client.aclose())

    assert result.output.items == []
    assert len(calls) == 1


def test_ollama_adapter_downgrades_incomplete_choices_and_labels_assumptions() -> None:
    incomplete = {
        "items": [
            {
                **QUESTION,
                "answer_type": "single_choice",
                "options": [],
                "default_assumption": "The owner approves the draft",
            }
        ]
    }
    incomplete["items"][0].pop("options")
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(lambda _request: chat_response(incomplete)),
    )
    provider = OllamaStructuredProvider(
        settings().model_copy(update={"ollama_schema_retries": 0}), client=client
    )
    result = asyncio.run(provider.generate(clarification_request()))
    asyncio.run(client.aclose())

    question = result.output.items[0]
    assert question.answer_type == "text"
    assert question.options == []
    assert question.default_assumption == "Assumption: The owner approves the draft"


def test_ollama_adapter_bounds_leaf_likely_effort_and_preserves_upper_range() -> None:
    oversized = {
        "items": [
            {
                **TASK,
                "effort_min_hours": 32,
                "effort_likely_hours": 40,
                "effort_max_hours": 48,
            }
        ]
    }
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(lambda _request: chat_response(oversized)),
    )
    provider = OllamaStructuredProvider(
        settings().model_copy(update={"ollama_schema_retries": 0}), client=client
    )
    result = asyncio.run(provider.generate(task_request()))
    asyncio.run(client.aclose())

    task = result.output.items[0]
    assert task.effort_min_hours == 24
    assert task.effort_likely_hours == 24
    assert task.effort_max_hours == 48


def test_ollama_adapter_uses_minimum_positive_milestone_effort() -> None:
    zero_effort = {"items": [{**MILESTONE, "planned_effort_hours": 0}]}
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(lambda _request: chat_response(zero_effort)),
    )
    provider = OllamaStructuredProvider(
        settings().model_copy(update={"ollama_schema_retries": 0}), client=client
    )
    result = asyncio.run(provider.generate(milestone_request()))
    asyncio.run(client.aclose())

    assert result.output.items[0].planned_effort_hours == 1


def test_ollama_adapter_normalizes_nested_analysis_questions() -> None:
    incomplete_question = {**QUESTION, "answer_type": "single_choice"}
    incomplete_question.pop("options")
    duplicate_module = {
        **MODULE,
        "temp_id": "MOD-002",
        "name": "Duplicate objective module",
    }
    analysis = {
        **ANALYSIS,
        "open_questions": [incomplete_question],
        "modules": [MODULE, duplicate_module],
    }
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(lambda _request: chat_response(analysis)),
    )
    provider = OllamaStructuredProvider(
        settings().model_copy(update={"ollama_schema_retries": 0}), client=client
    )
    result = asyncio.run(provider.generate(analysis_request()))
    asyncio.run(client.aclose())

    question = result.output.open_questions[0]
    assert question.answer_type == "text"
    assert question.options == []
    assert [module.temp_id for module in result.output.modules] == ["MOD-001"]


def test_ollama_adapter_rejects_invalid_output_after_bounded_repair() -> None:
    invalid = {"items": [{**DEPENDENCY, "reason": "short"}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return chat_response(invalid)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider.generate(dependency_request()))
    asyncio.run(client.aclose())

    assert caught.value.code is ModelFailureCode.INVALID_RESPONSE
    assert caught.value.retryable is False


def test_ollama_adapter_maps_truncation() -> None:
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(lambda _request: chat_response(MODULE, done_reason="length")),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    with pytest.raises(ModelTruncatedError):
        asyncio.run(provider.generate(module_request()))
    asyncio.run(client.aclose())


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (404, ModelFailureCode.INVALID_REQUEST, False),
        (429, ModelFailureCode.RATE_LIMITED, True),
        (503, ModelFailureCode.UNAVAILABLE, True),
        (400, ModelFailureCode.INVALID_REQUEST, False),
    ],
)
def test_ollama_adapter_maps_http_errors(
    status: int, code: ModelFailureCode, retryable: bool
) -> None:
    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status, json={"error": "sensitive detail"})
        ),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider.generate(module_request()))
    asyncio.run(client.aclose())

    assert caught.value.code is code
    assert caught.value.retryable is retryable
    assert "sensitive" not in str(caught.value)


def test_ollama_adapter_maps_connection_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive address", request=request)

    client = httpx.AsyncClient(
        base_url="http://ollama.test:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaStructuredProvider(settings(), client=client)
    with pytest.raises(StructuredModelError) as caught:
        asyncio.run(provider.generate(module_request()))
    asyncio.run(client.aclose())

    assert caught.value.code is ModelFailureCode.UNAVAILABLE
    assert caught.value.retryable is True
    assert "sensitive" not in str(caught.value)


def test_provider_factory_selects_local_openai_or_none() -> None:
    local_settings = settings()
    local = build_structured_model_provider(local_settings)
    assert isinstance(local, OllamaStructuredProvider)
    assert provider_is_configured(local_settings) is True
    asyncio.run(local.close())

    openai_settings = Settings(
        ai_provider="openai", openai_api_key="test-provider-key", _env_file=None
    )
    hosted = build_structured_model_provider(openai_settings)
    assert isinstance(hosted, OpenAIResponsesProvider)
    asyncio.run(hosted.close())

    disabled = Settings(ai_provider="none", _env_file=None)
    assert build_structured_model_provider(disabled) is None
    assert provider_is_configured(disabled) is False


def request_text(captured: list[dict[str, Any]]) -> str:
    return json.dumps(captured, separators=(",", ":"))
