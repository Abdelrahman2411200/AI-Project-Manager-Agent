"""Safe live provider probe used by the local demo configuration helper."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.openai_provider import OpenAIResponsesProvider
from app.ai.provider import (
    ModelFailureCode,
    StructuredModelError,
    StructuredModelProvider,
    StructuredModelRequest,
)
from app.core.config import get_settings


class ProviderProbeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: Literal[True]


class ProviderProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unconfigured", "quota_exhausted", "provider_error"]
    failure_code: str | None = None
    retryable: bool = False
    model: str | None = None
    total_tokens: int = 0


async def probe_provider(provider: StructuredModelProvider) -> ProviderProbeResult:
    """Exercise the same structured Responses API path used by planning nodes."""

    try:
        result = await provider.generate(
            StructuredModelRequest(
                prompt_key="provider_probe",
                prompt_version="v1",
                instructions="Return ready=true. Do not add prose.",
                input_text='<UNTRUSTED_PROJECT_DATA>{"probe":"configuration"}</UNTRUSTED_PROJECT_DATA>',
                output_type=ProviderProbeOutput,
                token_budget=128,
                safety_identifier="local_demo_probe",
                reasoning_effort="none",
                metadata={"purpose": "configuration_probe"},
            )
        )
    except StructuredModelError as error:
        if error.code is ModelFailureCode.QUOTA_EXHAUSTED:
            return ProviderProbeResult(
                status="quota_exhausted",
                failure_code=error.code.value,
                retryable=False,
            )
        return ProviderProbeResult(
            status="provider_error",
            failure_code=error.code.value,
            retryable=error.retryable,
        )

    return ProviderProbeResult(
        status="ready",
        model=result.model,
        total_tokens=result.usage.total_tokens,
    )


async def run_cli() -> int:
    settings = get_settings()
    if settings.openai_api_key is None:
        print(ProviderProbeResult(status="unconfigured").model_dump_json())
        return 2

    provider = OpenAIResponsesProvider(settings)
    try:
        result = await probe_provider(provider)
    finally:
        await provider.close()

    print(result.model_dump_json())
    return {
        "ready": 0,
        "unconfigured": 2,
        "quota_exhausted": 3,
        "provider_error": 4,
    }[result.status]


def main() -> None:
    raise SystemExit(asyncio.run(run_cli()))


if __name__ == "__main__":
    main()
