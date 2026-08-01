# AI Project Manager Agent

An intelligent, stateful project-management system that turns an initial project idea into an approved plan, then supports execution, monitoring, recommendations, and grounded progress reporting.

The product combines schema-constrained AI output with deterministic project-management rules. AI proposes and explains; application code owns authorization, dependency validation, scheduling, progress, health, audit history, and approval boundaries.

## Current status

Phase 13 of the [engineering implementation plan](./IMPLEMENTATION%20PLAN.MD) packages the complete university release on top of the hardened MVP and full-version experience:

- FastAPI service with typed settings, `/api/v1` routing, request IDs, health checks, and consistent error responses
- React, TypeScript, Vite, TanStack Query, and React Router application shell
- Database-backed worker with leased claims, heartbeats, stale-worker protection, retry backoff, and cooperative cancellation
- PostgreSQL, API, worker, and frontend orchestration through Docker Compose
- Locked backend and frontend dependencies with lint, type-check, test, and build commands
- UI design tokens adapted from the repository's Stitch design exploration
- Argon2id authentication, opaque server-side sessions, CSRF/origin protection, and login throttling
- Owner-scoped project intake with requirements, constraints, calendars, audit events, and optimistic concurrency
- Alembic migrations verified against PostgreSQL, plus premium sign-in and guided project-creation flows
- Version-local DAG validation with stable topological order, downstream reachability, readiness projection, and concrete cycle paths
- Explainable priority scores, leaf-only weighted progress, IANA-timezone working calendars, and deterministic capacity scheduling
- Completion forecasts and precedence-ordered health classifications with stable rule codes and evidence
- Property-style fixtures with 98% domain branch coverage and a 1,000-task/approximately 3,000-edge benchmark below two seconds
- Provider-neutral structured request, result, refusal, usage, and error contracts with an offline fake provider
- A native local Ollama adapter with JSON-schema output, bounded schema repair, deterministic generation settings, timeouts, and complete token accounting
- A configurable OpenAI Responses adapter using strict Pydantic output, `store: false`, pseudonymous safety identifiers, explicit timeouts, and complete token accounting
- Nine semantic output schemas and three versioned workflow-state schemas with fail-closed cross-field invariants
- Twelve immutable prompt versions with content hashes, output budgets, stable untrusted-data delimiters, positive fixtures, and adversarial regression examples
- A schema, identifier, business-rule, permission, and deterministic validation ladder with at most one repair attempt
- Immutable prompt-version persistence and append-only model-usage records through the fourth Alembic migration
- Owner-scoped, idempotent planning-run APIs with polling traces, clarification answers, cancellation, and safe resume
- Checkpointed clarification, analysis, module, milestone, task, acceptance, dependency, schedule, risk, and quality-gate nodes
- Atomic persistence of validated plan versions, analyses, milestones, tasks, dependencies, and risks after deterministic validation
- Plan-version isolation through composite database constraints, with temporary model references mapped to UUIDs only at persistence
- Partial outcomes for token-budget exhaustion and fail-closed behavior for refusals, invalid required output, cycles, and quality violations
- A fifth Alembic migration for plan drafts, durable agent runs, node traces, and the leased job queue
- Owner-scoped plan graph and version-history APIs with optimistic `If-Match` concurrency
- Draft-only milestone, task, and dependency CRUD with stable keys, lock protection, and user/protected provenance
- Deterministic persisted-graph validation that recalculates priorities, dates, milestone effort, and content hashes
- Review submission, changes-requested return, exact-hash approval, and atomic activation/supersession
- Append-only approval records, immutable reviewed content, and a database-enforced single active version
- Deterministic plan-version diffs across content, estimates, dates, dependencies, and lock/source changes
- A sixth Alembic migration with lifecycle triggers and active-version/approval constraints
- Typed TanStack Query hooks and mutation clients for the Phase 6 lifecycle
- Guided project intake that can save independently or immediately start an idempotent planning run
- Polling planning progress with concise public step labels, cancellation, safe failures, token usage, and clarification routing
- Typed clarification controls with required-answer gating, explicit suggested assumptions, keyboard operation, and browser-local draft persistence
- A semantic plan review covering analysis, scope, modules, assumptions, milestones, tasks, dependencies, risks, provenance, estimates, priority, and schedule
- Focused React Hook Form and Zod editors for analysis, milestones, tasks, effort ranges, acceptance criteria, definitions of done, and priority factors
- Atomic keyboard milestone reordering, owner locks, deletion confirmation, dependency cycle feedback, and dirty-navigation guards
- Deterministic validation evidence, exact `If-Match` conflict recovery, review/change-request controls, and explicit exact-hash activation confirmation
- Responsive list-first layouts with retained navigation and no horizontal overflow at 360 px
- MSW-backed component tests, axe semantic checks, keyboard tests, and Playwright create-to-approval coverage at desktop and 360 px
- Active-plan task projections that keep mutable execution state separate from immutable approved content
- Legal, optimistic-concurrency-protected task transitions with idempotency keys, append-only status events, progress updates, and audit records
- Dependency readiness propagation and leaf-weighted task, milestone, and project progress recalculation
- State-hashed remaining-work scheduling that rejects stale monitoring results before persistence
- Stable detectors for overdue and blocked work, unmet dependencies, delayed milestones, schedule slippage/infeasibility, low buffer, capacity, scope, ready work, and inconsistent state
- Precedence-ordered health labels with exact rule codes, entity references, forecast facts, and calculation versions
- Database-backed monitoring jobs that run without AI and resume through the existing worker queue
- Owner-scoped execution, event-history, progress, and health APIs under `/api/v1`
- Accessible overview, Kanban/list board, task controls, activity history, and evidence-rich health pages
- A seventh Alembic migration with projection indexes, plan-version constraints, and database-level append-only execution-history triggers
- API, domain, migration, component, axe, keyboard, and Playwright lifecycle coverage at desktop and 360 px
- Deterministic recommendation candidates for every supported monitoring detection, deduplicated by exact state and evidence hashes
- Immutable recommendation evidence with owner decisions for accept, dismiss, and defer; every decision explicitly preserves the active plan
- Optional schema-constrained AI wording that is rejected when a reference, number, date, percentage, or unsafe markup is unsupported
- Immediate factual `ReportData` snapshots with asynchronous weekly, project, milestone, risk, and comparison report workflows
- Persisted report JSON, cited narrative, sanitized Markdown, content hashes, partial factual fallback, and safe owner-scoped export filenames
- Correlated request, workflow, model-usage, audit, and redacted product-outcome telemetry with stable pseudonymous user identifiers
- Owner-scoped recommendation and report APIs, report run polling, optimistic recommendation decisions, CSRF, and idempotency enforcement
- Accessible recommendation evidence, decision dialogs, report history/detail screens, and structured evidence indexes without raw HTML rendering
- An eighth reversible Alembic migration with insight indexes and database-level append-only evidence, decision, report, and metric triggers
- Phase 9 API, grounding, migration, component, axe, keyboard, reload, export, desktop, and 360 px Playwright coverage
- Persisted, owner-scoped what-if scenarios calculated from immutable active-plan snapshots with idempotency and exact baseline hashes
- Deterministic critical-path forward/backward passes, capacity forecasts, stable-key plan comparison, and downstream change-impact discovery
- Selective regeneration proposals restricted to explicitly selected fields on unlocked, unprotected AI draft content
- A two-step regeneration approval boundary with proposal concurrency, stale-baseline rejection, complete diffs, affected references, and mandatory draft revalidation
- Schema-constrained change/scenario explanation support that receives only deterministic result objects and rejects unsupported references, numbers, dates, markup, or approval claims
- Normalized, version-constrained risk relations plus scenario and regeneration persistence in the ninth reversible Alembic migration
- Owner-scoped comparison, scenario, and regeneration REST APIs with permission-safe 404 responses, CSRF, idempotency keys, and `If-Match`
- Accessible scenario inputs/results, baseline delta tables, version-comparison tables, and regeneration preview/decision controls
- Phase 11 domain, API, AI-grounding, migration, component, axe, ownership, lock-attack, cross-version, virtual-isolation, and 1,000-node coverage
- A lazy-loaded React Flow dependency overview with deterministic layout and a complete keyboard/screen-reader edge table
- A responsive date-only timeline/Gantt with text labels and schedule-table parity for every task, including unscheduled work
- A dedicated risk register with owner-scoped list/read/create/update/delete APIs, optimistic concurrency, deterministic severity, and draft-only mutation controls
- A reviewed eight-fixture evaluation baseline exposed through an authenticated endpoint, with threshold/provenance dashboard and fail-closed dataset verification
- Rich baseline/scenario metric bars with exact value tables and explicit increased/decreased/unchanged labels
- Hash-bound factual PDF export from the immutable report representation with escaped print HTML, isolated Playwright/Chromium, no JavaScript or network, bounded concurrency/timeout/size, safe audit events, and Markdown fallback
- Accessible desktop and 360 px Intelligence routes with table alternatives, reduced-motion support, no page-level overflow, and no color-only or drag-only operation
- Phase 12 API, PDF-render, ownership, concurrency, axe, keyboard, large-graph, visual snapshot, download, responsive, dependency-audit, and browser acceptance coverage
- Eight deterministic synthetic university fixtures with stable UUIDs, complete intake, run checkpoints, generated retained drafts, independently approved active plans, execution events, monitoring, grounded recommendations/decisions, and factual weekly reports
- Persisted representative what-if and selective-regeneration evidence proving immutable active baselines, draft-only proposals, locked-item preservation, and explicit approval boundaries
- A fail-closed demo reset that requires an allowed environment, a database name containing `demo`, an explicit confirmation literal, and a separately supplied synthetic password
- Same-origin production API proxying that aligns the built frontend with its CSP and cookie/CSRF boundary
- Vendor-neutral production and demo Compose packages with ordered migrations, health checks, API/worker isolation, PostgreSQL volumes, and an encrypted backup operation
- A clean-release rehearsal that builds from source, migrates, seeds, validates the public API and Markdown/PDF exports, restarts services, and proves database persistence
- Final architecture/72-item traceability review, deployment guide, operator/developer guide, release checklist, expected fixture records, and exact 23-step university demonstration
- A separate university-release GitHub workflow for source immutability, clean Compose configuration, deterministic seed verification, clean-host browser/API persistence, and seeded backup/restore evidence

