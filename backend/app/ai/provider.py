"""Provider-neutral contracts for schema-constrained model calls."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel


class ModelFailureCode(StrEnum):
    REFUSED = "refused"
    TRUNCATED = "truncated"
    RATE_LIMITED = "rate_limited"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


class StructuredModelError(RuntimeError):
    """Base error safe to expose to workflow code without provider details."""

    def __init__(
        self,
        code: ModelFailureCode,
        message: str,
        *,
        retryable: bool,
        response_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.response_id = response_id


class ModelRefusalError(StructuredModelError):
    def __init__(self, *, response_id: str | None = None) -> None:
        super().__init__(
            ModelFailureCode.REFUSED,
            "The model declined to produce this structured output.",
            retryable=False,
            response_id=response_id,
        )


class ModelTruncatedError(StructuredModelError):
    def __init__(self, *, response_id: str | None = None) -> None:
        super().__init__(
            ModelFailureCode.TRUNCATED,
            "The model response ended before the structured output was complete.",
            retryable=True,
            response_id=response_id,
        )


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class StructuredModelRequest[StructuredOutputT: BaseModel]:
    prompt_key: str
    prompt_version: str
    instructions: str
    input_text: str
    output_type: type[StructuredOutputT]
    token_budget: int
    safety_identifier: str
    reasoning_effort: str = "low"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StructuredModelResult[StructuredOutputT: BaseModel]:
    output: StructuredOutputT
    provider: str
    model: str
    response_id: str
    usage: ModelUsage
    duration_ms: int


class StructuredModelProvider(Protocol):
    async def generate[StructuredOutputT: BaseModel](
        self, request: StructuredModelRequest[StructuredOutputT]
    ) -> StructuredModelResult[StructuredOutputT]:
        """Return a schema-constrained candidate without performing persistence."""
        ...


def public_error_details(error: StructuredModelError) -> dict[str, Any]:
    """Return a log-safe error payload that never includes prompt or model output."""
    return {
        "code": error.code.value,
        "retryable": error.retryable,
        "response_id": error.response_id,
    }


def make_safety_identifier(owner_id: UUID, secret: str) -> str:
    """Create a stable pseudonymous identifier without sending a database ID."""
    if len(secret) < 32:
        raise ValueError("Safety identifier secret must contain at least 32 characters.")
    digest = hmac.new(
        secret.encode("utf-8"),
        str(owner_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"apm_{digest}"
