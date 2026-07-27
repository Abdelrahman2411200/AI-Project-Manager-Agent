# Phase 11 Verification Matrix

Release candidate: 0.11.0. Every acceptance item is backed by an automated layer or an
explicit architecture review.

| Requirement/backlog | Verification | Evidence |
|---|---|---|
| FR-014 / BE-011 selective regeneration | API + service tests | exact selected field, preview before apply, separate approval, required revalidation |
| FR-014 locked/user edit protection | negative API tests | locked attack and unlocked-but-owner-edited attack both return 409 |
| FR-014 active-plan protection | lifecycle policy + route tests | regeneration accepts `draft` only; reviewed/active states return 409 |
| FR-022 virtual scenario | API/component tests | active hash and state unchanged; baseline/scenario table rendered |
| FR-022 allowed overrides | Pydantic/domain/API tests | positive capacity, date-only deadline, known positive task efforts |
| FR-022 isolation/idempotency | API tests | same key/input returns same row; other owners receive 404 |
| FR-027 version comparison | service, API, and component tests | complete stable-key diff; schedule, risk, and scope summary; cross-project rejection |
| FR-021 risk relations / DB-008 | migration/schema tests | composite risk/version FK, unique relation targets, cascade deletion |
| ARCH-004 active mutation prohibition | architecture review | virtual clone and proposal state/sequence diagrams |
| ALG critical path | unit and scale tests | forward/backward values, slack, cycle and cross-version rejection, 1,000-node chain |
| ALG capacity schedule | unit/API tests | deterministic finish, deadline delta, calculation version |
| ALG change impact | API tests | diff categories and reachable affected stable keys |
| AI-010 grounded explanation | fake-provider and grounding tests | deterministic input only; unsupported factual token rejected |
| DB-008 persistence | SQLite + PostgreSQL migration suites | reversible 0009 migration, JSONB, indexes, same-version FK |
| DB-008 scenario immutability | ORM/migration/PostgreSQL tests | update/delete triggers and append-only contract |
| Authorization | API tests | project-owner scoping and permission-safe 404 |
| Concurrency | API/service tests | proposal `If-Match`, exact baseline hash, stale terminal state |
| Accessibility | Vitest + axe | labelled baseline table, semantic form, permission/error states |
| Responsive result access | table fallback + existing 360 px shell | horizontally scrollable semantic tables; no graph-only control |
| Recovery | restore verifier | advanced tables required after restore |

## Release commands

```powershell
Set-Location backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app

Set-Location ../frontend
npm run lint
npm run typecheck
npm run test:run
npm run build
```

PostgreSQL migration tests, browser tests, security scans, and restore drills run in the ordered
GitHub Actions pipeline before the release gate. No test authorizes mutation of the active
plan; all advanced fixtures include the negative boundary.
