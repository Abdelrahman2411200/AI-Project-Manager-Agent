# University demonstration

Version: `0.13.0`
Scenario: “Build an e-commerce website in six weeks with a three-person team.”

This package has two rehearsed paths:

- `sh infra/release/verify-demo.sh` is the deterministic release proof. It builds
  from a clean checkout, loads all eight synthetic fixtures, exercises the public
  API and Markdown/PDF exports, restarts services, and rechecks persistence.
- The 23-step presentation below demonstrates the interactive product workflow.
  Starting a new planning run requires `OPENAI_API_KEY`; all validation, schedule,
  priority, health, and approval results remain deterministic. Without a provider
  key, present the pre-seeded “Commerce MVP — Six Weeks” record, which contains the
  expected end-state and evidence without making a model call.

No fixture contains secrets, live provider credentials, or real personal data.

Demo-only workflow quotas default to 100 runs and 2,000,000 reserved/used tokens
per UTC day so fixture loading and rehearsal do not consume production-sized
limits. Override `USER_DAILY_RUN_LIMIT` and `USER_DAILY_TOKEN_BUDGET` when
testing quota behavior.

## Start and reset

```sh
cp .env.demo.example .env.demo
# Set OPENAI_API_KEY in .env.demo only when exercising a new planning run.
docker compose --env-file .env.demo -f compose.demo.yaml up -d --build db
docker compose --env-file .env.demo -f compose.demo.yaml run --rm migrate
docker compose --env-file .env.demo -f compose.demo.yaml --profile reset run --rm seed
docker compose --env-file .env.demo -f compose.demo.yaml up -d --build api worker frontend
```

To exercise a new AI planning run, set `OPENAI_API_KEY` in `.env.demo` before the
final `up` command and keep that ignored file outside version control. If the key
is omitted, the UI disables planning and the API returns
`503` with `X-Error-Code: ai_provider_unconfigured` before creating a run, job,
or quota reservation.
Existing `AI_UNCONFIGURED` failures remain as audit records.

On Windows, configure the ignored file without placing the key in shell history:

```powershell
& .\infra\release\configure-demo-openai.ps1
```

The script prompts with hidden input, updates only the ignored `.env.demo`, restarts
the API and worker, and verifies that the API loaded the key. Never paste an API
key into the browser, chat, source code, or a committed file. After the capability
check turns available, an old failed-run screen offers **Start a new planning run**.

Open `http://localhost:8080`.

Credentials:

- Email: `demo.owner@example.com`
- Password: `SyntheticDemoOnly!2026`

Reset is intentionally destructive to the dedicated demo database. It requires
`APP_ENV=demo`, a database name containing `demo`, the password environment
variable, and the exact confirmation `RESET-DEMO-DATA`. It refuses production and
staging.

## The eight fixtures

| Fixture | Evidence to show |
|---|---|
| `ecommerce_six_weeks` | 3 people/6 weeks, payment and inventory answers, locked task, blocker, recommendation, report |
| `football_scouting_eight_weeks` | profiles/reports/search/comparison without an invented live-data provider |
| `attendance_system` | personal-data, access-control, retention, correction, and audit risks |
| `expense_tracker_mobile` | platform/sync clarification and offline conflict behavior |
| `marketing_site_small` | concise 1–2 week plan without microservices |
| `analytics_dashboard` | source/freshness/permission clarification and ingestion-first dependencies |
| `incident_investigator` | evidence separated from inference and a human decision gate |
| `impossible_deadline` | one person/five days; infeasibility surfaced without estimate compression |

Every fixture persists project intake, answered clarifications, completed planning
runs with step checkpoints, a generated draft based on an independently approved
active plan, task events, a blocked task, monitoring evidence, a grounded
recommendation and decision, and a factual weekly report. The representative
commerce fixture additionally persists an immutable active-plan what-if scenario
and a pending selective-regeneration proposal attached only to its retained draft.

## Rehearsed 23-step presentation

For each step, capture the listed evidence. Do not replace a failed assertion with
verbal explanation.

1. **Log in and create the project.** Use the seeded owner. Create “Commerce Live
   Demo” with `120` team-hours/week, team size `3`, Monday–Friday at eight hours,
   and timezone `Africa/Cairo`.
   - Expected: owner-scoped UUID, calendar, deadline, capacity, and row version
     appear after reload.

2. **Enter scope.** Require catalog, cart, checkout, authentication, testing, and
   deployment. Exclude marketplace and native mobile applications.
   - Expected: confirmed/excluded requirements preserve user source.

3. **Start planning.**
   - Expected: HTTP `202`, persisted run UUID, queued/running status, current step,
     and polling progress. Reusing the idempotency key returns the same run.

4. **Answer clarifications.** Choose sandbox payment and manual inventory.
   - Expected: Q-001/Q-002 answers and planning decisions are stored; the same run
     resumes.

5. **Inspect analysis.**
   - Expected: shoppers and administrator, explicit MVP boundary, confirmed
     requirements, assumptions/open questions, “sandbox payment provider until
     Q-001 is answered,” and exclusions “marketplace, native apps.”

6. **Inspect modules.**
   - Expected: foundation, catalog, commerce, operations, and quality—not generic
     backend/frontend buckets. Required module coverage is at least 85%.

7. **Inspect milestones.**
   - Expected: deliverable-based milestones in dependency order. MS-002 is
     “Purchasing flow demonstrable” with deliverable “A tested
     cart-to-sandbox-checkout vertical slice.”

8. **Open task detail.**
   - Expected: TASK references, one concrete deliverable, 0.5–3 day estimate,
     acceptance criteria, definition of done, sources, and requirement links.
     TASK-014 is “Persist idempotent checkout result,” likely `16` hours, with
     duplicate-callback and failed-payment acceptance cases.

