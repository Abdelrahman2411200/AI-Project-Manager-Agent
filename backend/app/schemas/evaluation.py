"""Authenticated evaluation-dashboard response contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationFixtureView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=3, max_length=120)
    metrics: dict[str, float | bool]
    passed: bool


class EvaluationDashboardView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    dataset_version: str
    dataset_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    fixture_source: str
    fixture_count: int = Field(ge=1)
    pass_count: int = Field(ge=0)
    release_status: Literal["passed", "failed"]
    thresholds: dict[str, str]
    summary: dict[str, float]
    fixtures: list[EvaluationFixtureView]
