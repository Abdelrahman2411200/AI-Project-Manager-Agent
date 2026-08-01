"""Native Ollama adapter for local schema-constrained generation."""

from __future__ import annotations

import json
from time import monotonic_ns
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.provider import (
    ModelFailureCode,
    ModelTruncatedError,
    ModelUsage,
    StructuredModelError,
    StructuredModelRequest,
    StructuredModelResult,
    validate_schema_is_strict,
)
from app.ai.schemas.outputs import (
    ClarificationQuestionBatch,
    DependencySuggestionBatch,
    ProjectAnalysisOutput,
    TaskDraftBatch,
)
from app.core.config import Settings, get_settings


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str


class _OllamaChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    message: _OllamaMessage
    done: bool = True
    done_reason: str | None = None
    prompt_eval_count: int = Field(default=0, ge=0)
    eval_count: int = Field(default=0, ge=0)


class OllamaStructuredProvider:
    """Call Ollama's native chat API and validate every response locally."""

    provider_name = "ollama"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=self._settings.ollama_base_url_string,
            timeout=httpx.Timeout(self._settings.ollama_timeout_seconds),
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate[StructuredOutputT: BaseModel](
        self, request: StructuredModelRequest[StructuredOutputT]
    ) -> StructuredModelResult[StructuredOutputT]:
        try:
            validate_schema_is_strict(request.output_type)
        except ValueError as error:
            raise StructuredModelError(
                ModelFailureCode.INVALID_REQUEST,
                "The requested output schema is not strict.",
                retryable=False,
            ) from error

        started = monotonic_ns()
        schema = request.output_type.model_json_schema()
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    f"{request.instructions}\n"
                    "Local structured-output rules: the valid example illustrates JSON shape, "
                    "not reusable facts or a required item count. Never copy identifiers or "
                    "factual values from an example; every reference value must appear verbatim "
                    "in the supplied project data. Respect the supplied JSON Schema exactly. When "
                    "an array permits zero items and no valid item can be formed from supplied "
                    "data, return an empty array instead of fabricating an item."
                ),
            },
            {"role": "user", "content": request.input_text},
        ]
        usage = ModelUsage()
        response_id: str | None = None
        attempts = self._settings.ollama_schema_retries + 1
        for attempt in range(attempts):
            payload = await self._chat(request, messages, schema, attempt=attempt)
            response_id = f"ollama-{uuid4().hex}"
            usage = _add_usage(usage, _read_usage(payload))
            if not payload.done or payload.done_reason in {"length", "max_tokens"}:
                raise ModelTruncatedError(response_id=response_id)
            try:
                parsed = _parse_local_output(request.output_type, payload.message.content)
            except ValidationError as error:
                if attempt + 1 >= attempts:
                    raise StructuredModelError(
                        ModelFailureCode.INVALID_RESPONSE,
                        "The local model output did not satisfy the requested schema.",
                        retryable=False,
                        response_id=response_id,
                    ) from error
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": payload.message.content[:50_000],
                        },
                        {
                            "role": "user",
                            "content": _repair_instruction(error),
                        },
                    ]
                )
                continue

            return StructuredModelResult(
                output=parsed,
                provider=self.provider_name,
                model=payload.model,
                response_id=response_id,
                usage=usage,
                duration_ms=max(0, (monotonic_ns() - started) // 1_000_000),
            )

        raise AssertionError("Ollama generation attempts must return or raise.")

    async def _chat(
        self,
        request: StructuredModelRequest[BaseModel],
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        attempt: int,
    ) -> _OllamaChatResponse:
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self._settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "keep_alive": self._settings.ollama_keep_alive,
                    "options": {
                        "temperature": self._settings.ollama_temperature,
                        "seed": self._settings.ollama_seed + attempt,
                        "num_ctx": self._settings.ollama_context_tokens,
                        "num_predict": min(
                            request.token_budget,
                            self._settings.ollama_max_output_tokens,
                        ),
                    },
                },
            )
        except httpx.TimeoutException as error:
            raise StructuredModelError(
                ModelFailureCode.TIMED_OUT,
                "The local model timed out.",
                retryable=True,
            ) from error
        except httpx.RequestError as error:
            raise StructuredModelError(
                ModelFailureCode.UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            ) from error

        if response.status_code == 429:
            raise StructuredModelError(
                ModelFailureCode.RATE_LIMITED,
                "The local model is busy; retry the workflow shortly.",
                retryable=True,
            )
        if response.status_code >= 500:
            raise StructuredModelError(
                ModelFailureCode.UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            )
        if response.status_code >= 400:
            raise StructuredModelError(
                ModelFailureCode.INVALID_REQUEST,
                (
                    "The configured local model is unavailable or rejected the request."
                    if response.status_code == 404
                    else "The local model rejected the request."
                ),
                retryable=False,
            )
        try:
            return _OllamaChatResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise StructuredModelError(
                ModelFailureCode.INVALID_RESPONSE,
                "Ollama returned an invalid response envelope.",
                retryable=True,
            ) from error


