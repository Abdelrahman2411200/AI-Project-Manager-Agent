# AI Project Manager Agent

An intelligent, stateful project-management system that turns an initial project idea into an approved plan, then supports execution, monitoring, recommendations, and grounded progress reporting.

The product combines schema-constrained AI output with deterministic project-management rules. AI proposes and explains; application code owns authorization, dependency validation, scheduling, progress, health, audit history, and approval boundaries.

## Current status

Phase 8 of the [engineering implementation plan](./IMPLEMENTATION%20PLAN.MD) delivers active-plan execution with deterministic progress, forecasting, and health:

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

Only an unchanged, validated, owner-reviewed content hash can become active. Phase 9 adds grounded recommendations, risk warnings, factual reports, and Markdown export on top of the persisted Phase 8 evidence.

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
| Frontend | React 19, TypeScript, Vite, TanStack Query, React Router |
| Persistence | PostgreSQL in deployment; SQLite for single-worker local development |
| Quality | Pytest, Ruff, mypy, Vitest, Testing Library, MSW, axe-core, Playwright, ESLint |
| Packaging | Dockerfiles and Docker Compose |
| AI boundary | OpenAI Responses adapter, strict Pydantic schemas, immutable prompts, offline fake provider |

## Repository layout

```text
.
|-- backend/                       FastAPI API and worker
|-- frontend/                      React web application
|-- AI_project_manager_os/         Design exploration and screen references
|-- compose.yaml                   Local service orchestration
|-- IMPLEMENTATION PLAN.MD         Approved engineering plan
|-- IMPLEMENTATION%20PLAN.MD       Original source specification
`-- README.md
```

The source specification and Stitch exports are retained as project artifacts.

## Local development

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24, npm 11, and optionally Docker Desktop.

Copy the example environment file before starting services:

```powershell
Copy-Item .env.example .env
```

Never commit real credentials or API keys.

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
```

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

The MVP is completed through Phase 10 of the implementation plan. Selective regeneration, critical-path analysis, advanced scheduling, what-if simulation, dependency visualization, PDF export, and the university demo are delivered in Phases 11-13. External integrations, multi-user collaboration, portfolios, budgets, and resource assignment remain post-MVP.
