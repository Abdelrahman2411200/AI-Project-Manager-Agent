"""OpenAI Responses API adapter with strict parsing and provider-neutral failures."""

from __future__ import annotations

from time import monotonic_ns
from typing import Any, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel

from app.ai.provider import (
    ModelFailureCode,
    ModelRefusalError,
    ModelTruncatedError,
    ModelUsage,
    StructuredModelError,
    StructuredModelRequest,
    StructuredModelResult,
)
from app.core.config import Settings, get_settings


class OpenAIResponsesProvider:
    provider_name = "openai"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if client is not None:
            self._client = client
        else:
            api_key = self._settings.openai_api_key
            if api_key is None:
                raise ValueError("OPENAI_API_KEY is required to construct the OpenAI provider.")
            self._client = AsyncOpenAI(
                api_key=api_key.get_secret_value(),
                timeout=self._settings.openai_timeout_seconds,
            )

    async def generate[StructuredOutputT: BaseModel](
        self, request: StructuredModelRequest[StructuredOutputT]
    ) -> StructuredModelResult[StructuredOutputT]:
        started = monotonic_ns()
        try:
            response = await self._client.responses.parse(
                model=cast(Any, self._settings.openai_model),
                instructions=request.instructions,
                input=request.input_text,
                text_format=request.output_type,
                max_output_tokens=request.token_budget,
                reasoning={"effort": cast(Any, request.reasoning_effort)},
                verbosity=self._settings.openai_verbosity,
                safety_identifier=request.safety_identifier,
                store=False,
                metadata={
                    "prompt_key": request.prompt_key,
                    "prompt_version": request.prompt_version,
                    **request.metadata,
                },
                timeout=self._settings.openai_timeout_seconds,
            )
        except RateLimitError as error:
            raise StructuredModelError(
                ModelFailureCode.RATE_LIMITED,
                "The model provider rate limit was reached.",
                retryable=True,
            ) from error
        except APITimeoutError as error:
            raise StructuredModelError(
                ModelFailureCode.TIMED_OUT,
                "The model provider timed out.",
                retryable=True,
            ) from error
        except APIConnectionError as error:
            raise StructuredModelError(
                ModelFailureCode.UNAVAILABLE,
                "The model provider is unavailable.",
                retryable=True,
            ) from error
        except APIStatusError as error:
            server_failure = error.status_code >= 500
            raise StructuredModelError(
                (
                    ModelFailureCode.UNAVAILABLE
                    if server_failure
                    else ModelFailureCode.INVALID_RESPONSE
                ),
                (
                    "The model provider is unavailable."
                    if server_failure
                    else "The model provider rejected the request."
                ),
                retryable=server_failure,
            ) from error

        response_id = str(response.id)
        if response.status == "incomplete":
            raise ModelTruncatedError(response_id=response_id)
        if self._contains_refusal(response.output):
            raise ModelRefusalError(response_id=response_id)

        parsed = response.output_parsed
        if parsed is None or not isinstance(parsed, request.output_type):
            raise StructuredModelError(
                ModelFailureCode.INVALID_RESPONSE,
                "The model response did not contain the requested structured output.",
                retryable=True,
                response_id=response_id,
            )

        duration_ms = max(0, (monotonic_ns() - started) // 1_000_000)
        return StructuredModelResult(
            output=parsed,
            provider=self.provider_name,
            model=str(response.model),
            response_id=response_id,
            usage=self._read_usage(response.usage),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _contains_refusal(outputs: list[Any]) -> bool:
        for output in outputs:
            if getattr(output, "type", None) != "message":
                continue
            for content in getattr(output, "content", []):
                if getattr(content, "type", None) == "refusal":
                    return True
        return False

    @staticmethod
    def _read_usage(usage: Any) -> ModelUsage:
        if usage is None:
            return ModelUsage()
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return ModelUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
            cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
            cache_write_input_tokens=int(getattr(input_details, "cache_write_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        )


def validate_schema_is_strict(output_type: type[BaseModel]) -> None:
    """Fail startup/tests if a schema permits uncontracted object properties."""

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                raise ValueError(f"Schema object at {path} must forbid additional properties.")
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(output_type.model_json_schema(), "$")
