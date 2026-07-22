from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StructuredModelRequest:
    prompt_key: str
    prompt_version: str
    context: dict[str, Any]
    output_schema: dict[str, Any]
    token_budget: int


@dataclass(frozen=True, slots=True)
class StructuredModelResult:
    output: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class StructuredModelProvider(Protocol):
    async def generate(self, request: StructuredModelRequest) -> StructuredModelResult:
        """Return a schema-constrained candidate without performing persistence."""
        ...
