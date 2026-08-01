"""Deterministic provider used by tests and local workflow development."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any

from pydantic import BaseModel

from app.ai.provider import (
    ModelUsage,
    StructuredModelError,
    StructuredModelRequest,
    StructuredModelResult,
)


@dataclass(frozen=True, slots=True)
class FakeModelResponse:
    """Scripted provider result with realistic usage and response metadata."""

    output: dict[str, Any] | BaseModel
    usage: ModelUsage = field(default_factory=ModelUsage)
    model: str | None = None
    response_id: str | None = None
    duration_ms: int = 0


class FakeStructuredModelProvider:
    """Return queued outputs while enforcing the same Pydantic contract as production."""

    def __init__(
        self,
        outputs: Iterable[dict[str, Any] | BaseModel | StructuredModelError | FakeModelResponse],
        *,
        model: str = "fake-structured-model",
    ) -> None:
        self._outputs = deque(outputs)
        self.model = model
        self.requests: list[StructuredModelRequest[Any]] = []

    async def generate[StructuredOutputT: BaseModel](
        self, request: StructuredModelRequest[StructuredOutputT]
    ) -> StructuredModelResult[StructuredOutputT]:
        started = monotonic_ns()
        self.requests.append(request)
        if not self._outputs:
            raise RuntimeError("Fake provider has no queued output.")
        scripted = self._outputs.popleft()
        if isinstance(scripted, StructuredModelError):
            raise scripted
        response = scripted if isinstance(scripted, FakeModelResponse) else None
        candidate = response.output if response is not None else scripted
        if isinstance(candidate, request.output_type):
            parsed = candidate
        elif isinstance(candidate, BaseModel):
            parsed = request.output_type.model_validate(candidate.model_dump(mode="json"))
        else:
            parsed = request.output_type.model_validate(candidate)
        return StructuredModelResult(
            output=parsed,
            provider="fake",
            model=response.model if response and response.model else self.model,
            response_id=(
                response.response_id
                if response and response.response_id
                else f"fake-{len(self.requests):04d}"
            ),
            usage=response.usage if response else ModelUsage(),
            duration_ms=(
                response.duration_ms
                if response
                else max(0, (monotonic_ns() - started) // 1_000_000)
            ),
        )

    async def close(self) -> None:
        return None