Only an unchanged, validated, owner-reviewed content hash can become active. Recommendations are guidance, never implicit plan mutations, and reports remain factual even when AI wording is unavailable or rejected.

## Product workflow

```text
Project brief
    -> clarification and analysis
    -> modules, milestones, tasks, and dependencies
    -> deterministic validation and scheduling
    -> editable draft plan
    -> explicit owner approval
    -> active execution and monitoring
    -> evidence-backed recommendations and reports
```

AI-generated plans remain drafts until the project owner approves them. Once activated, any AI-proposed plan change must pass validation and return to the user for approval.

## Architecture

```text
React / TypeScript web application
              |
        REST /api/v1
              |
          FastAPI API
       /             \
PostgreSQL       Worker process
                       |
        Persisted workflow state machine
                       |
             AI provider adapter
```

The workflow engine is application-owned and persisted. Nodes have typed state, checkpoints, deterministic exit conditions, retry policies, idempotency protection, and audit records. MVP background work uses a database-backed job table and a separate worker process; Redis, Celery, and LangGraph are not required.

## Technology

| Area | Foundation |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic Settings, Uvicorn |
| Frontend | React 19, TypeScript, Vite, TanStack Query, React Router, lazy React Flow |
| Persistence | PostgreSQL in deployment; SQLite for single-worker local development |
| Quality | Pytest, Ruff, mypy, Vitest, Testing Library, MSW, axe-core, Playwright/Chromium, ESLint |
| Packaging | Dockerfiles and Docker Compose |
| AI boundary | Local Ollama by default (`gemma3:4b`), optional OpenAI adapter, strict Pydantic schemas, immutable prompts, offline fake provider |
| Hardening | Request limits, owner/run budgets, encrypted restore drills, SLO alerts, ordered CI |

