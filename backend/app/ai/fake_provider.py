"""Deterministic provider used by tests and local workflow development."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from time import monotonic_ns
from typing import Any

from pydantic import BaseModel

from app.ai.provider import (
    ModelUsage,
    StructuredModelError,
    StructuredModelRequest,
    StructuredModelResult,
)


class FakeStructuredModelProvider:
    """Return queued outputs while enforcing the same Pydantic contract as production."""

    def __init__(
        self,
        outputs: Iterable[dict[str, Any] | BaseModel | StructuredModelError],
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
        candidate = self._outputs.popleft()
        if isinstance(candidate, StructuredModelError):
            raise candidate
        if isinstance(candidate, request.output_type):
            parsed = candidate
        elif isinstance(candidate, BaseModel):
            parsed = request.output_type.model_validate(candidate.model_dump(mode="json"))
        else:
            parsed = request.output_type.model_validate(candidate)
        return StructuredModelResult(
            output=parsed,
            provider="fake",
            model=self.model,
            response_id=f"fake-{len(self.requests):04d}",
            usage=ModelUsage(),
            duration_ms=max(0, (monotonic_ns() - started) // 1_000_000),
        )
