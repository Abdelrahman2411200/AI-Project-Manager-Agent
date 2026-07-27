"""Provider-neutral contracts for schema-constrained model calls."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel


class ModelFailureCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
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

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.cached_input_tokens,
            self.cache_write_input_tokens,
            self.total_tokens,
        )
        if any(value < 0 for value in values):
            raise ValueError("Model usage token counts cannot be negative.")
        if self.total_tokens and self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("Total tokens cannot be lower than input plus output tokens.")


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

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", self.prompt_key):
            raise ValueError("prompt_key must be a stable lowercase identifier.")
        if not re.fullmatch(r"v[1-9][0-9]{0,5}", self.prompt_version):
            raise ValueError("prompt_version must use the vN form.")
        if not self.instructions.strip() or not self.input_text.strip():
            raise ValueError("Structured model instructions and input cannot be empty.")
        if not 1 <= self.token_budget <= 128_000:
            raise ValueError("token_budget must be between 1 and 128000.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", self.safety_identifier):
            raise ValueError("safety_identifier must be a safe pseudonymous identifier.")
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported reasoning_effort.")
        if len(self.metadata) > 16:
            raise ValueError("Model request metadata cannot contain more than 16 entries.")
        for key, value in self.metadata.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key):
                raise ValueError("Model request metadata contains an invalid key.")
            if not isinstance(value, str) or len(value) > 512:
                raise ValueError("Model request metadata values must be strings up to 512 chars.")


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