## Repository layout

```text
.
|-- backend/                       FastAPI API and worker
|-- frontend/                      React web application
|-- AI_project_manager_os/         Design exploration and screen references
|-- compose.yaml                   Local service orchestration
|-- compose.demo.yaml              Reproducible synthetic university demonstration
|-- compose.production.yaml        Vendor-neutral production profile
|-- docs/                          Architecture, operations, deployment, demo, release evidence
|-- infra/                         Backup, observability, and release rehearsal
|-- IMPLEMENTATION PLAN.MD         Approved engineering plan
|-- IMPLEMENTATION%20PLAN.MD       Original source specification
`-- README.md
```

The source specification and Stitch exports are retained as project artifacts.

## Local development

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24, npm 11, and optionally Docker Desktop.

For Windows development with Ollama installed in the Ubuntu WSL distribution, start the complete local demo from the repository root:

```powershell
& .\infra\release\start-local-ollama.ps1
```

The helper keeps WSL running, verifies that `gemma3:4b` is installed, configures the ignored `.env.demo`, starts Docker Compose, and exercises the same structured provider path used by the worker. Open the URL printed by the script (normally `http://localhost:8080`, or the existing `HTTP_PORT` in `.env.demo`). No hosted API key is required.

To run services manually, copy the example environment file first:

