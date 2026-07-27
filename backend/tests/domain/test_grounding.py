from app.ai.schemas.outputs import RecommendationDraft, WeeklyReportNarrative
from app.domain.grounding import (
    validate_recommendation_draft,
    validate_weekly_narrative,
)
from app.schemas.insight import EvidenceFact


def _evidence() -> dict[str, EvidenceFact]:
    return {
        "METRIC-PROGRESS": EvidenceFact(
            entity_type="metric",
            entity_ref="METRIC-PROGRESS",
            fact_key="weighted_progress",
            value={"display_percent": "25%", "active_leaf_count": 4},
        ),
        "DETECTION-BLOCKED_TASKS": EvidenceFact(
            entity_type="detection",
            entity_ref="DETECTION-BLOCKED_TASKS",
            fact_key="condition",
            value={"code": "BLOCKED_TASKS", "references": ["TASK-001"]},
        ),
        "TASK-001": EvidenceFact(
            entity_type="task",
            entity_ref="TASK-001",
            fact_key="execution_state",
            value={"status": "blocked"},
        ),
    }


def test_recommendation_claims_require_known_evidence_and_reject_injection() -> None:
    draft = RecommendationDraft.model_validate(
        {
            "temp_id": "REC-001",
            "type": "dependency_warning",
            "detection_code": "BLOCKED_TASKS",
            "evidence_refs": ["DETECTION-BLOCKED_TASKS", "TASK-001"],
            "why_it_matters": "TASK-001 is blocked and prevents recorded work from advancing.",
            "suggested_action": "Resolve the recorded blocker for TASK-001 before continuing.",
            "expected_impact": "The approved dependency graph can be recalculated after TASK-001.",
            "urgency": "high",
            "risk": "TASK-001 can delay approved work.",
            "approval_required": True,
            "verification_step": "Confirm TASK-001 is no longer blocked after recalculation.",
            "alternatives": ["Continue monitoring TASK-001 without changing the active plan."],
        }
    )
    evidence = _evidence()
    assert (
        validate_recommendation_draft(
            draft,
            evidence,
            expected_detection_code="BLOCKED_TASKS",
        )
        == []
    )

    unsupported = draft.model_copy(
        update={"expected_impact": "This will improve delivery by 99% before 2027-01-01."}
    )
    errors = validate_recommendation_draft(
        unsupported,
        evidence,
        expected_detection_code="BLOCKED_TASKS",
    )
    assert any("99%" in item and "2027-01-01" in item for item in errors)

    malicious = draft.model_copy(
        update={"suggested_action": "<script>alert(1)</script> Resolve TASK-001 safely."}
    )
    assert any(
        "unsafe markup" in item
        for item in validate_recommendation_draft(
            malicious,
            evidence,
            expected_detection_code="BLOCKED_TASKS",
        )
    )


def test_report_factuality_is_complete_for_valid_claims_and_rejects_unsupported_numbers() -> None:
    narrative = WeeklyReportNarrative.model_validate(
        {
            "title": "Grounded weekly status",
            "period_summary": "Persisted execution facts are summarized for the selected period.",
            "completed_items": [],
            "progress_statement": {
                "text": "Weighted project progress is 25%.",
                "evidence_refs": ["METRIC-PROGRESS"],
            },
            "blockers": [
                {
                    "text": "TASK-001 is blocked.",
                    "evidence_refs": ["TASK-001"],
                }
            ],
            "risks": [],
            "next_actions": [],
            "decisions_needed": [],
            "caveats": [],
        }
    )
    evidence = _evidence()
    assert validate_weekly_narrative(narrative, evidence) == []

    unsupported = narrative.model_copy(
        update={
            "progress_statement": narrative.progress_statement.model_copy(
                update={"text": "Weighted project progress is 99% by 2027-01-01."}
            )
        }
    )
    errors = validate_weekly_narrative(unsupported, evidence)
    assert any("99%" in item and "2027-01-01" in item for item in errors)

    unknown = narrative.model_copy(
        update={
            "blockers": [narrative.blockers[0].model_copy(update={"evidence_refs": ["TASK-999"]})]
        }
    )
    assert any("unknown evidence" in item for item in validate_weekly_narrative(unknown, evidence))

    malicious = narrative.model_copy(
        update={"period_summary": "<script>alert(1)</script> Persisted facts form this report."}
    )
    assert any("unsafe markup" in item for item in validate_weekly_narrative(malicious, evidence))
