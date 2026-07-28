# Final architecture and traceability review

Release: `0.13.0`
Plan phase: 13 — University release
Source specification SHA-256:
`03e80036926b25cc16d6b7b5891a859047ad493cc4b983455142033682166e27`

## Decision

The implemented repository is consistent with the approved greenfield plan. There
is no unresolved Must requirement or university-release Should requirement. The
release remains vendor-neutral and keeps every authorization, lifecycle, graph,
schedule, progress, priority, health, report-fact, and audit decision outside the
model.

The review is accepted only for a commit on which both
`continuous-verification` and `university-release` complete successfully. The
release checklist records the exact GitHub evidence after merge.

## Architecture conformance

| Planned decision | Implemented evidence | Result |
|---|---|---|
| Monorepo areas | `backend/`, `frontend/`, `infra/`, `.github/` | Conformant |
| Python 3.12/FastAPI/Pydantic/SQLAlchemy/Alembic | locked backend project, nine ordered migrations, REST app | Conformant |
| PostgreSQL deploy; SQLite local single-worker | production config validation, Compose PostgreSQL, SQLite tests | Conformant |
| React/TypeScript/Vite/query/forms/accessibility | locked frontend, unit/E2E/a11y/table-alternative gates | Conformant |
| Explicit persisted workflows | agent runs, steps, jobs, checkpoints, leases, retries, terminal states | Conformant |
| No broker required | database-backed worker and job claims | Conformant |
| `/api/v1`, polling, versions, idempotency | OpenAPI routes and service conflict tests | Conformant |
| Secure owner sessions | Argon2, opaque HttpOnly cookie, CSRF, origin check, owner policies | Conformant |
| UUIDs and version-scoped temporary refs | relational models, unique/same-version constraints | Conformant |
| Date-only planning; UTC events; IANA timezone | schemas, calendar/scheduler, timezone tests | Conformant |
| OpenAI Responses adapter and schema outputs | adapter, `store=false`, safety ID, usage/cost, configurable model | Conformant |
| Deterministic trusted decisions | `backend/app/domain/` and persisted validation gates | Conformant |
| Stored factual reports and Playwright PDF | immutable report JSON/Markdown/hash and Chromium renderer | Conformant |
| Compose/GitHub Actions/vendor-neutral release | development, demo, production Compose and two CI workflows | Conformant |

## Data and contract review

- The implemented entities cover identity, owner-scoped intake, calendars, plan
  versions and approvals, analyses, clarifications and decisions, milestones,
  tasks, same-version dependencies, risks and relations, execution projections,
  append-only status/progress/monitoring history, recommendations/evidence/decisions,
  factual reports, agent runs/steps/jobs, scenarios/regeneration, prompts/usage,
  telemetry, and audit events.
- Database checks, composite foreign keys, uniqueness, indexes, row versions,
  one-active-plan enforcement, and append-only service/model behavior match the
  plan-version isolation rules.
- The eleven required structured AI/agent-state contracts live in typed Pydantic
  schemas with strict fields, examples/fixtures, cross-field checks, validation,
  retry, refusal, and rejection tests.
- Twelve versioned prompts are registered with hashes, bounded context, untrusted
  input delimiters, output schemas, retry/budget policy, stored versions, and
  regression snapshots.
- Every model output passes provider schema parsing, temporary-reference
  validation, permission/ownership checks, deterministic graph/business rules,
  and transactional persistence. Failed output cannot activate a plan.

## Workflow and boundary review

- Planning covers clarification, analysis, modules, milestones, tasks,
  dependencies, estimates, schedule, risk, quality, and atomic draft persistence.
- Editing/locking/review/approval binds an exact content hash. Active-plan
  replacement always requires owner approval.
- Selective regeneration applies only to a draft. Locked or protected items are
  rejected if changed. Scenarios and change-impact records cannot mutate active
  state.
- The release fixture proves this boundary with eight retained generated drafts,
  an immutable active-plan scenario, and a pending draft-only regeneration
  proposal whose baseline hashes survive service restart.
- Execution events drive readiness, weighted progress, forecast, health, and
  monitoring. Recommendations cite stored evidence and decisions are audited.
- Reports derive factual JSON from state/events and export matching sanitized
  Markdown/PDF. Narrative failure cannot remove factual output.
- Organization tenancy, multi-user collaboration, resource assignment, budgets,
  portfolio management, and external GitHub/Jira/chat/calendar/email writes remain
  post-MVP and are not silently included.

## Dependency and operational-cost review

| Component | Purpose | Considered alternative | MVP/release need | Operational cost |
|---|---|---|---|---|
| FastAPI/Pydantic | typed REST and validation | Django REST | Required | one API process plus replicas |
| SQLAlchemy/Alembic/PostgreSQL | relational integrity and migration | document DB | Required | managed/self-hosted database and backups |
| Database jobs | durable asynchronous work | Redis/Celery | Required; broker deferred | worker process, no extra datastore |
| React/Vite/TanStack Query | responsive SPA/server state | server templates | Required UI | static Nginx container |
| OpenAI adapter | structured semantic proposals | embedded model | Optional for seeded proof; required for live AI | configurable token/cost budgets |
| Playwright Chromium | factual PDF and browser acceptance | native PDF engine | Full university version | larger image and bounded render memory/time |
| OpenTelemetry/Grafana assets | safe SLO visibility | vendor APM | Required operational evidence | optional collector/dashboard service |
| Docker Compose | portable package/rehearsal | vendor PaaS manifest | Required release | Docker host |
| GitHub Actions | ordered verification | vendor CI | Required repository gate | hosted-runner minutes |

