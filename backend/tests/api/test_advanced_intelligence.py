from uuid import UUID

from tests.api.test_plan_lifecycle import _fixture, _plan_headers
from tests.api.test_projects import ORIGIN, create_user_and_client


def _activate(client: object, csrf: str, plan_id: UUID) -> dict[str, object]:
    draft = client.get(f"/api/v1/plan-versions/{plan_id}").json()
    review = client.post(
        f"/api/v1/plan-versions/{plan_id}/submit-review",
        headers=_plan_headers(csrf, draft["row_version"]),
    ).json()
    response = client.post(
        f"/api/v1/plan-versions/{plan_id}/approve",
        json={"content_hash": review["content_hash"], "reason": "Scenario baseline"},
        headers=_plan_headers(csrf, review["row_version"]),
    )
    assert response.status_code == 200
    return response.json()


def _write_headers(csrf: str, key: str, version: int | None = None) -> dict[str, str]:
    result = {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": key,
    }
    if version is not None:
        result["If-Match"] = str(version)
    return result


def test_scenario_is_idempotent_virtual_and_owner_scoped() -> None:
    _, client, csrf, project_id, plan_id = _fixture("scenario-owner@example.com")
    (
        _,
        other_client,
        _,
    ) = create_user_and_client("scenario-other@example.com")
    with client, other_client:
        active = _activate(client, csrf, plan_id)
        baseline_hash = active["content_hash"]
        first = client.post(
            f"/api/v1/projects/{project_id}/scenarios",
            json={
                "name": "More weekly capacity",
                "baseline_version_id": str(plan_id),
                "overrides": {"capacity_hours_per_week": 45},
            },
            headers=_write_headers(csrf, "scenario-capacity-001"),
        )
        duplicate = client.post(
            f"/api/v1/projects/{project_id}/scenarios",
            json={
                "name": "More weekly capacity",
                "baseline_version_id": str(plan_id),
                "overrides": {"capacity_hours_per_week": 45},
            },
            headers=_write_headers(csrf, "scenario-capacity-001"),
        )

        assert first.status_code == 201
        assert duplicate.json()["id"] == first.json()["id"]
        assert first.json()["result_json"]["delta"]["forecast_finish_days"] < 0
        assert client.get(f"/api/v1/scenarios/{first.json()['id']}").status_code == 200
        assert other_client.get(f"/api/v1/scenarios/{first.json()['id']}").status_code == 404
        after = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        assert after["state"] == "active"
        assert after["content_hash"] == baseline_hash


def test_regeneration_requires_unprotected_ai_draft_and_separate_approval() -> None:
    _, client, csrf, _, plan_id = _fixture("regeneration-owner@example.com")
    with client:
        before = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        task = before["tasks"][0]
        payload = {
            "targets": [
                {
                    "entity_type": "task",
                    "stable_key": task["stable_key"],
                    "fields": ["title"],
                }
            ],
            "replacements": [
                {
                    "entity_type": "task",
                    "stable_key": task["stable_key"],
                    "values": {"title": "Regenerated deterministic task title"},
                }
            ],
        }
        proposed = client.post(
            f"/api/v1/plan-versions/{plan_id}/regenerations",
            json=payload,
            headers=_write_headers(csrf, "regenerate-task-001"),
        )
        assert proposed.status_code == 201
        proposal = proposed.json()
        unchanged = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        assert unchanged["tasks"][0]["title"] == task["title"]
        assert proposal["impact_json"]["affected_stable_keys"]

        approved = client.post(
            f"/api/v1/regeneration-proposals/{proposal['id']}/approve",
            json={"reason": "Owner reviewed the exact diff"},
            headers=_write_headers(
                csrf,
                "unused-decision-key",
                proposal["row_version"],
            ),
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        changed = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        assert changed["tasks"][0]["title"] == "Regenerated deterministic task title"
        assert changed["quality_status"] == "failed"


def test_regeneration_rejects_locked_user_and_active_targets() -> None:
    _, client, csrf, _, plan_id = _fixture("regeneration-locks@example.com")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        task = graph["tasks"][0]
        locked = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"locked": True},
            headers=_plan_headers(csrf, graph["row_version"]),
        ).json()
        payload = {
            "targets": [
                {
                    "entity_type": "task",
                    "stable_key": task["stable_key"],
                    "fields": ["title"],
                }
            ],
            "replacements": [
                {
                    "entity_type": "task",
                    "stable_key": task["stable_key"],
                    "values": {"title": "Attack locked content"},
                }
            ],
        }
        blocked = client.post(
            f"/api/v1/plan-versions/{plan_id}/regenerations",
            json=payload,
            headers=_write_headers(csrf, "locked-attack-001"),
        )
        assert blocked.status_code == 409

        # Human edits remain protected even after unlocking.
        unlocked = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"locked": False},
            headers=_plan_headers(csrf, locked["plan"]["row_version"]),
        )
        assert unlocked.status_code == 200
        protected = client.post(
            f"/api/v1/plan-versions/{plan_id}/regenerations",
            json=payload,
            headers=_write_headers(csrf, "user-attack-001"),
        )
        assert protected.status_code == 409


