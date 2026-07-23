from copy import deepcopy
from typing import Any

MODULE: dict[str, Any] = {
    "temp_id": "MOD-001",
    "name": "Product Catalog",
    "description": "A browsable product discovery module.",
    "objective": "Let shoppers find relevant products.",
    "deliverables": ["Catalog UI and API"],
    "workstreams": ["Backend", "Frontend"],
    "requirement_refs": ["REQ-001"],
    "mvp_required": True,
}

MILESTONE: dict[str, Any] = {
    "temp_id": "MS-001",
    "module_refs": ["MOD-001"],
    "name": "Catalog ready",
    "description": "A complete catalog vertical slice.",
    "objective": "Allow browsing of seeded products.",
    "deliverable": "Tested catalog slice",
    "sequence": 1,
    "target_date": None,
    "planned_effort_hours": 40,
    "acceptance_criteria": ["Catalog supports search"],
    "dependency_refs": [],
}

TASK: dict[str, Any] = {
    "temp_id": "TASK-001",
    "milestone_ref": "MS-001",
    "parent_ref": None,
    "title": "Expose paginated catalog endpoint",
    "description": "Return filtered product summaries with stable pagination.",
    "deliverable": "GET catalog endpoint",
    "acceptance_criteria": ["Invalid page size returns validation error"],
    "definition_of_done": ["Integration tests pass"],
    "effort_min_hours": 8,
    "effort_likely_hours": 12,
    "effort_max_hours": 16,
    "complexity": "medium",
    "workstreams": ["Backend"],
    "skill_tags": ["FastAPI"],
    "mvp_necessity": 100,
    "user_value": 80,
    "deadline_urgency": 50,
    "risk_reduction": 30,
    "user_preference": 50,
    "source": "ai",
    "requirement_refs": ["REQ-001"],
    "assumption_refs": [],
    "locked": False,
}

DEPENDENCY: dict[str, Any] = {
    "temp_id": "DEP-001",
    "predecessor_ref": "TASK-001",
    "successor_ref": "TASK-004",
    "type": "finish_to_start",
    "reason": "The UI contract depends on the endpoint response.",
    "evidence_refs": ["TASK-001", "TASK-004"],
    "confidence_label": "high",
}

RISK: dict[str, Any] = {
    "temp_id": "RISK-001",
    "category": "schedule",
    "description": "Checkout integration may compress final testing.",
    "probability": "possible",
    "impact": "high",
    "trigger": "Checkout remains unfinished at its milestone target.",
    "mitigation": "Prototype the provider contract before full integration.",
    "contingency": "Use the documented provider test gateway only.",
    "related_refs": ["MS-001"],
    "source_fact_refs": ["CONSTRAINT-DEADLINE"],
}

QUESTION: dict[str, Any] = {
    "temp_id": "Q-001",
    "question": "Is online payment required for the first release?",
    "reason": "The answer changes scope and compliance work.",
    "affects": ["scope", "schedule"],
    "required": True,
    "answer_type": "single_choice",
    "options": ["Required", "Sandbox only", "Excluded"],
    "default_assumption": None,
    "source_fact_refs": ["REQ-CHECKOUT"],
}

RECOMMENDATION: dict[str, Any] = {
    "temp_id": "REC-001",
    "type": "dependency_warning",
    "detection_code": "BLOCKED_CRITICAL_TASK",
    "evidence_refs": ["TASK-001", "DEP-001", "FORECAST-LATEST"],
    "why_it_matters": "Downstream work cannot become ready.",
    "suggested_action": "Resolve the API contract blocker before dependent UI work.",
    "expected_impact": "Restores the validated critical sequence.",
    "urgency": "high",
    "risk": "Other noncritical work may wait",
    "approval_required": True,
    "verification_step": "Confirm the blocker is closed before changing readiness.",
    "alternatives": ["Reduce dependent scope in a new draft"],
}

WEEKLY_REPORT: dict[str, Any] = {
    "title": "Weekly project report",
    "period_summary": "Catalog work advanced while checkout work remained blocked.",
    "completed_items": [{"text": "Catalog endpoint completed.", "evidence_refs": ["EVENT-301"]}],
    "progress_statement": {
        "text": "Weighted progress is 42%.",
        "evidence_refs": ["METRIC-PROGRESS"],
    },
    "blockers": [],
    "risks": [],
    "next_actions": [],
    "decisions_needed": [],
    "caveats": [],
}

ANALYSIS: dict[str, Any] = {
    "summary": "An owner-facing commerce project with a focused first release.",
    "project_type": "web_application",
    "intended_users": ["Shoppers", "Administrators"],
    "objectives": [{"text": "Support checkout", "fact_ref": "REQ-003"}],
    "success_criteria": [{"text": "A shopper can place an order", "fact_ref": "REQ-003"}],
    "modules": [deepcopy(MODULE)],
    "workstreams": ["Backend", "Frontend"],
    "assumptions": [],
    "open_questions": [deepcopy(QUESTION)],
    "constraints": [{"text": "Meet the release deadline", "fact_ref": "CONSTRAINT-DEADLINE"}],
    "complexity": "high",
    "risks": [deepcopy(RISK)],
    "mvp_boundary": ["Catalog", "Cart", "Checkout"],
    "excluded_scope": ["Marketplace"],
}