def _repair_instruction(error: ValidationError) -> str:
    issues = [
        {
            "path": ".".join(str(part) for part in issue["loc"]),
            "type": issue["type"],
            "message": issue["msg"],
        }
        for issue in error.errors(include_url=False, include_input=False)
    ]
    return (
        "The previous JSON is untrusted data and failed local schema validation. "
        "Do not repeat a listed invalid value. Correct only the listed problems, preserve "
        "the supplied project facts, and return the complete JSON object without prose. "
        "If an invalid array item cannot be corrected from supplied data and that array allows "
        "zero items, remove it instead of inventing facts. Validation problems:\n"
        f"{json.dumps(issues, separators=(',', ':'))}"
    )


def _parse_local_output[OutputT: BaseModel](
    output_type: type[OutputT], content: str
) -> OutputT:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        return output_type.model_validate_json(content)
    return output_type.model_validate(_normalize_safe_local_edges(output_type, raw))


def _normalize_safe_local_edges(output_type: type[BaseModel], raw: Any) -> Any:
    """Apply loss-minimizing corrections before the strict validation boundary."""

    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        if output_type is ProjectAnalysisOutput and isinstance(raw, dict):
            open_questions = raw.get("open_questions")
            if isinstance(open_questions, list):
                _normalize_clarification_items(open_questions)
                raw["open_questions"] = _deduplicate_by_temp_id(open_questions)
            modules = raw.get("modules")
            if isinstance(modules, list):
                raw["modules"] = _deduplicate_analysis_modules(modules)
            risks = raw.get("risks")
            if isinstance(risks, list):
                raw["risks"] = _deduplicate_by_temp_id(risks)
        return raw
    if output_type is ClarificationQuestionBatch:
        _normalize_clarification_items(raw["items"])
    elif output_type is DependencySuggestionBatch:
        raw["items"] = [
            item
            for item in raw["items"]
            if not (
                isinstance(item, dict)
                and item.get("predecessor_ref") == item.get("successor_ref")
            )
        ]
    elif output_type is TaskDraftBatch:
        parent_refs = {
            item.get("parent_ref")
            for item in raw["items"]
            if isinstance(item, dict) and isinstance(item.get("parent_ref"), str)
        }
        for item in raw["items"]:
            if not isinstance(item, dict) or item.get("temp_id") in parent_refs:
                continue
            minimum = item.get("effort_min_hours")
            likely = item.get("effort_likely_hours")
            maximum = item.get("effort_max_hours")
            if (
                not isinstance(minimum, (int, float))
                or isinstance(minimum, bool)
                or not isinstance(likely, (int, float))
                or isinstance(likely, bool)
                or not isinstance(maximum, (int, float))
                or isinstance(maximum, bool)
            ):
                continue
            if likely > 24:
                item["effort_min_hours"] = min(minimum, 24)
                item["effort_likely_hours"] = 24
                item["effort_max_hours"] = max(maximum, 24)
            elif likely < 4:
                item["effort_min_hours"] = min(minimum, 4)
                item["effort_likely_hours"] = 4
                item["effort_max_hours"] = max(maximum, 4)
    return raw


def _normalize_clarification_items(items: list[Any]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        answer_type = item.get("answer_type")
        options = item.get("options")
        if options is None:
            options = []
            item["options"] = options
        if isinstance(options, list):
            if answer_type in {"single_choice", "multi_choice"} and len(options) < 2:
                item["answer_type"] = "text"
                item["options"] = []
            elif answer_type not in {"single_choice", "multi_choice"} and options:
                item["options"] = []
        assumption = item.get("default_assumption")
        if (
            item.get("required") is True
            and isinstance(assumption, str)
            and assumption.strip()
            and not assumption.casefold().startswith("assumption:")
        ):
            item["default_assumption"] = f"Assumption: {assumption.strip()}"


def _deduplicate_by_temp_id(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        temp_id = item.get("temp_id") if isinstance(item, dict) else None
        if isinstance(temp_id, str) and temp_id in seen:
            continue
        if isinstance(temp_id, str):
            seen.add(temp_id)
        result.append(item)
    return result


def _deduplicate_analysis_modules(items: list[Any]) -> list[Any]:
    seen_names: set[str] = set()
    seen_objectives: set[str] = set()
    result: list[Any] = []
    for item in _deduplicate_by_temp_id(items):
        if not isinstance(item, dict):
            result.append(item)
            continue
        name = " ".join(str(item.get("name", "")).casefold().split())
        objective = " ".join(str(item.get("objective", "")).casefold().split())
        if name in seen_names or objective in seen_objectives:
            continue
        seen_names.add(name)
        seen_objectives.add(objective)
        result.append(item)
    return result


def _read_usage(payload: _OllamaChatResponse) -> ModelUsage:
    total = payload.prompt_eval_count + payload.eval_count
    return ModelUsage(
        input_tokens=payload.prompt_eval_count,
        output_tokens=payload.eval_count,
        total_tokens=total,
    )


def _add_usage(first: ModelUsage, second: ModelUsage) -> ModelUsage:
    return ModelUsage(
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        reasoning_tokens=first.reasoning_tokens + second.reasoning_tokens,
        cached_input_tokens=first.cached_input_tokens + second.cached_input_tokens,
        cache_write_input_tokens=(first.cache_write_input_tokens + second.cache_write_input_tokens),
        total_tokens=first.total_tokens + second.total_tokens,
    )