def test_regeneration_proposal_becomes_stale_after_any_draft_change() -> None:
    _, client, csrf, _, plan_id = _fixture("regeneration-stale@example.com")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        task = graph["tasks"][0]
        proposed = client.post(
            f"/api/v1/plan-versions/{plan_id}/regenerations",
            json={
                "targets": [
                    {
                        "entity_type": "task",
                        "stable_key": task["stable_key"],
                        "fields": ["title"],
                    }
                ],
                "replacements": [
                    {
                        "entity_type": "task",
                        "stable_key": task["stable_key"],
                        "values": {"title": "Proposal that will become stale"},
                    }
                ],
            },
            headers=_write_headers(csrf, "regenerate-stale-001"),
        ).json()
        changed = client.patch(
            f"/api/v1/plan-versions/{plan_id}/tasks/{task['id']}",
            json={"description": "Owner edit made after the exact proposal was created."},
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert changed.status_code == 200
        stale = client.post(
            f"/api/v1/regeneration-proposals/{proposed['id']}/approve",
            json={"reason": "This must fail against the changed baseline."},
            headers=_write_headers(csrf, "unused-stale-decision", proposed["row_version"]),
        )
        assert stale.status_code == 409
        stored = client.get(f"/api/v1/regeneration-proposals/{proposed['id']}").json()
        assert stored["status"] == "stale"


def test_active_plan_has_no_regeneration_write_path() -> None:
    _, client, csrf, _, plan_id = _fixture("regeneration-active@example.com")
    with client:
        active = _activate(client, csrf, plan_id)
        task = active["tasks"][0]
        response = client.post(
            f"/api/v1/plan-versions/{plan_id}/regenerations",
            json={
                "targets": [
                    {
                        "entity_type": "task",
                        "stable_key": task["stable_key"],
                        "fields": ["title"],
                    }
                ],
                "replacements": [
                    {
                        "entity_type": "task",
                        "stable_key": task["stable_key"],
                        "values": {"title": "Forbidden active mutation"},
                    }
                ],
            },
            headers=_write_headers(csrf, "regenerate-active-001"),
        )
        assert response.status_code == 409
        unchanged = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        assert unchanged["content_hash"] == active["content_hash"]


def test_plan_impact_comparison_hides_cross_project_versions() -> None:
    _, owner_client, _, _, first_id = _fixture("compare-owner@example.com")
    _, other_client, _, _, other_id = _fixture("compare-other@example.com")
    with owner_client, other_client:
        same = owner_client.get(f"/api/v1/plan-versions/{first_id}/compare/{first_id}/impact")
        assert same.status_code == 200
        assert same.json()["changes"] == []
        hidden = owner_client.get(f"/api/v1/plan-versions/{first_id}/compare/{other_id}/impact")
        assert hidden.status_code == 404


def test_full_risk_relations_are_version_scoped_and_severity_is_deterministic() -> None:
    _, client, csrf, _, plan_id = _fixture("risk-relations@example.com")
    with client:
        graph = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        task_key = graph["tasks"][0]["stable_key"]
        created = client.post(
            f"/api/v1/plan-versions/{plan_id}/risks",
            json={
                "category": "schedule",
                "description": "Critical delivery work could exceed the approved capacity.",
                "probability": "likely",
                "impact": "critical",
                "trigger": "Forecast passes the persisted deadline.",
                "mitigation": "Reduce scope after explicit owner review.",
                "contingency": "Create and approve a replacement plan version.",
                "relations": [{"entity_type": "task", "entity_ref": task_key}],
                "source_fact_refs": ["CONSTRAINT-001"],
            },
            headers=_plan_headers(csrf, graph["row_version"]),
        )
        assert created.status_code == 201
        body = created.json()
        assert body["item"]["severity"] == 12
        assert body["item"]["relations"][0]["entity_ref"] == task_key
        assert body["plan_content_hash"] != graph["content_hash"]

        updated = client.patch(
            f"/api/v1/plan-versions/{plan_id}/risks/{body['item']['id']}",
            json={"probability": "unlikely", "status": "mitigated"},
            headers=_plan_headers(csrf, body["plan_row_version"]),
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["severity"] == 4
        assert updated.json()["item"]["status"] == "mitigated"
        listing = client.get(f"/api/v1/plan-versions/{plan_id}/risks").json()
        persisted = next(item for item in listing if item["id"] == body["item"]["id"])
        assert persisted["relations"][0]["version_id"] == str(plan_id)

        current = client.get(f"/api/v1/plan-versions/{plan_id}").json()
        unknown = client.post(
            f"/api/v1/plan-versions/{plan_id}/risks",
            json={
                "category": "dependency",
                "description": "A relation attack references another version.",
                "probability": "possible",
                "impact": "high",
                "trigger": "An unknown stable key is submitted.",
                "mitigation": "Reject references outside the plan version.",
                "contingency": "Ask the owner to select a valid entity.",
                "relations": [{"entity_type": "task", "entity_ref": "TASK-99999"}],
            },
            headers=_plan_headers(csrf, current["row_version"]),
        )
        assert unknown.status_code == 409
