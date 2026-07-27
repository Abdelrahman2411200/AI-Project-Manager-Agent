import asyncio
from uuid import uuid4

import pytest

from app.ai.fake_provider import FakeStructuredModelProvider
from app.ai.schemas.outputs import GroundedExplanation
from app.core.config import get_settings
from app.db.models.identity import User
from app.db.session import SessionLocal
from app.domain.grounding import validate_grounded_explanation
from app.services.advanced_explanations import (
    AdvancedExplanationGroundingError,
    AdvancedExplanationService,
)


def test_grounded_explanation_accepts_exact_metrics_and_rejects_invention() -> None:
    evidence = {
        "RESULT-DELTA": {
            "forecast_finish_days": -4,
            "effort_hours": "0.00",
        }
    }
    valid = GroundedExplanation(
        summary="The supplied forecast finishes 4 days earlier.",
        evidence_refs=["RESULT-DELTA"],
        tradeoffs=["Effort remains at 0.00 additional hours."],
        approval_required=True,
    )
    invented = GroundedExplanation(
        summary="The supplied forecast finishes 9 days earlier.",
        evidence_refs=["RESULT-DELTA"],
        tradeoffs=["Effort remains at 0.00 additional hours."],
        approval_required=True,
    )

    assert validate_grounded_explanation(valid, evidence) == []
    assert "Unsupported factual tokens" in validate_grounded_explanation(invented, evidence)[0]


def test_advanced_explanation_provider_receives_only_deterministic_result() -> None:
    with SessionLocal() as session:
        user = User(
            email="advanced-explanation@example.com",
            password_hash="not-used-in-this-test",
        )
        session.add(user)
        session.commit()
        provider = FakeStructuredModelProvider(
            [
                {
                    "summary": "The supplied forecast finishes 4 days earlier.",
                    "evidence_refs": ["RESULT-DELTA"],
                    "tradeoffs": ["Effort remains at 0.00 additional hours."],
                    "approval_required": True,
                }
            ]
        )
        explanation, _ = asyncio.run(
            AdvancedExplanationService(session, user.id, "advanced-request").generate(
                kind="scenario",
                deterministic_result={
                    "baseline": {"forecast_finish": "2026-08-20"},
                    "scenario": {"forecast_finish": "2026-08-16"},
                    "delta": {
                        "forecast_finish_days": -4,
                        "effort_hours": "0.00",
                    },
                    "sources": {"baseline_content_hash": "sha256:abc"},
                },
                provider=provider,
                settings=get_settings(),
                artifact_id=uuid4(),
            )
        )
        assert explanation.approval_required is True
        assert provider.requests[0].prompt_key == "scenario"
        assert "active-write" not in provider.requests[0].input_text


def test_advanced_explanation_rejects_unsupported_model_claim() -> None:
    with SessionLocal() as session:
        user = User(
            email="advanced-explanation-bad@example.com",
            password_hash="not-used-in-this-test",
        )
        session.add(user)
        session.commit()
        provider = FakeStructuredModelProvider(
            [
                {
                    "summary": "The forecast improves by 99 days.",
                    "evidence_refs": ["RESULT-DELTA"],
                    "tradeoffs": ["Capacity is 30 hours."],
                    "approval_required": True,
                }
            ]
        )
        with pytest.raises(AdvancedExplanationGroundingError):
            asyncio.run(
                AdvancedExplanationService(session, user.id, "advanced-bad").generate(
                    kind="change_impact",
                    deterministic_result={"delta": {"forecast_finish_days": -4}},
                    provider=provider,
                    settings=get_settings(),
                    artifact_id=uuid4(),
                )
            )