9. **Inspect dependencies.**
   - Expected: zero invalid/cyclic edges and a legal topological order. Show
     TASK-011 → TASK-014 with its evidence-backed reason.

10. **Inspect schedule.**
    - Expected: working calendar, capacity allocation, project buffer, forecast,
      and deadline feasibility/warning. Estimates are never compressed to force a
      deadline.

11. **Inspect priority.**
    - Expected: deterministic score/label and factor breakdown for MVP necessity,
      deadline urgency, user value, risk reduction, and user preference.

12. **Inspect initial risks.**
    - Expected: deadline/payment risks cite stored facts, triggers, mitigation,
      contingency, and related refs.

13. **Edit one acceptance criterion.**
    - Expected: optimistic row version advances; source becomes `user`; audit
      contains before/after references.

14. **Lock the edited task.**
    - Expected: `locked=true` and protected state persist after reload.

15. **Selectively regenerate a different milestone.**
    - Expected: the selection excludes the locked task and the proposal is stored
      without changing active data.

16. **Review diff and impact, then apply to draft only.**
    - Expected: typed diff/impact lists changed entities; the active content hash is
      unchanged; applying requires explicit approval.

17. **Validate, review, approve, and activate.**
    - Expected: passed quality gate, exact reviewed content hash in PlanApproval,
      one active version, prior active version superseded, and execution projection
      initialization.

18. **Complete two ready tasks.**
    - Expected: immutable status/progress events, readiness recalculation, and
      weighted progress increase. The seeded evidence uses TASK-003/TASK-004 event
      IDs; the factual report rounds the stored weighted metric to 18%.

19. **Block the critical checkout task.**
    - Expected: TASK-014 records a reason, downstream readiness updates, and the
      remaining-work forecast recalculates.

20. **Inspect health.**
    - Expected: `At risk`, rule `BLOCKED_CRITICAL_TASK` or
      `BLOCKED_EFFORT_THRESHOLD`, TASK-014/dependency/forecast evidence, and no
      invented probability.

21. **Inspect and defer the recommendation.**
    - Expected: resolve/reduce the blocked checkout contract in a new draft,
      alternatives, `approval_required=true`, verification requiring readiness and
      a recalculated schedule. Defer it and show the immutable decision/audit event;
      active plan hash remains unchanged.

22. **Generate the weekly report.**
    - Expected: stored ReportData, Markdown, content/state hashes, and evidence
      index. Progress cites `METRIC-PROGRESS`; completed work cites immutable task
      events; blocker facts cite TASK-014.

23. **Export and reload.**
    - Expected: Markdown equals stored text; PDF begins with a valid PDF header and
      reports the stored content hash. Perform a browser reload and service restart,
      then confirm the active
      version/hash, task history, deferred recommendation decision, and report are
      unchanged.

## Representative expected records

| Record | Expected value |
|---|---|
| Analysis | “Six-week owner-operated commerce MVP for shoppers and an administrator.” |
| MS-002 | “Purchasing flow demonstrable”; tested cart-to-sandbox-checkout vertical slice |
| TASK-014 | “Persist idempotent checkout result”; 16 likely hours |
| Dependency | TASK-011 → TASK-014; finish-to-start; deterministic DAG accepted |
| Retained draft | Separate content hash; based on active; TASK-003 remains locked and protected |
| Scenario | Immutable active baseline; +20 hours/week and +7 days; no active-plan write |
| Regeneration | Pending TASK-012 title proposal on draft only; active hash unchanged |
| Health | At risk with blocked-work rule and stored evidence |
| Recommendation | approval required; alternatives and verification; deferred decision |
| Report | persisted factual JSON/Markdown with metric, event, risk, blocker, and forecast evidence |

The wording of provider-authored prose is not an assertion. The fixture assertions
are: module coverage ≥85%, no invalid or cyclic accepted edge, every report fact
supported, infeasible payment scope surfaced when capacity is insufficient, and
the locked task byte-for-byte equivalent across unrelated regeneration.

## Evidence checklist

- [ ] Release commit SHA and both green GitHub workflow URLs recorded.
- [ ] Clean Compose build and migration output retained.
- [ ] Seeder reports exactly eight fixture, project, active-plan, retained-draft,
  and report identifiers.
- [ ] Public API verifier JSON reports `status=passed`.
- [ ] Login and project list succeed through the frontend proxy.
- [ ] Planning run UUID and ten persisted step checkpoints shown.
- [ ] Q-001/Q-002 answers and decisions shown.
- [ ] Plan content hash equals the approved hash.
- [ ] Zero invalid/cyclic accepted dependencies shown.
- [ ] TASK-003 remains user-sourced, locked, and protected.
- [ ] Each project exposes one active plan and one retained draft based on it.
- [ ] The scenario baseline hash equals the unchanged active-plan hash.
- [ ] The regeneration proposal is pending on the draft and excludes TASK-003.
- [ ] TASK-011 → TASK-014 reason and evidence shown.
- [ ] TASK-014 has 16 likely hours and is blocked with a reason.
- [ ] Health is At risk with stored rule evidence.
- [ ] Recommendation evidence and deferred decision shown.
- [ ] Report data, Markdown, and evidence index shown.
- [ ] PDF and Markdown exports verified.
- [ ] Browser reload and container restart preserve all inspected identifiers/hashes.
- [ ] `verify_restore` returns passing migration, relational, and hash invariants.
- [ ] Encrypted backup/isolated restore drill evidence retained.
- [ ] No real personal data, credentials, or provider secrets appear in evidence.

## Teardown

```sh
docker compose -f compose.demo.yaml down
```

This preserves the demo database volume. Do not add `--volumes` unless you intend
to destroy the dedicated synthetic database; the normal reset command is the
audited and guarded way to return to the canonical state.