Versions are pinned in `uv.lock`, `package-lock.json`, container tags, and immutable
GitHub Action SHAs. Formal provider evaluation records the returned model and uses
a supported pinned snapshot when available.

## All 72 backlog items

“Complete” means implementation, acceptance criteria, and the verification layer
named in the source backlog are present. Category rows enumerate every item exactly
once and identify the authoritative evidence family.

| Items | Status | Primary evidence |
|---|---|---|
| ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-005, ARCH-006 | Complete | architecture docs, boundaries, Compose, this final review |
| DB-001, DB-002, DB-003, DB-004, DB-005, DB-006, DB-007, DB-008 | Complete | models, migrations 0001–0009, PostgreSQL/constraint/restore tests |
| BE-001, BE-002, BE-003, BE-004, BE-005, BE-006, BE-007, BE-008, BE-009, BE-010, BE-011, BE-012 | Complete | `/api/v1`, services/workflows/workers, API/reliability/performance tests |
| AI-001, AI-002, AI-003, AI-004, AI-005, AI-006, AI-007, AI-008, AI-009, AI-010 | Complete | provider/contracts/prompts/validation/usage, AI snapshots and evaluations |
| ALG-001, ALG-002, ALG-003, ALG-004, ALG-005, ALG-006, ALG-007, ALG-008 | Complete | graph/calendar/schedule/priority/progress/health/critical-path/impact modules and unit tests |
| FE-001, FE-002, FE-003, FE-004, FE-005, FE-006, FE-007, FE-008, FE-009, FE-010 | Complete | all planned screens, accessible alternatives, responsive unit/E2E/visual tests |
| TEST-001, TEST-002, TEST-003, TEST-004, TEST-005, TEST-006, TEST-007, TEST-008 | Complete | deterministic, DB, contract, workflow, security, E2E, performance, evaluation/release gates |
| SEC-001, SEC-002, SEC-003 | Complete | session/CSRF/owner policy, hardening, threat model and security workflow |
| OBS-001, OBS-002 | Complete | safe telemetry/SLO code, dashboard, budget/alert tests and docs |
| DEVOPS-001, DEVOPS-002, DEVOPS-003 | Complete | lockfiles, Compose profiles, CI, encrypted backup/restore and deployment rehearsal |
| DOC-001, DOC-002 | Complete | README, operator/developer guide, deployment guide, eight fixtures, reset, demo script |

Counts: 6 ARCH + 8 DB + 12 BE + 10 AI + 8 ALG + 10 FE + 8 TEST +
3 SEC + 2 OBS + 3 DEVOPS + 2 DOC = **72**.

## Requirement-to-test traceability

The numbered `FR-*`/`NFR-*` acceptance matrix in `IMPLEMENTATION PLAN.MD` is the
source mapping. The implemented verification layers are:

- Domain unit tests for every graph, calendar, priority, progress, schedule,
  critical-path, forecast, health, grounding, and change-impact rule.
- PostgreSQL migration, constraint, same-version, append-only, and restore tests.
- API tests for sessions, ownership, project intake, planning, plan lifecycle,
  execution, recommendations, reports, scenarios, regeneration, PDF, and evaluation.
- Workflow/worker failure injection for idempotency, retry, leases, resumption,
  cancellation, refusal, and transactional persistence.
- Frontend unit, accessibility, responsive, keyboard/table-parity, E2E, and visual
  snapshot tests.
- Security, dependency, source, secret, performance, backup, clean-deploy,
  restart/persistence, fixture, and public-API release gates.

No requirement is verified solely by documentation or a search result.

## Release risks and dispositions

| Risk | Disposition |
|---|---|
| Host/TLS differences | loopback bind, exact-origin config, generic reverse-proxy contract, clean Linux rehearsal |
| Destructive demo reset | environment + database-name + password + explicit-literal fail-closed guard |
| Model variability | deterministic fixture proof, schema/rule gates, evaluation snapshots and thresholds |
| PDF resource use | bounded concurrency/timeout/size and isolated Chromium |
| Migration/recovery failure | ordered migration gate, encrypted backup, isolated restore, RPO/RTO evidence |
| Hidden scope inconsistency | 72-item inventory and plan-boundary review above |

## Final review conclusion

The architecture, data model, contracts, dependencies, security boundaries, MVP/full
version scope, university fixtures, and vendor-neutral release package agree with
the implementation plan. No Must/Should inconsistency is accepted. Any future
change to active-plan mutation, tenancy, external integration, or deterministic
decision ownership requires a new architecture/security review.
