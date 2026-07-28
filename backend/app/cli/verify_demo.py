"""Black-box verification of the seeded university package through the public API."""

from __future__ import annotations

import argparse
import json
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app.demo.seed import (
    DEMO_EMAIL,
    DEMO_FIXTURE_NAMES,
    DEMO_REGENERATION_PROPOSAL_ID,
    DEMO_SCENARIO_ID,
)


class DemoVerificationError(RuntimeError):
    pass


def verify_demo_release(
    *,
    base_url: str,
    origin: str,
    password: str,
    verify_pdf: bool = True,
) -> dict[str, Any]:
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))

    def request_json(path: str, *, method: str = "GET", data: object | None = None) -> Any:
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Accept": "application/json", "Origin": origin}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method
        )
        try:
            with opener.open(request, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise DemoVerificationError(
                f"{method} {path} returned {error.code}: {detail}"
            ) from error

    session = request_json(
        "/auth/session",
        method="POST",
        data={"email": DEMO_EMAIL, "password": password},
    )
    if session["user"]["email"] != DEMO_EMAIL:
        raise DemoVerificationError("The authenticated fixture owner does not match.")
    projects = request_json("/projects?limit=100")["items"]
    if len(projects) != 8:
        raise DemoVerificationError(f"Expected eight projects; received {len(projects)}.")
    expected_names = set(DEMO_FIXTURE_NAMES)
    fixture_slugs = {_slug_from_notes_or_name(item["name"], item["goal"]) for item in projects}
    if fixture_slugs != expected_names:
        raise DemoVerificationError(
            f"Project fixture mismatch: expected {sorted(expected_names)}, "
            f"received {sorted(fixture_slugs)}."
        )

    commerce = next(item for item in projects if item["name"] == "Commerce MVP — Six Weeks")
    project_id = commerce["id"]
    versions = request_json(f"/projects/{project_id}/plan-versions")
    active_versions = [item for item in versions if item["state"] == "active"]
    draft_versions = [item for item in versions if item["state"] == "draft"]
    if len(active_versions) != 1 or len(draft_versions) != 1:
        raise DemoVerificationError(
            "The commerce fixture must expose exactly one active plan and one retained draft."
        )
    active = active_versions[0]
    draft = draft_versions[0]
    if draft["based_on_id"] != active["id"]:
        raise DemoVerificationError("The retained draft is not based on the active plan.")
    graph = request_json(f"/plan-versions/{active['id']}")
    tasks = {item["stable_key"]: item for item in graph["tasks"]}
    if len(tasks) != 14:
        raise DemoVerificationError("The commerce fixture must expose fourteen tasks.")
    if not tasks["TASK-003"]["locked"] or not tasks["TASK-003"]["protected"]:
        raise DemoVerificationError("The user-edited task did not remain locked and protected.")
    if tasks["TASK-014"]["title"] != "Persist idempotent checkout result":
        raise DemoVerificationError("TASK-014 does not match the representative fixture.")
    if graph["content_hash"] != active["content_hash"]:
        raise DemoVerificationError("The active plan hash changed between persisted views.")
    draft_graph = request_json(f"/plan-versions/{draft['id']}")
    draft_tasks = {item["stable_key"]: item for item in draft_graph["tasks"]}
    if draft_graph["content_hash"] != draft["content_hash"]:
        raise DemoVerificationError("The retained draft hash changed between persisted views.")
    protected_fields = ("title", "description", "locked", "protected", "source")
    if any(
        draft_tasks["TASK-003"][field] != tasks["TASK-003"][field] for field in protected_fields
    ):
        raise DemoVerificationError(
            "The retained draft did not preserve the locked user-edited task."
        )
    scenario = request_json(f"/scenarios/{DEMO_SCENARIO_ID}")
    if (
        scenario["baseline_version_id"] != active["id"]
        or scenario["baseline_content_hash"] != active["content_hash"]
        or scenario["status"] != "completed"
    ):
        raise DemoVerificationError("The persisted what-if scenario has a stale baseline.")
    regeneration = request_json(f"/regeneration-proposals/{DEMO_REGENERATION_PROPOSAL_ID}")
    if (
        regeneration["version_id"] != draft["id"]
        or regeneration["baseline_content_hash"] != draft["content_hash"]
        or regeneration["status"] != "pending"
    ):
        raise DemoVerificationError(
            "The selective-regeneration proposal is not approval-gated on the draft."
        )

    health = request_json(f"/projects/{project_id}/health")
    if health["label"] != "At risk" or "BLOCKED_EFFORT_THRESHOLD" not in health["rule_codes"]:
        raise DemoVerificationError("Blocked critical commerce work is not evidenced as At risk.")
    recommendations = request_json(f"/projects/{project_id}/recommendations")
    deferred = next((item for item in recommendations if item["state"] == "deferred"), None)
    if deferred is None or not deferred["evidence"] or deferred["latest_decision"] is None:
        raise DemoVerificationError("The grounded deferred recommendation is incomplete.")

    reports = request_json(f"/projects/{project_id}/reports")
    if len(reports) != 1:
        raise DemoVerificationError("The commerce fixture must expose one weekly report.")
    report = request_json(f"/reports/{reports[0]['id']}")
    if report["data"]["state_hash"] != health["state_hash"]:
        raise DemoVerificationError("The report does not cite the persisted monitoring state.")
    if "Evidence index" not in report["markdown"]:
        raise DemoVerificationError("The report is missing its evidence index.")
    markdown = _request_bytes(
        opener,
        f"{base_url.rstrip('/')}/reports/{reports[0]['id']}/export.md",
        origin,
    )
    expected_markdown = report["markdown"].encode("utf-8")
    if markdown.rstrip(b"\n") != expected_markdown.rstrip(b"\n"):
        raise DemoVerificationError(
            "Markdown export differs from the persisted report "
            f"(export={len(markdown)} bytes, stored={len(expected_markdown)} bytes, "
            f"export_tail={markdown[-20:]!r}, stored_tail={expected_markdown[-20:]!r})."
        )
    pdf_bytes = 0
    if verify_pdf:
        pdf = _request_bytes(
            opener,
            f"{base_url.rstrip('/')}/reports/{reports[0]['id']}/export.pdf",
            origin,
        )
        if not pdf.startswith(b"%PDF-") or len(pdf) < 1_000:
            raise DemoVerificationError("PDF export is not a valid non-empty PDF.")
        pdf_bytes = len(pdf)
    return {
        "status": "passed",
        "project_count": len(projects),
        "active_plan_id": active["id"],
        "active_content_hash": active["content_hash"],
        "retained_draft_id": draft["id"],
        "retained_draft_content_hash": draft["content_hash"],
        "task_count": len(tasks),
        "scenario_id": scenario["id"],
        "regeneration_proposal_id": regeneration["id"],
        "health": health["label"],
        "health_rules": health["rule_codes"],
        "recommendation_state": deferred["state"],
        "report_id": report["id"],
        "report_content_hash": report["content_hash"],
        "markdown_bytes": len(markdown),
        "pdf_bytes": pdf_bytes,
    }


def _request_bytes(opener: Any, url: str, origin: str) -> bytes:
    request = Request(url, headers={"Accept": "*/*", "Origin": origin}, method="GET")
    try:
        with opener.open(request, timeout=90) as response:
            return bytes(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise DemoVerificationError(f"GET {url} returned {error.code}: {detail}") from error


def _slug_from_notes_or_name(name: str, goal: str) -> str:
    exact = {
        "Commerce MVP — Six Weeks": "ecommerce_six_weeks",
        "Football Scouting — Eight Weeks": "football_scouting_eight_weeks",
        "University Attendance System": "attendance_system",
        "Offline Expense Tracker": "expense_tracker_mobile",
        "Small Marketing Site": "marketing_site_small",
        "Analytics Dashboard": "analytics_dashboard",
        "Incident Investigator": "incident_investigator",
        "Commerce — Impossible Deadline": "impossible_deadline",
    }
    try:
        return exact[name]
    except KeyError as error:
        raise DemoVerificationError(f"Unexpected seeded project {name!r}: {goal}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the demo through its public REST API.")
    parser.add_argument("--base-url", default="http://frontend/api/v1")
    parser.add_argument("--origin", default="http://localhost:8080")
    parser.add_argument("--password", required=True)
    parser.add_argument("--skip-pdf", action="store_true")
    arguments = parser.parse_args()
    try:
        result = verify_demo_release(
            base_url=arguments.base_url,
            origin=arguments.origin,
            password=arguments.password,
            verify_pdf=not arguments.skip_pdf,
        )
    except DemoVerificationError as error:
        print(json.dumps({"status": "failed", "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