```powershell
Copy-Item .env.example .env
```

Never commit credentials or ignored local environment files.

### Run with Docker Compose

```powershell
docker compose up --build
```

The web application is served at `http://localhost:5173`; the API is available at `http://localhost:8000`. API liveness and readiness endpoints are `/api/v1/health/live` and `/api/v1/health/ready`.

Create the first local owner account interactively after the stack starts:

```powershell
docker compose run --rm api uv run python -m app.cli.create_user --email owner@example.com
```

### Run the backend directly

```powershell
Set-Location backend
uv sync --group dev
uv run playwright install chromium
uv run alembic upgrade head
uv run python -m app.cli.create_user --email owner@example.com
uv run uvicorn app.main:app --reload
```

### Run the frontend directly

```powershell
Set-Location frontend
npm ci
npm run dev
```

## Quality checks

Backend:

```powershell
Set-Location backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app
```

Frontend:

```powershell
Set-Location frontend
npm run lint
npm run typecheck
npm run test:run
npm run test:e2e
npm run build
```

Compose configuration:

```powershell
docker compose config --quiet
docker compose -f compose.demo.yaml config --quiet
```

University release and prior operational evidence:

- [Architecture review](docs/architecture.md) and [threat model](docs/threat-model.md)
- [Observability and SLOs](docs/observability.md)
- [MVP operator runbook](docs/operations/mvp-runbook.md)
- [Backup and restore drill](docs/operations/backup-restore.md)
- [MVP release checklist](docs/release/mvp-checklist.md)
- [Advanced intelligence architecture](docs/architecture-advanced.md)
- [Phase 11 verification matrix](docs/release/phase-11-verification.md)
- [Visualization and PDF architecture](docs/architecture-ui.md)
- [Phase 12 evaluation baseline](docs/evals/phase-12-baseline.md)
- [Phase 12 verification matrix](docs/release/phase-12-verification.md)
- [Vendor-neutral deployment](docs/deploy.md)
- [Operator and developer guide](docs/operations/operator-developer-guide.md)
- [Local Ollama model selection and runtime](docs/local-ollama.md)
- [University demonstration](docs/demo.md)
- [Final architecture and 72-item review](docs/release-review.md)
- [Final 48-requirement system audit](docs/release/final-system-audit.md)
- [University release checklist](docs/release/university-checklist.md)

The ordered GitHub Actions pipelines run backend quality and PostgreSQL tests,
reference load, frontend tests/build, desktop/mobile browser acceptance,
dependency/SAST/secret scans, encrypted PostgreSQL restore, immutable-spec/release
manifest checks, and a clean demo build/restart/persistence rehearsal before the
university release can pass.

Run the deterministic university release rehearsal locally:

```powershell
sh infra/release/verify-demo.sh
```

The demo is served at `http://localhost:8080`. The public synthetic login is
`demo.owner@example.com` / `SyntheticDemoOnly!2026`; never reuse these values in
another environment.

## Core safety rules

- Treat project descriptions and imported text as untrusted input.
- Validate every model response against its schema, identifiers, permissions, and business rules.
- Keep scheduling, progress, health, graph, audit, and authorization decisions outside the model.
- Never silently activate or modify an approved plan.
- Preserve user-edited and locked plan items.
- Derive factual reports from persisted state and events.
- Require stored evidence for every recommendation.
- Record model usage, workflow transitions, approvals, and material changes.

## Delivery boundaries

The MVP is completed through Phase 10, full-version intelligence through Phase 11,
the full-version experience through Phase 12, and the reproducible university
release through Phase 13 of the implementation plan. External integrations,
multi-user collaboration, portfolios, budgets, and resource assignment remain
post-MVP.
