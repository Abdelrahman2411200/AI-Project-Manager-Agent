# AI Project Manager Agent — Repository-Specific Engineering Plan

Document status: implementation-ready  
Repository assessment date: 2026-07-22  
Target: credible MVP through Phase 10; full university version through Phase 13

## 1. Executive Summary

This repository is a greenfield workspace. The only existing file is IMPLEMENTATION%20PLAN.MD, which is the specification for this document. No application code, package manifest, database, tests, Git metadata, CI configuration, or local repository instructions exist.

The proposed product is a stateful AI Project Manager Agent. It converts an incomplete idea into a reviewed and approved plan, then monitors execution using persisted state, deterministic calculations, evidence-grounded recommendations, and factual reports. It is explicitly not a one-shot chatbot.

The implementation uses a Python/FastAPI backend, React/TypeScript frontend, PostgreSQL deployment database, explicit persisted workflow engine, database-backed worker, and an OpenAI Responses API adapter. Model output proposes semantic content; application code owns validation, authorization, persistence, graph operations, dates, scheduling, priority, progress, health, and auditability.

Delivery is divided into 13 phases and 72 dependency-ordered backlog items. Phases 1–10 produce the credible MVP. Phases 11–13 add the university-version differentiators and demonstration package.

## 2. Current Repository Assessment

### Observed state

| Item | Finding | Classification |
|---|---|---|
| Root structure | One source specification file only | Reuse unchanged |
| AGENTS.md / README | Not present | New component required |
| Backend/frontend | Not present | New component required |
| Database/ORM/migrations | Not present | New component required |
| Authentication/tenancy | Not present | New component required |
| LLM/agent/workflow | Not present | New component required |
| Queue/scheduler/worker | Not present | New component required |
| Storage/report/PDF | Not present | New component required |
| Tests/fixtures | Not present | New component required |
| Docker/CI/observability | Not present | New component required |
| Git repository | Not initialized | Outside this planning task |

All application paths in this plan are **Proposed**. IMPLEMENTATION%20PLAN.MD remains unchanged. No existing class, route, model, schema, configuration, or convention can be reused or extended.

### Selected greenfield direction

- Monorepo: backend/, frontend/, infra/, and .github/.
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic.
- Data: PostgreSQL in deployment; SQLite only for local single-worker use and fast unit tests.
- Frontend: React, TypeScript, Vite, TanStack Query, React Hook Form, Zod, accessible headless primitives, CSS tokens.
- Workflow: application-owned persisted state machine; no LangGraph dependency.
- Background execution: database job table plus one or more worker processes; no Redis/Celery for MVP.
- API: versioned REST at /api/v1; JSON errors using a common problem schema; polling for run state.
- AI: provider interface with an OpenAI Responses API adapter, strict structured output, store disabled, configurable model, token/cost logging.
- Deployment: Docker Compose on a generic Linux host; proposed GitHub Actions for checks, not automatic production deployment.

### Dependency decisions

| Library/service | Why | Alternative considered | MVP? | Cost/maintenance |
|---|---|---|---|---|
| FastAPI + Pydantic | Typed REST and shared validation language | Django REST Framework | Required | Small; Python ecosystem updates |
| SQLAlchemy + Alembic | Explicit relational model and migrations | Django ORM | Required | Migration discipline required |
| PostgreSQL | Constraints, JSON, concurrency, durable job claiming | SQLite | Required for deployment | Operated database and backups |
| OpenAI Python SDK | Supported Responses integration and structured output | Raw HTTP / other provider SDK | Required adapter | API cost and SDK upgrades |
| React + Vite | Focused SPA with fast development | Next.js | Required | Client routing and deployment remain separate |
| TanStack Query | Server cache, polling, mutation invalidation | Hand-written fetch state | Required | One client abstraction |
| React Hook Form + Zod | Performant accessible forms and client feedback | Controlled React forms | Required | Schemas duplicated selectively from API |
| Radix-style primitives | Keyboard/focus behavior for dialogs and menus | Custom widgets | Required where native HTML is insufficient | Styling remains local |
| React Flow | Dependency graph interactions | Custom SVG | Full version | Bundle size and accessibility overlay |
| Playwright | E2E tests and reuse for PDF rendering | Cypress + WeasyPrint | E2E required; PDF full version | Chromium image size |
| OpenTelemetry | Portable traces and metrics | Vendor SDK | MVP hardening | Collector/configuration overhead |

## 3. Assumptions and Open Questions

### Locked assumptions

1. MVP users are authenticated individual project owners. Workspaces, invitations, and collaborative roles are post-MVP.
2. A project has one persisted IANA timezone, a date-only start/deadline, and a working calendar.
3. Finish-to-start is the only MVP dependency type.
4. Planning runs are asynchronous and durable without an external broker.
5. A draft may be edited and locked before approval; changes to an active plan always create a new draft version and require approval.
6. Markdown is the MVP export. PDF is a full-version feature.
7. AI model names and prices are configuration/data, not hard-coded business logic. The initial balanced default is gpt-5.6-terra; evaluation may pin a dated snapshot.
8. Reports store source metrics plus Markdown so factual claims can be revalidated.
9. No external integration may write without explicit approval.

### Open questions retained for implementation kickoff

These do not block the architecture and use the stated defaults until changed:

- Production host: default generic Docker host with managed PostgreSQL.
- Email verification/password reset: excluded from university MVP; seed/admin CLI creates demonstration accounts.
- Data retention: default indefinite project retention until owner deletion; audit records are retained with redacted payload metadata.
- Provider region/data residency: configure per deployment before real sensitive data is accepted.

## 4. Product Scope: MVP, Full Version, Post-MVP, Out of Scope

### Credible MVP — Phases 1–10

- Account/session and project ownership.
- Project intake with incomplete-data support and clarification.
- AI analysis, modules, milestones, actionable tasks, acceptance criteria, dependencies, risks, and explicit assumptions.
- Draft persistence, editing, item locking, validation, approval, activation, and immutable history.
- DAG validation, explainable priority scoring, greedy capacity schedule, weighted progress, basic deterministic health.
- Task status events, blockers, overdue detection, grounded recommendations.
- Weekly/on-demand reports and Markdown export.
- Agent run trace, audit trail, retries, idempotency, observability, five or more fixtures, deterministic and LLM-contract tests.

### Full university version — Phases 11–13

- Selective regeneration while preserving locked/user-edited items.
- Version diff, advanced capacity scheduler, critical path, what-if scenarios, and change-impact analysis.
- Interactive dependency graph, rich timeline/Gantt, risk register, scenario comparison, PDF export, evaluation dashboard.
- Eight evaluation scenarios, seeded university demo, generic deployment and operator materials.

### Post-MVP integrations

GitHub, Jira, Slack, Microsoft Teams, Google Calendar, email, external notifications, resource assignment, budgets, portfolio management, workspace collaboration, and approval-gated external automation.

### Out of scope

- Autonomous deletion, deadline changes, scope removal, reassignment, external messaging, or plan approval.
- Hidden chain-of-thought or unsupported probability percentages.
- Automatic code generation/implementation of the planned project.
- Payroll, invoicing, procurement, or HR performance scoring.
- Unreviewed use of project text as model instructions.

## 5. User Roles and Permissions

| Role/actor | Read | Write | Approval | Restrictions |
|---|---|---|---|---|
| Authenticated user | Own profile and owned projects | Create projects | None outside owned projects | Cannot access another owner |
| Project owner | All owned project state and traces | Drafts, tasks, dependencies, status, reports | Approve/activate own draft; accept recommendations | Cannot rewrite immutable events or old versions |
| System agent | Context explicitly granted to one run | Proposed structured output and run trace | None | Cannot activate plans or perform external actions |
| Background worker | Jobs and scoped project data | Checkpoints/results/audit through services | None | No direct user authorization bypass |
| Future viewer/editor | Deferred | Deferred | Deferred | Requires workspace model |

Authorization occurs in service methods as well as route dependencies. Database queries always include owner_id. Agent and worker actions carry the initiating user ID and project ID into the audit context.

## 6. User Journeys

### Journey A — Idea to active plan

1. Owner creates a project with goal, deadline, capacity, timezone, constraints, required and excluded features.
2. System validates input and starts an idempotent planning run.
3. Agent identifies missing decisions; owner answers or accepts explicitly labeled assumptions.
4. Workflow generates and validates analysis, modules, milestones, tasks, dependencies, estimates, priorities, schedule, risks, and quality checks.
5. Owner edits content, locks user-controlled items, resolves assumptions, and validates the draft.
6. Owner approves. The immutable version becomes active and approval/audit events are stored.

### Journey B — Execute and monitor

1. Owner moves a ready task to in_progress.
2. Status event is appended; readiness, progress, schedule, and health are recomputed.
3. When a critical task is blocked, monitoring produces a warning supported by task IDs, dependency path, remaining effort, and forecast.
4. Owner accepts, defers, or dismisses the recommendation; the decision is audited.

### Journey C — Re-plan safely

1. Owner creates a new draft from the active version.
2. Owner selects a milestone or fields to regenerate and keeps locked/user-edited items protected.
3. System validates replacements, computes a diff and downstream impact, and asks for approval.
4. Accepted changes apply only to the draft; activation requires a new approval.

### Journey D — Report

1. Owner selects period and report type.
2. Deterministic aggregation builds factual report data from current state and immutable events.
3. Model writes narrative constrained to supplied facts; claim validator checks cited evidence.
4. JSON and Markdown are persisted and downloadable; PDF is available in the full version.

## 7. Functional Requirements with IDs and Acceptance Criteria

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-001 | Create project | Required name/goal plus optional fields are accepted; owner, timezone, dates, capacity, constraints, features and notes persist. |
| FR-002 | Incomplete intake | Missing noncritical fields do not fail creation; missing/uncertain facts are represented as questions or assumptions. |
| FR-003 | Project analysis | Produces summary, users, objectives, success criteria, modules, workstreams, assumptions, questions, constraints, complexity, risks and MVP boundary. |
| FR-004 | Clarification | Questions have stable IDs, reason, required flag, choices when useful, answer and resolution state. |
| FR-005 | Milestones | Each has stable key, objective, one deliverable, sequence, target date, effort, criteria, status and calculated progress. |
| FR-006 | Actionable tasks | Every leaf task has one deliverable, 0.5–3 day target size, effort, criteria, DoD, milestone, workstream, source and rationale. |
| FR-007 | Subtasks | Parent/child hierarchy is version-local; parent progress is derived from leaves and double counting is impossible. |
| FR-008 | Dependencies | Owner can create/remove finish-to-start edges; missing/self/duplicate/cycle/cross-version edges are rejected with useful errors. |
| FR-009 | Priority | Deterministic score and factor breakdown map every task to Critical/High/Medium/Low. |
| FR-010 | Scheduling | Calendar, capacity, parallelism and dependencies produce planned dates or an explainable infeasibility warning. |
| FR-011 | Draft review | Owner can edit analysis, milestones, tasks, estimates, priorities and dependencies and can lock user-controlled content. |
| FR-012 | Version lifecycle | States idea, clarification_required, generating, draft, under_review, approved, active, archived and superseded follow legal transitions. |
| FR-013 | Approval | Only owner approval activates a validated version; approval records actor, timestamp, version and content hash. |
| FR-014 | Selective regeneration | Full version regenerates selected unlocked targets, validates references and shows diff/impact before draft application. |
| FR-015 | Task status | pending, ready, in_progress, blocked, completed and cancelled transitions append immutable events. |
| FR-016 | Progress | Task, milestone and project weighted progress recompute deterministically after relevant changes. |
| FR-017 | Monitoring | Detects overdue/blocked/unmet dependency/delayed milestone/slippage/infeasibility/low buffer/scope/capacity/ready/inconsistent state. |
| FR-018 | Health | Returns Completed, On track, At risk, Delayed or Insufficient data with rule codes and evidence. |
| FR-019 | Recommendations | Each recommendation contains type, evidence, rationale, action, impact, urgency, risk, approval need, verification and alternatives. |
| FR-020 | Recommendation decision | Owner can accept, dismiss or defer; decision never silently mutates an active plan. |
| FR-021 | Risks | Full version supports category, probability band, impact, severity, trigger, mitigation, contingency, relations and status. |
| FR-022 | What-if | Full version applies scenario overrides to a virtual clone and compares forecast, critical path, health and risks without active changes. |
| FR-023 | Reports | Weekly, project, milestone, risk and comparison reports use persisted metrics/events and retain factual source data. |
| FR-024 | Export | MVP downloads sanitized Markdown; full version generates PDF from the same report representation. |
| FR-025 | Agent trace | Owner can inspect workflow, node status, referenced input/output, validation, retries, duration, model, tokens, cost and outcome. |
| FR-026 | Audit | User/agent changes, approvals, status/estimate/dependency/recommendation/report actions append audit events. |
| FR-027 | Plan comparison | Full version displays added/removed/changed items and schedule, risk and scope effects between two owned versions. |
| FR-028 | Dashboard | Owner sees projects, active version, progress, health, next action and recent activity with correct empty/error states. |

## 8. Non-Functional Requirements with IDs and Measurable Criteria

| ID | Requirement | Measurable criterion |
|---|---|---|
| NFR-001 | Security | OWASP-aligned controls; no critical/high findings in release scan; owner isolation tests pass. |
| NFR-002 | Privacy | store=false for provider calls; only node-required fields are sent; secrets and raw sensitive inputs are excluded from logs. |
| NFR-003 | Reliability | Required-node failure cannot yield completed run; interrupted runs resume from last committed checkpoint. |
| NFR-004 | Data integrity | FK/check/unique constraints enforce version locality and immutable histories; all database tests pass. |
| NFR-005 | Explainability | Every health result, priority and recommendation exposes rule/factor/evidence without chain-of-thought. |
| NFR-006 | Accessibility | WCAG 2.2 AA automated checks have no serious violations; all primary flows work by keyboard. |
| NFR-007 | API performance | p95 non-AI reads <300 ms and writes <600 ms at 50 concurrent users on reference deployment. |
| NFR-008 | Calculation performance | DAG/schedule/health recomputation for 1,000 tasks and 3,000 edges completes <2 s. |
| NFR-009 | AI latency | Planning run exposes progress within 2 s and completes p95 <5 min for the evaluation-size projects, excluding provider outage. |
| NFR-010 | Scalability | Stateless API scales horizontally; PostgreSQL job claiming prevents duplicate execution. |
| NFR-011 | Maintainability | Domain logic is framework-light, typed, documented and has ≥90% branch coverage for deterministic algorithms. |
| NFR-012 | Observability | Every request/run/node/model call has correlated IDs; latency, retry, token, cost and failure metrics exist. |
| NFR-013 | Cost control | Per-run token/cost budget aborts additional model calls safely; owner receives partial-state message. |
| NFR-014 | Provider portability | Provider interface has a fake implementation; domain/workflow tests run without network or OpenAI SDK. |
| NFR-015 | Idempotency | Repeating a start/mutation with the same owner/key/payload returns the original result; mismatched payload returns 409. |
| NFR-016 | Recovery | Nightly database backup procedure and quarterly restore test achieve RPO 24 h/RTO 4 h for reference deployment. |
| NFR-017 | Responsive UI | Required flows work at 360 px width; dense graphs/timelines provide list/table alternatives. |
| NFR-018 | Time correctness | DST, nonworking days and timezone boundaries are covered by deterministic fixtures; events remain UTC. |
| NFR-019 | Error safety | User messages are actionable and contain correlation IDs; stack traces, SQL, secrets and provider payloads are not exposed. |
| NFR-020 | Compatibility | API uses /api/v1 and additive changes; breaking changes require a new version and migration note. |

## 9. Proposed Architecture with Mermaid Diagram

~~~mermaid
flowchart LR
    U[Owner browser] -->|HTTPS /api/v1| API[FastAPI API]
    UI[React SPA] --> API
    API --> AUTH[Session and authorization]
    API --> APP[Application services]
    APP --> DOMAIN[Domain and deterministic engines]
    APP --> PG[(PostgreSQL)]
    API --> JOB[(Agent jobs)]
    WORKER[Worker process] --> JOB
    WORKER --> WF[Persisted workflow engine]
    WF --> DOMAIN
    WF --> AI[Provider abstraction]
    AI --> OAI[OpenAI Responses API]
    WF --> PG
    API --> OBS[Logs metrics traces]
    WORKER --> OBS
    REPORT[Report renderer] --> PG
    REPORT --> PDF[Playwright PDF - full]
~~~

### Component boundaries

- Routes authenticate, parse, authorize and map errors; they do not contain business calculations.
- Application services own transactions, idempotency, audit and orchestration.
- Domain modules are pure where possible and accept typed values.
- Workflow nodes read/write through services and never trust provider output directly.
- Provider adapters return raw metadata plus parsed candidates; validators decide acceptance.
- Worker claims jobs atomically. PostgreSQL uses SKIP LOCKED; SQLite development permits one worker only.
- Frontend treats API as source of truth; calculated values are never reimplemented for authority.

### Proposed top-level layout

~~~text
backend/
  app/{api,auth,core,db,domain,services,workflows,ai,workers,observability}
  migrations/ tests/
frontend/
  src/{app,api,components,features,pages,styles}
  tests/
infra/
  docker/
.github/workflows/
~~~

## 10. Agent Architecture with Workflow Diagrams

### Agent loop

~~~mermaid
flowchart TD
    P[Perceive persisted project state] --> I[Interpret facts constraints events]
    I --> PL[Select workflow node]
    PL --> T[Invoke bounded semantic tool]
    T --> V[Schema and deterministic validation]
    V -->|valid| A[Propose action]
    V -->|repairable, attempts left| T
    V -->|invalid| F[Persist failed or partial step]
    A --> H{Approval required?}
    H -->|yes| W[Persist proposal and wait]
    H -->|no| S[Persist permitted result]
    W --> O[Observe user decision]
    S --> O
    O --> P
~~~

### Common node contract

Every workflow node records purpose, typed input/output references, deterministic versus LLM execution, reads/writes, validation, timeout, maximum attempts, failure code, idempotency key, transaction boundary, start/end time, token/cost metadata and trace correlation. A node is idempotent on run_id + node_name + input_hash. Model calls retry twice for transient errors with jittered exponential backoff; one schema-repair attempt is allowed and uses validation errors only. Business-rule failures never retry unchanged output.

### Planning workflow nodes

| Node | Mode | Reads | Output/write | Validation/failure |
|---|---|---|---|---|
| validate_request | Deterministic | Project intake | Normalized constraints | Invalid date/capacity → failed |
| detect_gaps | LLM | Intake | ClarificationQuestion[] | Schema, duplication, relevance |
| wait_or_assume | Human/deterministic | Questions/answers | Decisions and assumptions | Required unanswered → waiting |
| analyze_project | LLM | Confirmed facts | ProjectAnalysisOutput | Fact/source and scope checks |
| draft_modules | LLM | Analysis | ModuleDraft[] | Stable refs, coverage, uniqueness |
| draft_milestones | LLM | Modules/constraints | MilestoneDraft[] | Deliverable, order, criteria |
| draft_tasks | LLM | Milestones | TaskDraft[] | Size, specificity, unique refs |
| suggest_dependencies | LLM | Tasks | DependencySuggestion[] | References only; candidates |
| validate_graph | Deterministic | Candidates/tasks | Accepted DAG or errors | Cycle path/missing/duplicate |
| normalize_effort | Deterministic | Task estimates | Normalized hours/ranges | Reject nonpositive/outlier |
| score_priority | Deterministic | Factors/graph | Score, label, rationale data | Bounded factors and weights |
| schedule | Deterministic | DAG/calendar/capacity | Dates/feasibility | No silent deadline fit |
| identify_risks | LLM + rules | Plan/schedule | RiskDraft[] | Evidence/reference validation |
| quality_gate | Deterministic | Whole draft | Quality report | Required failure blocks draft |
| persist_draft | Transactional | Validated candidates | Versioned entities | All-or-nothing, idempotent |
| await_approval | Human | Draft | Review state | Never self-approves |

### Selective regeneration workflow

~~~mermaid
flowchart LR
    S[Select targets] --> C[Load protected context]
    C --> G[Generate replacements]
    G --> V[Validate references and DAG]
    V --> D[Compute diff and impact]
    D --> H[Human approval]
    H -->|accept| A[Apply to draft]
    H -->|reject| R[Retain draft]
~~~

Nodes: validate selection; snapshot target/protected items; generate by field-specific prompt; reject edits to locked/user-edited IDs; validate schemas and cross-references; build deterministic diff; simulate schedule/health impact; persist proposal; wait for owner; apply in one version-checked transaction. Regeneration has no active-version write path.

### Monitoring workflow

Nodes: load active version/recent events; calculate readiness; calculate weighted progress; detect rule violations; recalculate schedule/critical path; classify health; create deterministic recommendation candidates; generate explanations only; validate evidence references; upsert monitoring result using input-state hash.

### Reporting workflow

Nodes: validate period; load active state/events; aggregate metrics; construct immutable ReportData; generate narrative; validate every factual claim against ReportData references; persist JSON/Markdown; render requested export. Missing narrative does not discard factual JSON; run is partial, not complete.

### What-if workflow

Nodes: validate allowed overrides; clone active state in memory; apply changes; recompute graph/schedule/critical path/health; compare baseline/scenario; generate constrained explanation; persist Scenario and results. It never writes task/milestone/plan tables.

### Non-planning node specifications

The common node contract above supplies retry, timeout, idempotency and telemetry for every row. Deterministic validation failures are final for the current input; LLM nodes receive at most one repair/regeneration attempt; waiting nodes are resumable and never consume a worker while waiting.

| Workflow/node | Purpose and mode | Inputs/reads | Outputs/writes | Validation and failure state |
|---|---|---|---|---|
| regenerate.validate_target | Check requested fields and draft state; deterministic | Owner, draft, selected stable IDs | Selection snapshot step | Missing/locked/active target → failed |
| regenerate.load_protected | Freeze locked and user-edited context; deterministic | Draft items and content hash | Protected-ID set/reference | Version/hash mismatch → stale |
| regenerate.generate | Produce only selected replacements; LLM | Target context, protected summaries, prompt version | Candidate structured step | Schema/reference violation → repair then failed |
| regenerate.validate | Rebuild affected graph and business checks; deterministic | Candidates and unchanged draft | Validation report | Protected change/cycle/bad ID → failed |
| regenerate.impact | Compare replacement virtually; deterministic | Baseline draft and valid candidates | Diff/impact snapshot | Calculation error → failed; no draft write |
| regenerate.await_approval | Obtain owner decision; human | Proposal/diff/content hash | waiting/accepted/rejected state | Stale draft → proposal expired |
| regenerate.apply | Apply approved replacement; transactional | Accepted proposal and exact hash | Updated draft entities/audit | Concurrency → conflict; transaction rolls back |
| monitor.load_state | Capture active state and event cursor; deterministic | Active version, events, calendar | Versioned monitoring input | No active version → insufficient-data completion |
| monitor.readiness | Recalculate executable tasks; deterministic | Tasks and edges | Readiness result reference | Invalid graph → failed/inconsistent condition |
| monitor.progress | Aggregate weighted progress; deterministic | Task projections/effort | Progress result | Unestimated threshold becomes warning, not invented value |
| monitor.detect | Find defined conditions; deterministic | State, dates, schedule, progress | Detection codes/evidence | Missing facts become insufficient-data evidence |
| monitor.reschedule | Forecast and critical path; deterministic | Remaining work, DAG, capacity | Schedule result | Infeasible is valid output; algorithm error → failed |
| monitor.health | Apply ordered rules; deterministic | Detection/schedule/progress | Health result | Must contain rule code and evidence |
| monitor.explain | Explain actionable candidates; LLM | Only detection evidence and allowed actions | RecommendationDraft candidates | Unsupported fact → candidate rejected |
| monitor.persist | Deduplicate and store results; transactional | State hash, valid results | Monitoring snapshot/recommendations | Changed active state → stale/requeue |
| report.validate_period | Normalize report type/period; deterministic | Request/project timezone | Inclusive UTC/date bounds | Invalid/future bounds → failed |
| report.load_history | Capture state/events at cursor; deterministic | Owned project/version/event log | Source snapshot reference | Missing active plan → failed with user action |
| report.aggregate | Build factual metrics; deterministic | Source snapshot | Immutable ReportData | Inconsistent event projection → failed |
| report.narrate | Write cited prose; LLM | ReportData only | WeeklyReportNarrative | Unknown number/ID → repair then partial |
| report.validate_claims | Match claims to data; deterministic | Narrative and ReportData | Claim report | Unsupported claim removes narrative/marks partial |
| report.persist | Store JSON and Markdown; transactional | ReportData, valid/absent narrative | Report row/content hash/audit | Duplicate input hash returns existing report |
| report.export | Render requested representation; deterministic | Stored report | Download/PDF metadata | PDF error → partial; stored Markdown remains |
| scenario.validate | Restrict override types/ranges; deterministic | Owner request and baseline | Normalized overrides | Unsupported external action → failed |
| scenario.clone | Create isolated in-memory graph; deterministic | Active version snapshot | Virtual clone/hash | Baseline changes → stale |
| scenario.calculate | Apply overrides and recompute; deterministic | Clone, calendar, capacity | Scenario metrics/path/health | Invalid graph/override → failed |
| scenario.compare | Produce baseline deltas; deterministic | Baseline/scenario results | Comparison object | Every delta must identify source values |
| scenario.explain | Explain trade-offs; LLM | Comparison object only | Cited explanation | Unsupported recommendation → rejected |
| scenario.persist | Store scenario, never plan mutations; transactional | Valid result/explanation | Scenario row/audit | Duplicate input returns existing scenario |

## 11. Domain Model with Mermaid ER Diagram

~~~mermaid
erDiagram
    USER ||--o{ SESSION : has
    USER ||--o{ PROJECT : owns
    PROJECT ||--o{ PROJECT_REQUIREMENT : contains
    PROJECT ||--o{ PROJECT_CONSTRAINT : contains
    PROJECT ||--o{ CLARIFICATION_QUESTION : asks
    PROJECT ||--o{ DECISION : records
    PROJECT ||--o{ PLAN_VERSION : versions
    PROJECT ||--o{ AGENT_RUN : executes
    PROJECT ||--o{ AUDIT_EVENT : audits
    PLAN_VERSION ||--o| PROJECT_ANALYSIS : includes
    PLAN_VERSION ||--o{ PLAN_APPROVAL : approved_by
    PLAN_VERSION ||--o{ MILESTONE : contains
    MILESTONE ||--o{ TASK : contains
    TASK ||--o{ TASK : parent_of
    TASK ||--o{ TASK_DEPENDENCY : predecessor
    TASK ||--o{ TASK_DEPENDENCY : successor
    TASK ||--o{ TASK_STATUS_EVENT : history
    TASK ||--o{ PROGRESS_UPDATE : updates
    PLAN_VERSION ||--o{ RISK : assesses
    PROJECT ||--o{ WORK_CALENDAR : schedules
    PROJECT ||--o{ RECOMMENDATION : receives
    RECOMMENDATION ||--o{ RECOMMENDATION_EVIDENCE : cites
    PROJECT ||--o{ SCENARIO : simulates
    PROJECT ||--o{ REPORT : reports
    AGENT_RUN ||--o{ AGENT_RUN_STEP : traces
    AGENT_RUN_STEP }o--|| PROMPT_VERSION : uses
~~~

### Entity rules

| Entity | Important fields and constraints | Relationships/indexes/deletion |
|---|---|---|
| User | UUID, normalized unique email, password_hash, status, timestamps | Owns projects; restrict delete while projects exist or use explicit account erasure workflow |
| Session | token_hash unique, user_id, csrf_hash, expires_at, revoked_at | Index user/expiry; cascade on user erasure |
| Project | owner_id, name, goal, dates, timezone, capacity, status, row_version | Index owner/status/updated; soft archive |
| ProjectRequirement | kind stated/suggestion/confirmed/excluded, text, source, status | Unique project + normalized text + kind; cascade with project |
| ProjectConstraint | type, value_json, source, confirmed | Validate known types; cascade |
| ProjectAnalysis | plan_version_id unique, structured_json, summary | Delete only with unapproved draft; immutable after approval |
| ClarificationQuestion | stable_key, question, reason, required, answer, status | Unique project + stable_key; retain for history |
| Decision | type assumption/decision/rejection/open_question, text, source, confirmed_at | Append revisions rather than overwrite confirmed history |
| PlanVersion | project_id, number, state, based_on_id, content_hash, row_version | Unique project + number; one active partial unique index |
| PlanApproval | version_id, actor_id, decision, reason, content_hash, created_at | Append-only; index version/date |
| Milestone | version_id, stable_key, sequence, deliverable, effort, dates, status | Unique version + stable_key/sequence; cascade only with draft |
| Task | version_id, milestone_id, parent_id, stable_key, fields, locked, source, row_version | Unique version + stable_key; parent must share version |
| TaskDependency | version_id, predecessor_id, successor_id, type=FS | Unique endpoints; checks nonself; both tasks share version |
| TaskStatusEvent | task_id, from/to, reason, actor, occurred_at, correlation_id | Append-only; index task/time |
| ProgressUpdate | task_id, fraction, actual_effort, note, source | Append-only; fraction 0..1 |
| WorkCalendar | project_id, weekday hours JSON, holidays, effective dates, parallel_limit | No overlapping effective ranges |
| Risk | version_id, stable_key, category, probability_band, impact, severity, trigger, mitigation, contingency, status | Unique version + stable_key; relations via join tables |
| Recommendation | project_id, version_id, type, action, state, urgency, input_hash | Unique project/type/input_hash while open |
| RecommendationEvidence | recommendation_id, entity_type/id, fact_key/value, captured_at | Entity allowlist; immutable snapshot |
| Scenario | project_id, baseline_version_id, overrides_json, result_json, status | Never becomes plan implicitly |
| Report | project_id, version_id, type, period, data_json, markdown, content_hash | Index project/type/created; immutable revisions |
| AgentRun | project_id, workflow, status, idempotency_key, input_hash, budget, outcome | Unique initiator/idempotency key |
| AgentRunStep | run_id, name, attempt, status, references, validation, usage, duration | Unique run/name/attempt; append attempts |
| PromptVersion | key, version, template_hash, schema_name, active | Unique key/version; immutable once used |
| AuditEvent | owner/project, actor_type/id, action, entity, before/after references, request_id | Append-only, partition-ready by occurred_at |

### Global ownership, versioning and deletion policies

- Every project child is owned through project_id directly or through a mandatory version/project relationship; repositories require owner_id at construction.
- Plan-version entities cannot reference a different project or version. Application validation is reinforced with composite unique/FK constraints where PostgreSQL permits.
- Mutable statuses use the enumerations in Sections 7, 10 and 20. Unknown values are rejected at API, domain and database layers.
- Draft-owned rows may be hard-deleted only before approval and still emit an audit event with a safe before-reference. Approved/active/superseded content is immutable and retained.
- Project deletion is a deliberate erasure workflow: revoke jobs/sessions, archive immediately, delete or pseudonymize after retention policy, and produce an erasure audit record without copied project text.
- Optimistic row_version protects mutable aggregates; event, approval, prompt-version and report-revision records are append-only.
- All major entity changes call AuditRecorder in the same transaction. High-volume read events are telemetry, not audit events.

## 12. Database and Migration Plan

### Database conventions

- PostgreSQL UUID primary keys; application-generated UUIDs.
- UTC timestamptz for instants; date for planned days; IANA timezone string on Project.
- Numeric(8,2) for effort hours; progress numeric constrained to 0..1.
- JSONB for bounded snapshots and structured provider metadata, never as a substitute for relational task/dependency state.
- created_at/updated_at plus row_version on mutable aggregates.
- Database enums are avoided initially; checked strings make migrations safer. Pydantic and CHECK constraints share canonical values.
- Approved plan content and history tables are immutable through service rules and database triggers where practical.

### Migration sequence

1. Identity: users and sessions.
2. Projects, requirements, constraints, calendars.
3. Plan versions, analyses, questions, decisions, approvals.
4. Milestones, tasks, dependencies and their constraints.
5. Status/progress events and audit events.
6. Agent runs, steps, jobs and prompt versions.
7. Risks, recommendations/evidence, reports and scenarios.
8. Partial indexes: one active version per project; open recommendation deduplication; job claim indexes.

Each migration has upgrade/downgrade where data-safe, a schema test, and a PostgreSQL integration test. Destructive migration requires backup, staged backfill, constraint validation, and explicit rollback/forward-fix notes. SQLite is not treated as proof of PostgreSQL compatibility.

### Transaction boundaries

- Create project + initial requirements/constraints/audit: one transaction.
- Persist generated draft graph: one transaction after all validation.
- Approve/activate: lock project/version rows; validate content hash; supersede previous active version; activate target; append approval/audit; commit atomically.
- Status update: lock task; validate transition/readiness; update task projection; append status/audit; enqueue monitoring job; commit.
- Worker checkpoint: step result and run/job state commit together.
- Idempotent API response is stored in the same transaction as its side effect.

## 13. Agent State Schemas

All state schemas are Pydantic models persisted as versioned JSON snapshots with schema_version, run_id, project_id, workflow, status, current_step, completed_steps, failed_steps, retry_counts, warnings, input_refs, output_refs, started_at and updated_at. Status is queued/running/waiting_for_user/partial/failed/completed/cancelled. References contain entity type, UUID and version/content hash rather than unrestricted project text.

### PlanningAgentState

Fields: base fields; project_version integer; intake_ref; clarification_ids list[UUID]; decision_ids list[UUID]; analysis_ref optional; module_refs; milestone_refs; task_refs; dependency_refs; risk_refs; validation_report_ref optional; proposed_plan_version_id optional; approval_required bool. Cross-validation requires clarification_required status to have open questions; completed requires a persisted draft and passed quality gate.

Example:

~~~json
{"schema_version":"1.0","run_id":"…","project_id":"…","workflow":"planning","status":"waiting_for_user","current_step":"wait_or_assume","clarification_ids":["…"],"completed_steps":["validate_request","detect_gaps"],"approval_required":true}
~~~

### MonitoringAgentState

Fields: base fields; active_plan_version_id; event_cursor; readiness_result_ref; progress_result_ref; schedule_result_ref; health_result_ref; detected_condition_codes list[str]; recommendation_ids list[UUID]; state_hash. Completed requires the state hash still match or the run is marked stale and requeued.

Example:

~~~json
{"schema_version":"1.0","run_id":"…","project_id":"…","workflow":"monitoring","status":"completed","active_plan_version_id":"…","detected_condition_codes":["BLOCKED_CRITICAL_TASK"],"recommendation_ids":["…"],"state_hash":"sha256:…"}
~~~

### ReportingAgentState

Fields: base fields; active_plan_version_id; report_type; period_start/date; period_end/date; event_cursor; report_data_ref optional; narrative_ref optional; report_id optional; export_format markdown/pdf; claim_validation_errors. completed requires stored data and Markdown; PDF failure yields partial.

Example:

~~~json
{"schema_version":"1.0","run_id":"…","project_id":"…","workflow":"reporting","status":"partial","report_type":"weekly","period_start":"2026-07-13","period_end":"2026-07-19","report_id":"…","export_format":"pdf","failed_steps":["render_pdf"]}
~~~

State parsing failure is nonrepairable for persisted data and alerts operations. A model never writes these state objects directly; workflow code constructs them.

## 14. LLM Structured Output Schemas

### Common contract

- Strict JSON Schema; additionalProperties=false at every object.
- Temporary keys match ^(MOD|MS|TASK|DEP|RISK|Q|REC)-[0-9]{3,5}$ and are unique within a run.
- Titles are 3–120 characters; descriptions 20–2,000; list fields have explicit maxima.
- Source facts use fact_ref values supplied in context. No arbitrary database IDs are accepted.
- Refusal, truncation and incomplete outputs are handled explicitly.
- Parse → schema validate → identifier validate → business validate → permission/scope validate → deterministic consistency validate.
- On schema failure, one repair request receives only the invalid JSON and machine-readable errors. A second failure rejects the node. Invalid business logic is returned to the generating node only if a changed output can address it; deterministic facts are never negotiated.

### ProjectAnalysisOutput

Fields: summary str; project_type str; intended_users list[str,1..10]; objectives list[FactItem,1..15]; success_criteria list[FactItem,1..20]; modules list[ModuleDraft]; workstreams list[str]; assumptions list[DecisionDraft]; open_questions list[ClarificationQuestion]; constraints list[FactItem]; complexity low/medium/high/very_high; risks list[RiskDraft]; mvp_boundary list[str]; excluded_scope list[str]. Every confirmed requirement must cite a user fact; assumptions cannot be marked confirmed.

Example: {"summary":"Owner-facing commerce MVP","project_type":"web_application","intended_users":["shoppers","administrator"],"objectives":[{"text":"Support checkout","fact_ref":"REQ-003"}],"success_criteria":[{"text":"A shopper can place an order","fact_ref":"REQ-003"}],"modules":[],"workstreams":["backend","frontend"],"assumptions":[],"open_questions":[],"constraints":[],"complexity":"high","risks":[],"mvp_boundary":["catalog","cart","checkout"],"excluded_scope":["marketplace"]}.

### ModuleDraft

Fields: temp_id; name; description; objective; deliverables list[str,1..8]; workstreams list[str,1..5]; requirement_refs list[str,1..20]; mvp_required bool. Name and normalized objective must be unique; every module must cover a supplied requirement or be labeled suggestion.

Example: {"temp_id":"MOD-001","name":"Product Catalog","description":"Browsable product discovery","objective":"Let shoppers find products","deliverables":["catalog UI and API"],"workstreams":["backend","frontend"],"requirement_refs":["REQ-001"],"mvp_required":true}.

### MilestoneDraft

Fields: temp_id; module_refs list; name; description; objective; deliverable; sequence int≥1; target_date optional date; planned_effort_hours positive decimal; acceptance_criteria list[str,1..10]; dependency_refs list[temp milestone ID]. A milestone has exactly one primary deliverable; sequence is unique; date may not precede project start.

Example: {"temp_id":"MS-001","module_refs":["MOD-001"],"name":"Catalog ready","description":"Catalog vertical slice","objective":"Browse seeded products","deliverable":"Tested catalog slice","sequence":1,"target_date":null,"planned_effort_hours":40,"acceptance_criteria":["Catalog supports search"],"dependency_refs":[]}.

### TaskDraft

Fields: temp_id; milestone_ref; parent_ref optional; title; description; deliverable; acceptance_criteria list[str,1..10]; definition_of_done list[str,1..10]; effort_min_hours; effort_likely_hours; effort_max_hours; complexity trivial/low/medium/high; workstreams list[str,1..3]; skill_tags list[str,0..8]; mvp_necessity/user_value/deadline_urgency/risk_reduction/user_preference integers 0..100; source ai/user; requirement_refs; assumption_refs; locked false. min≤likely≤max; a leaf target is 4–24 likely hours; larger work must have children.

Example: {"temp_id":"TASK-001","milestone_ref":"MS-001","parent_ref":null,"title":"Expose paginated catalog endpoint","description":"Return filtered product summaries with stable pagination","deliverable":"GET catalog endpoint","acceptance_criteria":["Invalid page size returns 422"],"definition_of_done":["Integration tests pass"],"effort_min_hours":8,"effort_likely_hours":12,"effort_max_hours":16,"complexity":"medium","workstreams":["backend"],"skill_tags":["FastAPI"],"mvp_necessity":100,"user_value":80,"deadline_urgency":50,"risk_reduction":30,"user_preference":50,"source":"ai","requirement_refs":["REQ-001"],"assumption_refs":[],"locked":false}.

### DependencySuggestion

Fields: temp_id; predecessor_ref; successor_ref; type fixed finish_to_start; reason; evidence_refs list; confidence_label low/medium/high. References must be distinct TaskDraft IDs. Confidence is qualitative and not used to bypass graph validation.

Example: {"temp_id":"DEP-001","predecessor_ref":"TASK-001","successor_ref":"TASK-004","type":"finish_to_start","reason":"UI contract depends on endpoint shape","evidence_refs":["TASK-001","TASK-004"],"confidence_label":"high"}.

### RiskDraft

Fields: temp_id; category technical/schedule/scope/dependency/security/quality/external; description; probability unlikely/possible/likely; impact low/medium/high/critical; trigger; mitigation; contingency; related_refs list; source_fact_refs list. Severity is calculated by code, not supplied by the model.

Example: {"temp_id":"RISK-001","category":"schedule","description":"Checkout integration may compress testing","probability":"possible","impact":"high","trigger":"Checkout incomplete by MS-003 target","mitigation":"Prototype provider contract early","contingency":"Use documented test gateway only","related_refs":["MS-003"],"source_fact_refs":["CONSTRAINT-DEADLINE"]}.

### ClarificationQuestion

Fields: temp_id; question; reason; affects list[scope/schedule/architecture/quality/cost]; required bool; answer_type text/single_choice/multi_choice/boolean/date/number; options list[str,0..6]; default_assumption optional str; source_fact_refs. Choice types require 2–6 options; required questions may have a default only if safe and explicitly labeled.

Example: {"temp_id":"Q-001","question":"Is online payment required for the first release?","reason":"It changes scope and compliance work","affects":["scope","schedule"],"required":true,"answer_type":"single_choice","options":["Required","Sandbox only","Excluded"],"default_assumption":null,"source_fact_refs":["REQ-CHECKOUT"]}.

### RecommendationDraft

Fields: temp_id; type enum from FR-019; detection_code; evidence_refs list[1..20]; why_it_matters; suggested_action; expected_impact; urgency low/medium/high/immediate; risk; approval_required bool; verification_step; alternatives list[str,1..5]. All numeric/date facts must occur in evidence snapshot; unsupported text rejects the draft.

Example: {"temp_id":"REC-001","type":"dependency_warning","detection_code":"BLOCKED_CRITICAL_TASK","evidence_refs":["TASK-014","DEP-009","FORECAST-2026-08-28"],"why_it_matters":"Two downstream tasks cannot start","suggested_action":"Resolve the API contract blocker before starting dependent UI work","expected_impact":"Restores the critical-path sequence","urgency":"high","risk":"Delaying other noncritical work","approval_required":true,"verification_step":"Mark TASK-014 ready only after its blocker is closed","alternatives":["Reduce dependent scope in a new draft"]}.

### WeeklyReportNarrative

Fields: title; period_summary; completed_items list[CitedStatement]; progress_statement CitedStatement; blockers list[CitedStatement]; risks list[CitedStatement]; next_actions list[CitedStatement]; decisions_needed list[CitedStatement]; caveats list[str]. CitedStatement has text and evidence_refs. It cannot introduce IDs or numbers absent from ReportData.

Example: {"title":"Weekly report — 13–19 July","period_summary":"Catalog work advanced; checkout is blocked.","completed_items":[{"text":"TASK-003 completed.","evidence_refs":["EVENT-301"]}],"progress_statement":{"text":"Weighted progress is 42%.","evidence_refs":["METRIC-PROGRESS"]},"blockers":[],"risks":[],"next_actions":[],"decisions_needed":[],"caveats":[]}.

## 15. Tool and Service Contracts

| Contract | Input | Output | Side effects/failures |
|---|---|---|---|
| ProjectContextReader | owner_id, project_id, version selector, field allowlist | Versioned ProjectContext + content hash | Read-only; 403/404 indistinguishable to unauthorized callers |
| StructuredModelProvider | prompt version, JSON schema, sanitized context, budget, safety ID | Parsed candidate, response/model ID, usage, latency, refusal | No DB writes; timeout/rate/refusal/schema error typed |
| DraftValidator | candidate bundle, project facts | ValidationReport with errors/warnings | Pure; error paths point to stable temp IDs |
| GraphEngine | version-local tasks/edges | DAG result, order, cycle, readiness, centrality | Pure; invalid references fail closed |
| PriorityEngine | factor values and graph | score, label, factor breakdown | Pure; weight config version returned |
| SchedulingEngine | tasks, DAG, calendar, capacity, as_of | ScheduleResult/feasibility | Pure and deterministic for same inputs |
| ProgressEngine | leaf tasks/status/progress/effort | task/milestone/project metrics | Pure; reports unestimated effort |
| HealthEngine | forecast/deadline/progress/blockers/slack | label, rule codes, evidence | Pure; no narrative |
| ChangeImpactEngine | baseline plus proposed changes | diff, affected nodes, schedule/health/risk deltas | Pure virtual clone |
| ReportAggregator | period, version, events | immutable ReportData | Read-only; cursor/hash supplied |
| MarkdownRenderer | ReportData + validated narrative | sanitized Markdown | No model call; neutralizes formula/HTML injection |
| PDFRenderer | stored report ID | PDF bytes/hash | Full version; sandboxed Chromium, timeout |
| AuditRecorder | actor, action, target, references, request ID | audit_event_id | Append-only in caller transaction |
| JobQueue | job type, scoped input ref, idempotency key | job ID/status | Durable insert/claim/heartbeat/cancel |

Tool descriptions exposed to models are narrower than these application services. MVP model calls receive data and return schemas; they do not receive database-write, messaging, filesystem or external-system tools.

## 16. Deterministic Algorithms and Pseudocode

### Dependency validation and topological order

~~~text
validate_graph(tasks, edges, version):
  ids = IDs of tasks in version
  seen = empty set
  for edge in edges:
    reject if either endpoint not in ids
    reject if predecessor == successor
    reject if pair already in seen
    add pair to seen and adjacency
  indegree = calculate indegrees
  queue = all zero-indegree IDs in stable-key order
  while queue:
    node = pop first
    append node to order
    decrement successors; enqueue new zeroes
  if len(order) != len(ids):
    run color DFS on remaining nodes and return the first closed cycle path
  return valid, order
~~~

Complexity: O(V+E) time and memory. Cycle errors return stable task keys in path order.

### Ready tasks

~~~text
for each active-version task:
  ready = status not in {completed,cancelled,blocked}
          and every predecessor status == completed
          and all dependency endpoints are in active version
  projection status becomes ready only from pending;
  in_progress remains in_progress.
~~~

### Priority score

Normalize each factor to 0..100:

score = 0.30×MVP necessity + 0.20×dependency centrality + 0.20×deadline urgency + 0.15×user value + 0.10×risk reduction + 0.05×user preference.

Centrality is 100 × reachable downstream tasks / max(1,total_tasks−1). Urgency is piecewise from slack: 100 at ≤0 working days, 80 at 1–2, 60 at 3–5, 40 at 6–10, 20 above 10. Labels: Critical ≥85; High 65–84.99; Medium 40–64.99; Low <40. No more than 25% may be Critical unless each has nonzero urgency or high centrality; quality gate flags saturation rather than changing scores.

### Weighted progress

Use leaf tasks only. Cancelled tasks are excluded from numerator and denominator from the cancellation event forward; historical reports retain their earlier baseline. Unestimated active leaves are excluded from the percentage but their effort count is reported; health becomes Insufficient data when they exceed 20% of active leaf count or expected effort cannot be bounded. Completed=1, status progress uses explicit latest fraction otherwise pending/ready=0, in_progress/blocked=stored fraction, completed=1. Added scope enters denominator on activation; removed scope requires a new version and remains visible in comparison.

~~~text
progress = sum(likely_effort × fraction) / sum(likely_effort)
milestone uses its descendant leaves; project uses all active leaves.
~~~

### MVP scheduler

1. Validate DAG and calculate stable topological order.
2. Expand WorkCalendar into per-working-day available hours from project start.
3. Track daily project capacity = team_size × hours_per_day × availability factor and parallel task limit.
4. For each ready task in priority/order sequence, choose earliest working slot after every predecessor finish with capacity in its workstream.
5. Allocate likely effort across working days; record start/finish.
6. Add configurable project buffer default 10% of scheduled working days after task placement, not hidden inside estimates.
7. Compare forecast with deadline and return shortfall hours/days and blocking path.

MVP assumes pooled capacity and workstream tags, not named assignments. It is deterministic but heuristic; it never claims optimality.

### Advanced scheduler and critical path

Full version adds per-workstream capacity, task parallelism/resource eligibility, range scenarios and list-scheduling heuristics. Critical path runs forward/backward passes over the DAG using working-hour durations: ES=max predecessor EF; EF=ES+duration; LF=min successor LS from project finish; LS=LF−duration; slack=LS−ES. Slack ≤ one scheduling quantum is critical. Complexity O(V+E) after calendar operations.

### Completion forecast

Baseline uses the schedule of remaining likely effort as of today. If at least three reporting periods contain actual effort, calculate capped velocity = completed planned hours / available capacity hours, winsorized to 0.5..1.25, and show baseline plus velocity-adjusted scenario. Never show a success probability.

### Health rules, evaluated in order

1. Completed: all noncancelled leaf tasks complete.
2. Insufficient data: no active plan/deadline/calendar, invalid graph, or unestimated threshold exceeded.
3. Delayed: deadline passed incomplete; forecast after deadline; or overdue incomplete critical milestone.
4. At risk: remaining buffer ≤10% of remaining planned duration; blocked effort ≥15% of remaining effort; any critical-path task blocked; milestone forecast > target; or capacity overload >10%.
5. On track: none of the above.

Result includes rule code, evaluated values, evidence references and calculation version.

### Change impact

Clone baseline structures; apply validated add/change/remove operations; revalidate graph; find directly changed nodes and all reachable successors; recompute milestone effort, schedule, critical path, forecast, health and risk-rule triggers; compare report metrics; return before/after values and affected stable IDs. The clone is discarded unless a separate owner-approved draft transaction applies it.

## 17. API Design

### API conventions

JSON uses snake_case. Mutations require session, CSRF header and If-Match row version where applicable. Workflow starts require Idempotency-Key. Errors use {type,title,status,code,detail,errors,request_id}. List endpoints use cursor pagination. Every write documents its audit event. 401 is unauthenticated; unauthorized resource lookups return 404; 409 is lifecycle/concurrency/idempotency conflict; 422 is validation; 429 includes Retry-After.

| Method/path | Purpose and primary schema | Authorization/validation | Side effects/audit |
|---|---|---|---|
| POST /api/v1/auth/session | Login → SessionView + CSRF token | Public; rate limited | SessionCreated |
| DELETE /api/v1/auth/session | Logout | Current user | Revoke session; SessionRevoked |
| GET/POST /api/v1/projects | List/Create ProjectCreate→ProjectView | Authenticated; date/timezone/capacity | ProjectCreated |
| GET/PATCH/DELETE /api/v1/projects/{id} | Read/update/archive | Owner; If-Match | ProjectUpdated/Archived |
| GET/PUT /projects/{id}/requirements | List/replace draft requirements | Owner; kinds/source rules | RequirementsChanged |
| GET/PUT /projects/{id}/constraints | List/replace constraints | Owner | ConstraintsChanged |
| GET /projects/{id}/analysis | Current selected-version analysis | Owner | None |
| GET/POST /projects/{id}/clarifications | List/answer questions | Owner; answer schema | ClarificationAnswered; may enqueue resume |
| POST /projects/{id}/planning-runs | Start PlanningRunRequest→AgentRunView | Owner; idempotency; no conflicting run | Job/run insert; PlanningStarted |
| GET/POST /agent-runs/{id}/cancel | Poll/cancel | Owner | Cancellation requested/audited |
| GET /agent-runs/{id}/steps | Trace views with redacted references | Owner | None |
| GET /projects/{id}/plan-versions | Version summaries | Owner | None |
| GET /plan-versions/{id} | Draft/active plan graph | Owner | None |
| PATCH /plan-versions/{id} | Edit draft metadata/analysis | Owner; draft only; If-Match | DraftEdited |
| POST /plan-versions/{id}/validate | Run quality/graph/schedule validation | Owner; idempotent by content hash | Validation result |
| POST /plan-versions/{id}/submit-review | draft→under_review | Owner; quality gate | PlanReviewStarted |
| POST /plan-versions/{id}/approve | Approve and activate | Owner; exact content hash | Atomic approval/activation |
| POST /plan-versions/{id}/archive | Archive nonsole active version | Owner | PlanArchived |
| GET /plan-versions/{a}/compare/{b} | Deterministic diff | Same owner/project | None |
| POST /plan-versions/{id}/regenerations | Start selective proposal | Owner; draft targets only | Full version job/audit |
| GET/POST/PATCH/DELETE /plan-versions/{id}/milestones | Milestone CRUD | Owner; draft only; stable/sequence rules | DraftMilestoneChanged |
| GET/POST/PATCH/DELETE /plan-versions/{id}/tasks | Task CRUD | Owner; draft only except status API | DraftTaskChanged |
| POST /tasks/{id}/status | StatusTransitionRequest | Owner; active version and legal transition | Event, projection, monitoring job |
| POST /tasks/{id}/estimate | EstimateUpdateRequest | Owner; active change creates draft proposal | EstimateChangeProposed/updated draft |
| GET/POST/DELETE /plan-versions/{id}/dependencies | Manage edges | Owner; draft only; DAG validation | DependencyChanged |
| GET /projects/{id}/progress | Current weighted metrics | Owner | None |
| GET /projects/{id}/health | Health result/evidence | Owner | None |
| GET /projects/{id}/recommendations | Filter recommendations | Owner | None |
| POST /recommendations/{id}/{accept|dismiss|defer} | Record decision | Owner; state transition | RecommendationDecision; no implicit plan mutation |
| GET/POST/PATCH /plan-versions/{id}/risks | Risk register | Owner; full version | RiskChanged |
| POST /projects/{id}/scenarios | Run virtual scenario | Owner; allowed overrides/idempotency | Scenario/run created |
| GET /scenarios/{id} | Baseline comparison | Owner | None |
| GET/POST /projects/{id}/reports | List/start report | Owner; period/type/idempotency | Run/report created |
| GET /reports/{id} | Stored JSON/Markdown metadata | Owner | None |
| GET /reports/{id}/export.md | Download sanitized Markdown | Owner; safe filename | ReportExported |
| GET /reports/{id}/export.pdf | Generate/download PDF | Owner; full version; rate limit | ReportExported/ExportFailed |

API request/response models are generated into OpenAPI; frontend API types are generated in CI only when the generated diff is committed intentionally.

## 18. Frontend Design

### Route and screen map

| Route/screen | Data and calls | Main interactions | States, accessibility, responsive tests |
|---|---|---|---|
| /projects dashboard | GET projects | Open/create/archive | Skeleton, first-project CTA, retry; headings/landmarks; cards→list |
| /projects/new create | POST project | Guided form/save/start planning | Inline errors, date/timezone help; focus summary; 360 px |
| /projects/:id/planning | run/steps polling | Observe/cancel/resume | Step states pending/running/completed/failed/skipped/waiting; aria-live |
| /projects/:id/clarify | questions/answers | Answer/accept assumption | Required indicators, saved draft, keyboard groups |
| /projects/:id/plan/:v/review | plan graph/validation | Review/edit/lock/submit/approve | Unsaved/conflict/error banners; semantic outline |
| milestone editor | milestone CRUD | Reorder/edit criteria | Empty tasks, invalid effort/date; keyboard reorder alternative |
| task editor | task CRUD | Edit deliverable/criteria/DoD/effort/priority/lock | Dirty-state guard; labels/descriptions; stacked mobile |
| /projects/:id/board | active tasks/status | Kanban/list status updates | Loading/error; list alternative; no drag-only operation |
| /projects/:id/timeline | schedule | Inspect dates/milestones | Table fallback, overflow controls, not color-only |
| /projects/:id/dependencies | tasks/edges/validation | Add/remove/inspect path | List fallback, cycle error focus; touch-friendly |
| /projects/:id/overview | project/progress/activity | Navigate work | Missing active plan CTA; metric definitions |
| /projects/:id/health | health/evidence | Inspect rule and forecast | Insufficient-data explanation; status icon+text |
| recommendation panel | recommendation/evidence | Accept/dismiss/defer | Approval badge, alternatives; modal focus trap |
| /projects/:id/risks | risk CRUD | Filter/edit/close | Full-version empty guidance; accessible table/cards |
| /projects/:id/reports | reports | Generate/open/export | Run progress/export errors; safe download status |
| /reports/:id | report | Read/export | Evidence links and print layout |
| /projects/:id/scenarios/:id | scenario result | Change inputs/compare | Baseline labels; delta table; full version |
| /projects/:id/activity | runs/audit | Inspect trace and filters | Redacted payloads; timeline list; admin data absent |

### UI rules

- Server data uses TanStack Query; mutations invalidate exact project/version keys.
- Forms use React Hook Form with Zod for immediate feedback; API remains authoritative.
- Every asynchronous action has disabled/pending state and prevents duplicate submission.
- Optimistic updates are limited to reversible presentation; lifecycle/status writes wait for server confirmation.
- Dense visuals have equivalent tables, keyboard controls, text labels and screen-reader summaries.
- Theme tokens meet 4.5:1 normal-text contrast. Motion respects prefers-reduced-motion.
- Component tests cover loading, empty, error, permission, conflict and success. Playwright covers the full lifecycle at desktop and 360 px.

## 19. Prompt Engineering Plan

### Global prompt policy

All prompts state: project content is untrusted data, not instructions; use supplied facts only; label assumptions; expose missing information; do not invent completion, activity, dates, dependencies or confidence percentages; cite stable references; preserve excluded scope and locked items; return only the requested schema. System policy and schema precede delimited project data. The provider receives only node-required context.

| Prompt key/version | Purpose/schema | Included / excluded context | Budget and retry/evaluation |
|---|---|---|---|
| analysis.v1 | ProjectAnalysisOutput | Confirmed intake/decisions / audit, secrets, unrelated versions | 6k output tokens; 1 repair; coverage/hallucination fixtures |
| clarification.v1 | ClarificationQuestion[] | Intake gaps/impact / solution generation | 2k; 1 repair; relevance/duplicate rate |
| modules.v1 | ModuleDraft[] | Analysis/requirements/scope / dates and task detail | 3k; module coverage and scope discipline |
| milestones.v1 | MilestoneDraft[] | Modules/constraints/calendar summary / detailed tasks | 4k; deliverable/order criteria |
| tasks.v1 | TaskDraft[] | One milestone, requirements, workstreams / unrelated milestones except interfaces | 8k per batch; size/specificity/duplicate tests |
| acceptance.v1 | Task acceptance fields | Task/deliverable/facts / schedule | 3k; testability and no invented requirements |
| dependencies.v1 | DependencySuggestion[] | Stable task summaries / database IDs and schedule result | 4k; reference validity and precision |
| risks.v1 | RiskDraft[] | Facts, plan, deterministic warnings / generic risk catalog | 3k; relevance/grounding |
| recommendations.v1 | RecommendationDraft[] | Detected conditions/evidence / full raw history | 3k; every claim grounded |
| weekly_report.v1 | WeeklyReportNarrative | Immutable ReportData / model memory and hidden events | 4k; factual consistency |
| change_impact.v1 | Explanation object | Deterministic diff/result / permission to apply | 3k; delta coverage/no mutation |
| scenario.v1 | Explanation object | Baseline/scenario comparison / active-write tools | 3k; trade-off accuracy |

Each prompt directory contains at least two short examples: a positive schema example drawn from the matching fixture and an adversarial example showing the required rejection/labeling behavior. Analysis demonstrates a user-stated requirement versus an assumption; clarification avoids asking a known fact; modules/milestones/tasks show stable references and one deliverable; acceptance shows observable criteria; dependencies reject a plausible but unsupported edge; risks cite a constraint; recommendations cite a detection snapshot; report/change/scenario examples preserve exact supplied metrics. Examples never include current dates, model-written completion claims or hidden reasoning.

Prompts use lean, outcome-focused instructions, stable prefixes, explicit stopping conditions and small relevant examples. Prompt versions are immutable and linked to runs. Model alias, reasoning effort and verbosity are configuration per prompt; baseline uses gpt-5.6-terra through Responses and evaluates same effort plus one lower before tuning. Optional persisted reasoning, Pro, programmatic tool calling, explicit caching and multi-agent behavior are excluded until an isolated evaluation demonstrates benefit.

## 20. Human Approval and Plan Versioning

### Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> idea
    idea --> clarification_required
    idea --> generating
    clarification_required --> generating
    generating --> draft
    generating --> clarification_required
    generating --> archived: cancelled
    draft --> under_review
    under_review --> draft: changes requested
    under_review --> approved
    approved --> active: atomic activation
    active --> superseded: newer version activated
    draft --> archived
    superseded --> archived
~~~

- Every version is a complete snapshot with based_on_id, reason and content hash.
- Stable keys make comparisons meaningful; database IDs remain version-specific.
- Approval signs the exact content hash. Any edit invalidates review/approval and increments row_version.
- Only one active version exists per project. Activation supersedes the previous version atomically.
- User edits set source=user and protected=true; locks explicitly block AI replacement.
- Active changes are proposals: create a derived draft, compute impact, and require approval.
- Old tasks, milestones, estimates, dates, decisions and approvals remain queryable.
- Diff categories: added, removed, content changed, estimate changed, date changed, dependency changed, lock/source changed.

## 21. Security and Privacy

- Passwords use Argon2id with calibrated parameters; opaque random sessions are stored only as hashes and sent via Secure, HttpOnly, SameSite=Lax cookies.
- State-changing requests require CSRF token plus origin validation. Login and AI endpoints are rate limited by IP and user.
- Owner scoping is mandatory in queries and services; object-level authorization tests cover every resource.
- Project text is bounded, normalized and treated as data. Prompt delimiters, instruction hierarchy, field allowlists and output schemas defend against prompt injection.
- Rendered Markdown strips raw HTML, unsafe URLs, scripts and spreadsheet-style formula prefixes in downloads. React never uses unsanitized inner HTML.
- SQLAlchemy parameterization, Pydantic validation, strict IDs and CSRF/CSP headers address SQL injection, malformed input, CSRF and XSS.
- OPENAI_API_KEY and database credentials come from secret injection; .env is ignored and only .env.example is proposed.
- Provider context is minimized by node; store=false; safety identifier is a one-way stable user hash; raw prompts/responses are not application logs.
- Run traces store structured outputs and hashes/references, with configurable redaction for sensitive text.
- Exports require owner authorization, use unpredictable URLs only within authenticated responses, safe Content-Disposition names and no public object ACL.
- Worker executes no arbitrary code or filesystem paths from project text. PDF Chromium runs without network, with time/memory limits.
- Dependency scanning, secret scanning, SAST and container scanning run in CI. Critical/high release findings block.
- Account/project erasure is an explicit audited workflow; immutable audit content is minimized and actor identifiers can be pseudonymized.

## 22. Reliability and Recovery

- Checkpoint after every workflow node; never set completed unless every required node succeeded.
- Timeouts: ordinary model call 90 s; large generation 180 s; entire planning run 10 min; PDF 60 s. Values are configurable.
- Transient provider/network errors retry twice with jittered exponential backoff. 4xx validation/refusal does not blindly retry.
- One schema-repair attempt; business validation returns structured errors and at most one semantic regeneration attempt.
- Partial results persist as candidate references but are not visible as valid drafts until quality gate and transaction succeed.
- Worker heartbeat every 15 s; a job becomes reclaimable after 90 s without heartbeat. Claim token prevents stale worker commit.
- Cancellation is cooperative between nodes and before model calls; committed audit/checkpoint data remains.
- Idempotency key scope is user + route + project; same key/different payload returns 409.
- Optimistic row_version protects edits. Approval locks rows and rechecks hash/version in the transaction.
- Provider outage leaves the project usable for deterministic operations; AI start returns queued/degraded guidance.
- Factual reports can complete without narrative as partial; UI clearly labels narrative unavailable.
- Backups use encrypted pg_dump or provider-native snapshots nightly; restore procedure verifies schema, row counts, active-version invariant and sample report hashes.
- User errors include recovery action and request ID. Operations alerts on stuck jobs, repeated schema failures, budget exhaustion and restore-test failure.

## 23. Observability and Cost Control

### Telemetry

- Structured JSON logs: timestamp, level, service, environment, request_id, user_hash, project_id, run_id, step, event, duration and safe error code.
- OpenTelemetry traces span HTTP, DB transaction, job claim, workflow node, provider call, validator, scheduler and renderer.
- Metrics: request rate/latency/errors; job queue age and retries; node success/duration; model latency/tokens/cached tokens/cost/refusals; schema/business failures; graph errors; schedule duration; exports; approvals; recommendation decisions; post-generation edit rate.
- Dashboards: API health, worker health, AI quality/cost, product funnel and report/export reliability.
- Alerts: p95 error spike, oldest queued job >5 min, provider failure >20% over 10 min, daily cost budget >80%, repeated duplicate claims, backup failure.

### Cost controls

- Prompt-specific input/output token caps and per-run maximum calls.
- Per-user daily planning/report limits with visible remaining quota.
- Stable prompt prefixes and context field allowlists; no full history when summarized references suffice.
- Default balanced model; lower-cost tier may be evaluated for extraction/narrative but never routed without contract results.
- Record model-returned usage and a versioned price-table estimate; label estimate rather than billing truth.
- Abort safely before exceeding the configured run budget and preserve partial checkpoint.
- Evaluation tracks cost per successful plan, not cost per call alone.

## 24. Testing Strategy and Requirement-to-Test Matrix

### Test layers

- Unit: graph, priority, progress, calendars, schedule, critical path, forecast, health, impact, transitions and schema rules.
- Database: FKs/checks/uniques, plan isolation, single active version, approval hash, immutable events, job claiming and concurrent edits on PostgreSQL.
- API integration: authentication/CSRF/ownership, project lifecycle, idempotency, errors and audit side effects.
- Workflow: fake provider happy/clarification/invalid/retry/partial/resume/cancel/reject/regenerate paths.
- LLM contract: strict schemas, unique refs, enums, specificity, size, references, scope exclusion and no invented completed work.
- Prompt regression: fixed fixtures scored against thresholds; prompt/model changes require comparison.
- Frontend: components, interactions, accessibility, conflicts, polling, forms, board, evidence, reports and responsive layouts.
- E2E: create → clarify → generate → edit/lock → selectively regenerate → approve → update/block → health/recommendation → report/export → reload.
- Security: injection, unauthorized IDs, malicious HTML/Markdown, oversized input, CSRF, rate limit and export filename/content.
- Performance: thresholds from NFR-007–009 and graph sizes at 100/500/1,000 tasks.

### Requirement-to-test matrix

| Requirements | Primary tests |
|---|---|
| FR-001–004 | API project/clarification integration; analysis/clarification contracts; create-flow E2E |
| FR-005–008 | Schema, database version-isolation, graph unit and draft API tests |
| FR-009–010 | Priority/scheduler unit, deadline fixture and performance tests |
| FR-011–014 | Draft concurrency, lifecycle/approval DB, lock/regeneration workflow and review UI tests |
| FR-015–018 | Transition, event, progress, monitoring and health rule tests |
| FR-019–022 | Evidence validator, decision API, risk/scenario/impact unit and UI tests |
| FR-023–027 | Report factuality, export security, trace, audit and version diff tests |
| FR-028 | Dashboard component, permission, empty/error and responsive E2E |
| NFR-001–002 | Security suite, provider-payload snapshot/redaction tests |
| NFR-003–005 | Resume/failure workflow, database constraints and explainability snapshots |
| NFR-006–009 | axe/keyboard, API load, graph benchmark and timed workflow suite |
| NFR-010–014 | Concurrent worker, architecture boundary and fake-provider tests |
| NFR-015–020 | Idempotency, restore drill, mobile E2E, timezone fixtures, safe-error and OpenAPI compatibility tests |

Release coverage gates: deterministic domain ≥90% branch; application/API ≥80% branch; no threshold for generated migrations but every migration has integration coverage. Flaky tests are quarantined only with an owner, issue and seven-day deadline.

## 25. AI Evaluation Strategy

### Dataset

Versioned JSONL fixtures contain fixture_id, project intake, confirmed requirements, excluded scope, expected module concepts, required task concepts, forbidden claims, allowed assumptions, deadline/capacity, reference risk concepts and reviewer labels. Store inputs under backend/tests/fixtures/evals/ and results outside source control or as small reviewed baselines under docs/evals/.

Required scenarios:

1. E-commerce website.
2. Football scouting platform.
3. University attendance system.
4. Mobile expense tracker.
5. AI Production Incident Investigator.
6. Small marketing website.
7. Data analytics dashboard.
8. Intentionally impossible deadline.

### Metrics and thresholds

| Metric | Formula | Release threshold |
|---|---|---|
| Module coverage | expected concepts represented / expected concepts | ≥0.85 average; no fixture <0.70 |
| MVP scope discipline | 1 − unsupported MVP items / generated MVP items | ≥0.95 |
| Task specificity | rubric-passing leaf tasks / leaf tasks | ≥0.90 |
| Acceptance quality | criteria passing observable/testable rubric / criteria | ≥0.90 |
| Task-size compliance | leaves with likely effort 4–24 h / estimated leaves | ≥0.90 |
| Duplicate rate | duplicate clusters beyond first / tasks | ≤0.03 |
| Missing-task rate | missing required concepts / required concepts | ≤0.10 |
| Dependency validity | accepted valid edges / proposed edges | ≥0.98; zero accepted cycles |
| Estimate plausibility | estimates within labeled expert band / tasks with band | ≥0.80 |
| Schedule feasibility | deterministic result matches oracle feasible/infeasible label | 1.00 |
| Risk relevance | reviewer-relevant risks / generated risks | ≥0.80 |
| Recommendation grounding | claims with valid stored evidence / factual claims | 1.00 |
| Report factual accuracy | factual statements matching ReportData / factual statements | 1.00 |
| Hallucination rate | unsupported factual requirements/claims / factual claims | ≤0.01; zero severe |
| Structured success | valid without repair / calls | ≥0.95; ≥0.99 after repair |
| Human edit distance | normalized changed fields before approval | Track baseline; investigate >0.35 |
| Latency/cost | p50/p95 duration and cost per successful run | No >20% regression without approved quality gain |

### Runner and regression

The runner executes fake deterministic tests on every PR and provider-backed evaluation manually/nightly when credentials and budget are available. It records prompt hash, schema version, model/returned model, reasoning configuration, seed where supported, timestamps, usage, validation attempts, metric results and reviewer annotations. A candidate fails if a hard factual/graph threshold fails or a metric drops by >5 percentage points from the accepted baseline. Model aliases are not accepted as reproducible baselines; record the returned model and pin a supported snapshot for formal comparisons.

## 26. Sample Data and Demo Fixtures

| Fixture | Purpose | Key facts and expected behavior |
|---|---|---|
| ecommerce_six_weeks | Main university demo | 3 people, 6 weeks; catalog/cart/checkout/auth/testing/deployment; asks payment/inventory questions; feasible or scoped warning based on answers |
| football_scouting_eight_weeks | Rich modular plan | 3 developers, 8 weeks; profiles/reports/search/comparison/auth/test/deploy; no invented live-data provider |
| attendance_system | Privacy/risk | University roles and attendance; flags personal-data/access/audit concerns |
| expense_tracker_mobile | Cross-platform constraints | Offline capture, categorization, reports; clarifies platform/sync |
| marketing_site_small | Avoid overengineering | 1–2 weeks; concise plan, no unnecessary microservices |
| analytics_dashboard | Data dependencies | Clarifies sources/freshness/permissions; valid ingestion-before-visualization edges |
| incident_investigator | AI-specific safety | Separates evidence collection, inference and human incident decisions |
| impossible_deadline | Infeasibility | One person, complex commerce, five days; scheduler must warn, not compress estimates |

Seeds include user, project intake, expected clarifications, a generated draft, active version, task events, blocked critical task, evidence-grounded recommendation and weekly report. Secrets and real personal data are never fixtures.

## 27. Implementation Phases

Every path below is **Proposed**. “Modify” means modifying a file created in an earlier phase.

### Phase 1 — Repository foundation

- Objective: establish runnable monorepo shells and engineering conventions.
- Dependencies: none.
- Create: backend/pyproject.toml, backend/app/main.py, frontend/package.json, frontend/src/app/, compose.yaml, .env.example, README.md.
- Modify: none. Database: connection configuration only, no tables.
- Backend: settings, health endpoint, error envelope and dependency boundaries. Frontend: router, layout, API client shell and design tokens. AI: provider interface placeholder only.
- Tests: backend health test, frontend render/type test, Compose configuration check.
- Acceptance/exit: API and SPA start locally; health is green; secrets are not committed; architecture boundaries documented.
- Complexity: M. Risks: version drift and premature dependencies; mitigate with lockfiles and minimal packages.

### Phase 2 — Identity and persistence

- Objective: secure sessions, ownership and the core relational foundation.
- Dependencies: Phase 1.
- Create: db/base.py, db/models/identity.py, db/models/project.py, auth/, migrations/versions/0001_*.py.
- Modify: main.py, API router, settings, frontend login shell.
- Database: User, Session, Project, Requirement, Constraint, WorkCalendar, AuditEvent; indexes/checks.
- Backend: Argon2id, opaque sessions, CSRF, owner-scoped project CRUD, audit transaction hook. Frontend: login and project list/create primitives. AI: none.
- Tests: PostgreSQL constraints, session/CSRF, owner isolation, project CRUD, concurrency.
- Acceptance/exit: two users cannot observe each other’s IDs/data; project intake persists; audit is appended.
- Complexity: L. Risks: authorization gaps; mitigate service-level owner scoping and negative tests.

### Phase 3 — Deterministic planning core

- Objective: implement trusted graph, scoring, progress, schedule and health engines.
- Dependencies: Phase 2 domain value types.
- Create: domain/graph.py, priority.py, progress.py, calendar.py, scheduler.py, health.py and unit fixtures.
- Modify: domain types/config.
- Database: none beyond calculation-version configuration. Backend: pure functions and typed results. Frontend: none. AI: none.
- Tests: cycles with returned path, topo order, readiness, scoring boundaries, progress edge cases, DST/calendars, infeasible schedule and health precedence.
- Acceptance/exit: deterministic repeatability and ≥90% branch coverage; 1,000-task benchmark <2 s.
- Complexity: L. Risks: false precision and calendar bugs; mitigate ranges, rule codes and property-based tests.

### Phase 4 — AI contracts and prompts

- Objective: establish provider portability, strict schemas, prompt versions and safe validation.
- Dependencies: Phases 1 and 3 contracts.
- Create: ai/provider.py, ai/openai_provider.py, ai/schemas/, ai/prompts/, ai/validation.py, fake_provider.py.
- Modify: settings, telemetry.
- Database: PromptVersion and provider usage fields. Backend: Responses adapter with store disabled, safety identifier, refusal/usage handling. Frontend: none.
- AI: implement the 12 schemas and initial prompt catalog; no write tools.
- Tests: schema examples, malformed/refusal/truncation, prompt injection, fake-provider parity and usage capture.
- Acceptance/exit: every output passes the validation ladder; tests need no network; model/config is not hard-coded.
- Complexity: L. Risks: SDK/API change and schema brittleness; mitigate adapter boundary and contract fixtures.

### Phase 5 — Persistent planning workflow

- Objective: produce a validated, resumable draft through the complete multi-stage planning graph.
- Dependencies: Phases 2–4.
- Create: workflow engine/nodes, worker/job models, planning services, plan domain models and migrations.
- Modify: AI prompts, API run routes, telemetry.
- Database: PlanVersion, analysis, clarification, decision, milestone, task, dependency, risk candidate, AgentRun/Step/Job.
- Backend: node checkpoints, retries, idempotent run start, quality gate and atomic draft persistence. Frontend: polling data client only.
- AI: analysis through risk nodes. Tests: happy/clarification/repair/failure/resume/cancel/duplicate runs.
- Acceptance/exit: a fixture becomes a validated draft; required failure cannot appear complete; restart resumes.
- Complexity: XL. Risks: partial inconsistency and long runs; mitigate referenced snapshots, transactions and bounded batches.

### Phase 6 — Draft lifecycle and approval

- Objective: safe review, editing, locking, validation and immutable activation.
- Dependencies: Phase 5.
- Create: plan services/routes, approval model/migration, diff primitives and lifecycle policy.
- Modify: task/milestone services, audit and quality gate.
- Database: approvals, content hashes, single-active constraint, row versions, protected/source fields.
- Backend: draft CRUD, If-Match conflicts, review and atomic activation. Frontend: API hooks only. AI: locked fields excluded from generation context/output targets.
- Tests: lifecycle table, content hash mismatch, concurrent edit, lock protection and one-active invariant.
- Acceptance/exit: only the owner activates an unchanged validated draft; prior version remains intact.
- Complexity: L. Risks: version corruption; mitigate row locks, hash recheck and full snapshot versions.

### Phase 7 — Planning frontend

- Objective: complete project creation through plan approval in an accessible UI.
- Dependencies: Phases 5–6 APIs.
- Create: project, planning, clarification, review, milestone/task editor pages and reusable state components.
- Modify: router, query keys, forms, styles.
- Database/backend: only API refinements discovered by contract tests. Frontend: all planning/review screens, conflict handling and responsive behavior. AI: display concise run summaries, never chain-of-thought.
- Tests: components, axe, keyboard, API mocking and create-to-approval Playwright flow.
- Acceptance/exit: a 360 px or desktop keyboard user completes the planning lifecycle with clear progress/errors.
- Complexity: XL. Risks: dense review UX; mitigate progressive disclosure and list-first alternatives.

### Phase 8 — Active execution

- Objective: manage active tasks and compute truthful readiness, progress, schedule and health.
- Dependencies: Phases 3, 6 and 7.
- Create: status/progress models and routes, monitoring projections, board/overview/health pages.
- Modify: scheduler services, audit, query hooks.
- Database: TaskStatusEvent and ProgressUpdate; task projection indexes.
- Backend: legal transitions, event append, monitoring enqueue and recalculation. Frontend: board with accessible list alternative and evidence views. AI: none required for calculations.
- Tests: transition concurrency, readiness propagation, weighted progress, blocked critical task and UI/E2E.
- Acceptance/exit: status events survive reload and produce expected metric/health changes.
- Complexity: L. Risks: stale derived values; mitigate state hashes and transactional enqueue.

### Phase 9 — Monitoring and reporting

- Objective: turn deterministic detections into grounded actions and factual reports.
- Dependencies: Phase 8.
- Create: Recommendation/Evidence and Report models, monitoring/report workflows, report/recommendation UI.
- Modify: worker, provider prompts, Markdown sanitization.
- Database: recommendations/evidence/reports and dedup indexes.
- Backend: rule detectors, evidence validator, recommendation decisions, report aggregation/export. Frontend: panels, report list/detail/export. AI: explanations and narrative only.
- Tests: unsupported-claim rejection, dedup, period aggregation, malicious Markdown and report lifecycle.
- Acceptance/exit: blocked fixture yields a cited recommendation and factually exact weekly Markdown.
- Complexity: L. Risks: persuasive unsupported text; mitigate claim-to-evidence validation and deterministic source data.

### Phase 10 — MVP hardening

- Objective: make Phases 1–9 secure, observable, recoverable and demonstrably within thresholds.
- Dependencies: all MVP features.
- Create: threat model, load tests, OpenTelemetry config, backup/restore scripts and MVP release checklist.
- Modify: rate limits, redaction, CSP, timeouts, budgets, CI.
- Database: retention and backup verification. Backend/frontend/AI: hardening only, no scope expansion.
- Tests: security, performance, failure injection, restore drill and full MVP E2E/evaluation.
- Acceptance/exit: all MVP FR/NFR gates pass; no critical/high security finding; five fixtures pass; runbook exists.
- Complexity: L. Risks: late cross-cutting defects; mitigate security/telemetry work in earlier phases plus this gate.

### Phase 11 — Full-version intelligence

- Objective: advanced re-planning without unsafe active-plan mutation.
- Dependencies: stable MVP and sufficient fixture history.
- Create: regeneration, comparison, advanced scheduler, critical path, scenario and impact services/models/routes.
- Modify: plan workflow, graph engine, prompt catalog.
- Database: Scenario and full risk relations; regeneration proposals.
- Backend: virtual clones, diffs, protected replacements, advanced capacity and critical path. Frontend: API hooks/basic result tables. AI: change/scenario explanations only after deterministic results.
- Tests: locked-item preservation, cross-version references, schedule deltas, virtual isolation and approval.
- Acceptance/exit: regeneration changes only selected draft fields; scenario never changes active state.
- Complexity: XL. Risks: combinatorial scheduler/UI expectations; label heuristic behavior and benchmark.

### Phase 12 — Full-version experience

- Objective: professional visual analysis, PDF and evaluation visibility.
- Dependencies: Phase 11.
- Create: dependency graph, Gantt/timeline, risk register, scenario comparison, evaluation dashboard and PDF renderer.
- Modify: report UI and Compose Chromium image.
- Database: evaluation-result metadata if dashboard persistence is enabled. Backend: secure PDF/eval endpoints. Frontend: accessible visualizations with table alternatives. AI: no new autonomous behavior.
- Tests: graph/timeline keyboard/table parity, visual snapshots, PDF content/hash/security and dashboard permissions.
- Acceptance/exit: full-version insights are understandable without color/drag and PDF matches stored report facts.
- Complexity: L. Risks: bundle/render complexity; lazy-load visuals and reuse Playwright.

### Phase 13 — University release

- Objective: reproducible deployment and a polished evidence-backed demonstration.
- Dependencies: Phases 10–12.
- Create: eight seeds, demo reset command, CI workflow, deployment/backup/operator docs and scripted demo.
- Modify: Compose production profile, README and release checklist.
- Database: seed/reset restricted to development/demo; final restore rehearsal.
- Backend/frontend/AI: fix release blockers only. Tests: clean-machine setup, full demo, browser reload/persistence and CI from scratch.
- Acceptance/exit: another engineer can deploy and run the 23-step demo from documentation; all 72 backlog items meet DoD.
- Complexity: M. Risks: environment-specific failures; mitigate generic containers, pinned lockfiles and rehearsal.

## 28. File-by-File Change Map

| Path | Existing/Proposed | Action | Purpose | Main Changes | Tests |
|---|---|---|---|---|---|
| IMPLEMENTATION%20PLAN.MD | Existing | Reuse unchanged | Source specification | None | Hash comparison |
| backend/pyproject.toml | Proposed | Create | Python dependencies/tooling | FastAPI, SQLAlchemy, tests, lint/type config | Lock/install check |
| backend/app/main.py | Proposed | Create | API composition | Lifespan, routers, errors, telemetry | Health/API smoke |
| backend/app/core/ | Proposed | Create | Settings/errors/security primitives | Typed config, IDs, time, problem details | Unit |
| backend/app/auth/ | Proposed | Create | Sessions/CSRF/authorization | Password/session and owner policies | Security/API |
| backend/app/db/ | Proposed | Create | Database infrastructure/models | Engine, sessions, models, repositories | PostgreSQL integration |
| backend/migrations/ | Proposed | Create | Versioned schema | Eight migration groups | Upgrade/schema |
| backend/app/domain/ | Proposed | Create | Trusted deterministic core | Graph, progress, priority, calendars, scheduling, health, impact | ≥90% branch/benchmarks |
| backend/app/services/ | Proposed | Create | Transactions/use cases | Projects, plans, tasks, reports, audit | Integration |
| backend/app/api/v1/ | Proposed | Create | REST surface | Auth and all domain resources | OpenAPI/API |
| backend/app/ai/ | Proposed | Create | Provider/prompt/contracts | OpenAI adapter, schemas, prompt versions, validation | Contract/eval |
| backend/app/workflows/ | Proposed | Create | Persistent state machines | Planning, monitoring, reporting, regeneration, scenario | Workflow |
| backend/app/workers/ | Proposed | Create | Durable asynchronous execution | DB claim, heartbeat, resume, cancellation | Concurrency/failure |
| backend/app/observability/ | Proposed | Create | Logs/traces/metrics/cost | OpenTelemetry and redaction | Telemetry assertions |
| backend/tests/ | Proposed | Create | Backend verification | Unit, DB, API, workflow, security, performance, eval fixtures | CI suites |
| frontend/package.json | Proposed | Create | Client dependencies/scripts | React/Vite/query/forms/tests | Lock/type/build |
| frontend/src/app/ | Proposed | Create | Router/providers/layout | Auth, query, error boundary | Component |
| frontend/src/api/ | Proposed | Create | Typed API client | Fetch, CSRF, errors, query keys | Unit/contract |
| frontend/src/features/ | Proposed | Create | Product modules | Projects, planning, plans, tasks, health, reports, scenarios | Component/E2E |
| frontend/src/components/ | Proposed | Create | Accessible shared UI | Forms, dialogs, data states, evidence | axe/keyboard |
| frontend/src/styles/ | Proposed | Create | Design tokens/responsiveness | Theme, layouts, reduced motion | Visual/responsive |
| frontend/tests/ | Proposed | Create | UI/E2E coverage | Component, accessibility, Playwright | CI |
| compose.yaml | Proposed | Create | Local/reference deployment | API, worker, frontend, PostgreSQL, profiles | Config/smoke |
| infra/docker/ | Proposed | Create | Reproducible images | Multi-stage builds, Chromium full profile | Image scan/smoke |
| .github/workflows/ci.yml | Proposed | Create | Proposed CI | Lint/type/test/build/scan | Workflow dry validation |
| README.md | Proposed | Create | Developer entrypoint | Setup, commands, architecture and demo | Clean-machine rehearsal |
| docs/ | Proposed | Create | Architecture/operations/evals | Threat model, runbooks, demo, decisions | Link/checklist review |

## 29. Detailed Engineering Backlog

All files are **Proposed** except the unchanged source specification. Items are ordered by phase and dependency.

| ID | Title | Description | Files | Dependencies | Acceptance criteria | Tests | Priority | Complexity | Phase |
|---|---|---|---|---|---|---|---|---|---:|
| ARCH-001 | Establish monorepo boundaries | Define backend/frontend/infra layout, dependency direction and command conventions. | README.md; backend/; frontend/ | None | Layout and boundary rules match Section 9 and startup docs work. | Structure/smoke | Must | M | 1 |
| ARCH-002 | Define shared configuration strategy | Add typed environment settings, safe defaults, validation and .env.example without secrets. | backend/app/core/config.py; .env.example | ARCH-001 | Missing required production values fail fast; secrets never log. | Config unit | Must | S | 1 |
| BE-001 | Bootstrap FastAPI service | Implement lifespan, /health/live, /health/ready, problem errors and v1 router. | backend/app/main.py; backend/app/api/ | ARCH-001, ARCH-002 | API starts and both health checks reflect dependencies. | API smoke | Must | M | 1 |
| FE-001 | Bootstrap React application | Add Vite React shell, router, query provider, error boundary and design tokens. | frontend/src/app/; frontend/src/styles/ | ARCH-001 | Production build renders accessible shell and route fallback. | Type/build/component | Must | M | 1 |
| DEVOPS-001 | Create local Compose stack | Build API, worker placeholder, frontend and PostgreSQL services with health checks. | compose.yaml; infra/docker/ | ARCH-001, BE-001, FE-001 | One documented command starts healthy stack; volumes are explicit. | Compose config/smoke | Must | M | 1 |
| DB-001 | Create identity schema | Add User and Session models/migration with unique normalized email, hashes, expiry and revocation. | db/models/identity.py; migrations/0001_identity.py | BE-001 | Constraints/indexes match Section 11; plaintext tokens/passwords never persist. | PostgreSQL schema | Must | M | 2 |
| DB-002 | Create project intake schema | Add Project, Requirement, Constraint and WorkCalendar with ownership/time checks. | db/models/project.py; migrations/0002_projects.py | DB-001 | Owner/date/timezone/capacity constraints reject invalid rows. | DB integration | Must | L | 2 |
| DB-003 | Create audit schema | Add append-only AuditEvent and transaction-aware recorder. | db/models/audit.py; services/audit.py; migration | DB-001 | Covered writes create correlated events; update/delete is denied through service. | DB/service | Must | M | 2 |
| BE-002 | Implement sessions and project CRUD | Add Argon2id login, CSRF, logout, owner-scoped project/requirement/constraint/calendar APIs. | auth/; api/v1/projects.py; services/projects.py | DB-001, DB-002, DB-003 | Auth and FR-001/002 work; unauthorized resource access returns 404. | Auth/API/ownership | Must | L | 2 |
| SEC-001 | Enforce identity attack controls | Add login rate limit, secure cookies, origin checks, constant-time token comparison and safe errors. | auth/security.py; middleware/ | BE-002 | Session controls satisfy Section 21 and expose no sensitive error detail. | CSRF/rate/timing tests | Must | M | 2 |
| TEST-001 | Verify persistence and ownership baseline | Build PostgreSQL fixtures and concurrent two-owner lifecycle tests. | backend/tests/db/; backend/tests/api/ | DB-001, DB-002, BE-002 | Constraints, isolation, audit and optimistic project updates pass. | Integration | Must | M | 2 |
| ALG-001 | Implement dependency validator | Reject missing, self, duplicate, cross-version edges and return a concrete cycle path. | domain/graph.py | DB-002 | Behavior and O(V+E) contract match Section 16. | Unit/property | Must | M | 3 |
| ALG-002 | Implement topological order and readiness | Produce stable topo order, downstream reachability and ready-task projections. | domain/graph.py | ALG-001 | All order/readiness edge cases and invalid version references pass. | Unit/property | Must | M | 3 |
| ALG-003 | Implement priority scoring | Normalize factors, calculate centrality/urgency, labels and auditable breakdown. | domain/priority.py | ALG-002 | Boundary scores and saturation warning are deterministic. | Unit/table | Must | M | 3 |
| ALG-004 | Implement weighted progress | Calculate leaf-only task/milestone/project progress and unestimated warnings. | domain/progress.py | ALG-002 | Cancelled, parent, added/removed scope and blocked cases match rules. | Unit/property | Must | M | 3 |
| ALG-005 | Implement working calendar | Expand timezone-aware working hours, holidays and effective capacity. | domain/calendar.py | DB-002 | DST/weekend/holiday fixtures produce correct working slots. | Unit | Must | L | 3 |
| ALG-006 | Implement MVP scheduler | Greedy list-schedule topological tasks against pooled capacity and buffer. | domain/scheduler.py | ALG-002, ALG-003, ALG-005 | Dates respect prerequisites/capacity and impossible deadlines warn. | Unit/performance | Must | L | 3 |
| ALG-007 | Implement forecast and health rules | Produce forecast and precedence-ordered health with evidence/rule codes. | domain/health.py | ALG-004, ALG-006 | Completed/insufficient/delayed/risk/on-track fixtures match exact rules. | Unit | Must | M | 3 |
| AI-001 | Define provider abstraction | Specify typed request/result/refusal/usage/errors and fake provider. | ai/provider.py; ai/fake_provider.py | ARCH-002 | Domain/workflow code imports no OpenAI types and tests run offline. | Interface/unit | Must | M | 4 |
| AI-002 | Implement OpenAI Responses adapter | Call configurable model with strict schema, store=false, safety ID, timeout and usage capture. | ai/openai_provider.py | AI-001 | Adapter handles success/refusal/truncation/rate/timeout without logging content. | Mock SDK contract | Must | M | 4 |
| AI-003 | Implement structured AI schemas | Add all nine semantic output Pydantic schemas and common reference constraints. | ai/schemas/outputs.py | AI-001 | Examples parse; additional fields, bad IDs and cross-field errors fail. | Schema unit | Must | L | 4 |
| AI-004 | Implement agent state schemas | Add planning, monitoring and reporting states with completion invariants. | workflows/state.py | AI-003 | Persisted examples round-trip and invalid terminal states fail. | State unit | Must | M | 4 |
| AI-005 | Create prompt registry | Add 12 immutable prompt templates, versions, hashes, budgets and data delimiters. | ai/prompts/; db/models/prompt.py | AI-003, DB-003 | Every key has schema/budget/global policy and used versions cannot change. | Prompt snapshot | Must | L | 4 |
| AI-006 | Build validation and repair ladder | Compose schema, ID, business, permission and deterministic checks with one repair. | ai/validation.py | AI-003, ALG-001 | Invalid content never reaches persistence; failures are machine-readable. | Contract/injection | Must | L | 4 |
| DB-004 | Create planning and run schema | Add PlanVersion, analysis, question, decision, milestones, tasks, dependencies, risks, runs, steps and jobs. | db/models/plan.py; db/models/run.py; migrations/ | DB-002, AI-004 | Version locality, stable keys, edge uniqueness and job indexes are enforced. | PostgreSQL schema | Must | XL | 5 |
| BE-003 | Implement durable workflow engine | Add node registry, checkpoint, claim, heartbeat, retry, cancel, resume and stale-claim protection. | workflows/engine.py; workers/ | DB-004 | Crash/restart resumes exactly once from last committed checkpoint. | Failure/concurrency | Must | L | 5 |
| BE-004 | Implement planning run API | Add idempotent run start, status, step trace, cancellation and clarification resume. | api/v1/runs.py; services/runs.py | BE-003, BE-002 | Duplicate keys are safe; trace is owner-scoped/redacted. | API/idempotency | Must | M | 5 |
| BE-005 | Persist validated plan drafts atomically | Convert temporary refs to UUIDs and write the complete valid graph in one transaction. | services/planning.py | DB-004, AI-006, ALG-006 | No partial draft is visible; temp references map uniquely and audit exists. | DB/workflow | Must | L | 5 |
| AI-007 | Implement planning semantic nodes | Connect clarification, analysis, modules, milestones, tasks, acceptance and risk prompts. | workflows/planning_nodes.py | AI-005, AI-006, BE-003 | Each node uses minimal context and emits referenced validated output. | Mock workflow/contract | Must | XL | 5 |
| AI-008 | Implement planning quality gate | Check coverage, task specificity/size, duplicates, graph, schedule, scope and assumptions. | services/plan_quality.py | AI-007, ALG-001–007 | Failed must-check blocks draft completion with actionable errors. | Quality fixtures | Must | L | 5 |
| TEST-002 | Test full planning workflow | Cover happy, clarification, repair, semantic retry, refusal, budget, partial, resume, cancel and duplicate starts. | tests/workflows/test_planning.py | BE-003–005, AI-007, AI-008 | All required workflow branches pass using fake provider. | Workflow | Must | L | 5 |
| DB-005 | Add approvals and active-version invariants | Create approvals, hashes, source/protection fields and one-active-version constraint. | db/models/plan.py; migration | DB-004 | Approval is append-only; at most one active version exists. | DB concurrency | Must | M | 6 |
| BE-006 | Implement draft editing and validation APIs | Add milestone/task/dependency CRUD, locking, If-Match and plan validation. | api/v1/plans.py; services/plans.py | DB-005, AI-008 | Only drafts edit; lock/source and graph rules are preserved. | API/graph/conflict | Must | L | 6 |
| BE-007 | Implement approval and activation | Atomically validate hash, approve, activate and supersede prior version. | services/approval.py; api/v1/plans.py | BE-006 | Only owner activates exact reviewed content; events/audit are complete. | Transaction/concurrency | Must | L | 6 |
| SEC-002 | Protect plan lifecycle authorization | Centralize owner, draft-only, active-only and approval policies. | auth/policies.py | BE-006, BE-007 | Route/service matrix denies every invalid actor/state combination. | Authorization matrix | Must | M | 6 |
| TEST-003 | Verify draft/version lifecycle | Test transitions, conflicts, hashes, locks, invalid edges and historical immutability. | tests/api/test_plan_lifecycle.py | BE-006, BE-007, SEC-002 | FR-011–013 and single-active invariant pass under concurrency. | API/DB | Must | L | 6 |
| FE-002 | Build project intake flow | Implement project form for dates, timezone, capacity, constraints, required/excluded scope and notes. | features/projects/ | FE-001, BE-002 | Incomplete valid input saves; errors/focus/mobile behavior meet spec. | Component/E2E | Must | L | 7 |
| FE-003 | Build planning progress view | Poll run/steps, show six states, retries/failures, cancel and resume links. | features/planning/RunProgress.tsx | FE-001, BE-004 | Progress updates without duplicate polling and aria-live is useful. | Component/polling | Must | M | 7 |
| FE-004 | Build clarification experience | Render typed questions, answers, explicit assumptions and resume action. | features/planning/Clarifications.tsx | FE-003, BE-004 | Required answers gate resume; keyboard and saved-state behavior pass. | Component/E2E | Must | M | 7 |
| FE-005 | Build draft review screen | Present analysis, assumptions, modules, milestones, tasks, dependencies and validation. | features/plans/PlanReview.tsx | FE-003, BE-006 | Users distinguish AI/user/deterministic content and find errors by ID. | Component/axe | Must | L | 7 |
| FE-006 | Build milestone and task editors | Add accessible edit, move, criteria, DoD, effort, priority and lock controls. | features/plans/editors/ | FE-005 | Dirty/conflict states work; no drag-only operation; locks display. | Component/keyboard | Must | L | 7 |
| FE-007 | Build review and approval controls | Submit, validate, display hash/version conflict and approve with confirmation. | features/plans/ApprovalPanel.tsx | FE-005, BE-007 | Approval targets exact version; stale UI cannot activate. | E2E/concurrency | Must | M | 7 |
| DB-006 | Add task execution history | Create TaskStatusEvent and ProgressUpdate plus projection indexes. | db/models/execution.py; migration | DB-005 | Events append; fractions/checks and task/time indexes are valid. | DB integration | Must | M | 8 |
| BE-008 | Implement task status service | Enforce transitions/readiness, append event/audit, update projection and enqueue monitoring. | services/execution.py; api/v1/tasks.py | DB-006, ALG-002 | Illegal/stale updates fail; valid update is atomic and idempotent. | API/concurrency | Must | L | 8 |
| BE-009 | Implement progress and health APIs | Recompute/store state-hashed metrics and expose evidence-rich results. | services/monitoring.py; api/v1/insights.py | BE-008, ALG-004, ALG-007 | Results match active version and stale runs cannot overwrite new state. | Service/API | Must | M | 8 |
| ALG-008 | Implement monitoring detectors | Detect overdue, blocked, unmet, milestone, buffer, scope, capacity, ready and inconsistent conditions. | domain/monitoring.py | ALG-002, ALG-006, ALG-007 | Each detection returns stable code and concrete evidence references. | Unit/table | Must | L | 8 |
| FE-008 | Build execution and health UI | Add board/list, overview, progress, health rules and status-change controls. | features/tasks/; features/health/ | BE-008, BE-009 | Reload preserves state; blocked task changes progress/health visibly. | Component/E2E/axe | Must | L | 8 |
| TEST-004 | Verify active execution lifecycle | Test transitions, readiness propagation, event history, blocked critical task and stale recomputation. | tests/execution/; frontend E2E | BE-008, BE-009, FE-008 | FR-015–018 scenario passes end to end. | Unit/API/E2E | Must | L | 8 |
| DB-007 | Add recommendations and reports | Create Recommendation, Evidence and Report with dedup/content hashes. | db/models/insights.py; migration | DB-006 | Evidence immutable; open duplicates prevented; reports retain JSON/Markdown. | DB integration | Must | M | 9 |
| BE-010 | Implement recommendation and report services | Add evidence validation, decisions, aggregation, Markdown rendering and export APIs. | services/recommendations.py; services/reports.py | DB-007, ALG-008 | Unsupported claims reject; decisions audit; factual data drives output. | Service/API/security | Must | L | 9 |
| AI-009 | Implement monitoring/report narratives | Generate constrained recommendation explanations and weekly narratives from evidence/data. | workflows/monitoring.py; workflows/reporting.py | AI-005, BE-010 | Every factual statement cites valid evidence; refusal yields usable partial result. | Contract/factuality | Must | L | 9 |
| FE-009 | Build recommendations and reports UI | Add evidence panel, decisions, report list/detail and Markdown download. | features/recommendations/; features/reports/ | BE-010, AI-009 | Owner can inspect evidence and export safe factual report. | Component/E2E | Must | L | 9 |
| TEST-005 | Verify grounding and reporting | Test dedup, unsupported numbers, periods, malicious content, decisions and reload. | tests/insights/; frontend E2E | BE-010, AI-009, FE-009 | Grounding/report accuracy is 100% on deterministic fixtures. | Contract/API/E2E | Must | L | 9 |
| OBS-001 | Instrument runs and product outcomes | Add correlated request/run/model traces and approval/edit/recommendation metrics. | observability/; services/telemetry.py | BE-010 | Required spans/metrics exist with redacted attributes and stable IDs. | Telemetry assertions | Must | M | 9 |
| ARCH-003 | Conduct MVP architecture and threat review | Verify boundaries, data flows, approval gates, dependency rationale and threat model. | docs/architecture.md; docs/threat-model.md | Phases 1–9 | Review has no unresolved Must issue and diagrams match code contracts. | Checklist/review | Must | M | 10 |
| SEC-003 | Harden input, output and abuse controls | Add CSP, sanitization, size/rate limits, export safety, secret/SAST/dependency scans. | middleware/; reports/sanitize.py; CI | SEC-001, SEC-002, BE-010 | Security suite passes; no critical/high release finding. | Security/scan | Must | L | 10 |
| OBS-002 | Add SLO dashboards, budgets and alerts | Implement queue/API/provider/cost dashboards, per-run/user budgets and alert rules. | observability/; docs/runbooks/ | OBS-001 | Budget exhaustion is safe; alerts fire in controlled tests. | Failure/metrics | Must | M | 10 |
| TEST-006 | Run MVP acceptance and performance suite | Build complete E2E, 1,000-node benchmark, load test, injection and restore drill. | tests/e2e/; tests/performance/; docs/restore.md | ARCH-003, SEC-003, OBS-002 | All MVP FR/NFR gates and five fixtures pass. | Full acceptance | Must | XL | 10 |
| DEVOPS-002 | Build continuous verification pipeline | Add lint, type, unit, PostgreSQL, frontend, E2E, build and scans with caches/artifacts. | .github/workflows/ci.yml | TEST-006 | Clean CI executes ordered gates and retains safe reports. | Workflow validation | Must | L | 10 |
| ARCH-004 | Specify advanced planning contracts | Freeze regeneration, diff, scenario, critical path and impact I/O and approval boundaries. | docs/architecture-advanced.md | ARCH-003 | Contracts prohibit active mutation and align API/domain/UI. | Design review | Should | M | 11 |
| DB-008 | Add scenario and advanced risk schema | Create Scenario, regeneration proposal and risk relation tables. | db/models/scenario.py; migration | ARCH-004, DB-007 | Virtual results/reference ownership/version rules are constrained. | DB integration | Should | M | 11 |
| BE-011 | Implement advanced planning services | Add selective regeneration, comparison, advanced schedule, critical path, scenarios and impact. | services/regeneration.py; domain/critical_path.py; domain/impact.py | DB-008, ALG-006, BE-007 | Locks survive; diffs are complete; active version is unchanged without approval. | Unit/workflow/API | Should | XL | 11 |
| AI-010 | Implement change/scenario explanations | Use deterministic result objects for explanation prompts and validate all deltas/evidence. | workflows/regeneration.py; prompts/change_* | BE-011, AI-005 | Narrative introduces no unsupported change, date or risk. | Contract/eval | Should | M | 11 |
| TEST-007 | Verify advanced intelligence | Cover selective fields, lock attacks, cycles, version isolation, critical path and virtual scenarios. | tests/advanced/ | BE-011, AI-010 | FR-014, FR-022 and FR-027 pass including negative paths. | Unit/API/workflow | Should | L | 11 |
| ARCH-005 | Define visualization and PDF architecture | Choose React Flow, accessible alternatives, lazy loading and sandboxed Chromium reuse. | docs/architecture-ui.md | ARCH-004 | Dependency and operational costs plus fallbacks are documented. | Design/accessibility review | Should | S | 12 |
| BE-012 | Implement risk, evaluation and PDF APIs | Add full risk CRUD, evaluation result read and authenticated sandboxed PDF rendering. | api/v1/advanced.py; services/pdf.py | BE-011, ARCH-005 | PDF content matches report hash; permissions/timeouts/network isolation pass. | API/security/render | Should | L | 12 |
| FE-010 | Build full-version visual experience | Add dependency graph, Gantt, risk register, scenario compare and evaluation dashboard. | features/advanced/ | BE-012, ARCH-005 | Every visual has keyboard/table alternative and responsive behavior. | Component/visual/E2E | Should | XL | 12 |
| TEST-008 | Verify full-version experience | Test accessibility parity, graph scale, scenarios, PDF, dashboard permissions and visual regressions. | frontend/tests/advanced/; backend/tests/pdf/ | BE-012, FE-010 | Phase 12 acceptance and NFR-006/008 pass. | Axe/performance/render | Should | L | 12 |
| ARCH-006 | Perform release architecture review | Confirm final implementation, data model, contracts, dependencies and scope match this plan. | docs/release-review.md | Phases 1–12 | No unresolved Must/Should inconsistency for university release. | Traceability review | Must | M | 13 |
| DEVOPS-003 | Package vendor-neutral release | Finalize production Compose profile, migrations, health, backups and clean deployment rehearsal. | compose.yaml; infra/docker/; docs/deploy.md | ARCH-006, DEVOPS-002 | Clean Linux host deploy and restore meet RPO/RTO procedure. | Deployment/restore | Must | L | 13 |
| DOC-001 | Create operator and developer documentation | Document setup, architecture, commands, config, security, workflows, troubleshooting and recovery. | README.md; docs/operations/ | DEVOPS-003 | New engineer completes setup and common recovery without undocumented steps. | Clean-machine doc test | Must | M | 13 |
| DOC-002 | Create university demo package | Add eight seeds, reset command, 23-step script, expected outputs and evidence checklist. | docs/demo.md; backend/tests/fixtures/demo/ | DOC-001, TEST-008 | Rehearsed demo completes, persists across reload and matches expected outputs. | Demo rehearsal | Must | M | 13 |

Backlog totals: ARCH 6, DB 8, BE 12, AI 10, ALG 8, FE 10, TEST 8, SEC 3, OBS 2, DEVOPS 3, DOC 2; overall 72.

## 30. Risks and Mitigations

| Risk | Probability | Impact | Mitigation | Fallback |
|---|---|---|---|---|
| Generic tasks | Medium | High | Task schema, size/specificity gate, fixtures and human review | Regenerate affected milestone or edit draft |
| Hallucinated requirements | Medium | Critical | Fact refs, assumption types, excluded scope and claim validation | Block approval and request clarification |
| Unrealistic estimates | High | High | Ranges, deterministic normalization/scheduler and warnings | Use conservative max scenario/manual estimate |
| Invalid/circular dependencies | Medium | High | Version-local FK plus DAG validator and cycle path | Reject edge set and retain last valid draft |
| Overly large plans | Medium | High | Module/milestone/task caps and batched generation | Ask owner to narrow MVP or split project |
| Model cost | Medium | Medium | Budgets, minimal context, balanced default and cost-per-success eval | Disable narrative/regeneration; deterministic features remain |
| Slow generation | Medium | Medium | Async runs, progress, batching, timeout and resume | Partial checkpoint plus retry later |
| Duplicate runs | Medium | High | Idempotency keys, unique jobs, atomic claiming/input hashes | Return original run; operator reconciles orphan |
| Prompt injection | Medium | Critical | Treat text as data, minimal tools, delimiters, strict schemas, redaction | Reject output/run and surface safe error |
| Incorrect reports | Low | Critical | Deterministic ReportData and evidence validation | Deliver factual JSON/metrics without narrative |
| Inconsistent versions | Medium | Critical | Complete snapshots, hashes, row locks, single-active constraint | Abort activation and rebuild draft from active |
| Poor recommendation grounding | Medium | High | Detection codes, immutable evidence and 100% claim gate | Suppress recommendation and show raw condition |
| User overreliance | Medium | High | Approval boundaries, explanations, uncertainty labels and alternatives | Require explicit acknowledgment for high-impact action |
| UI complexity | High | Medium | Progressive disclosure, list alternatives and staged delivery | Ship table/list MVP; defer rich visual |
| Schedule overrun | High | High | Phase exit gates, Must/Should boundary and risk tracking | Stop at Phase 10 credible MVP |
| Scope expansion | High | High | Versioned scope, excluded features and change impact | Create proposed version; do not alter active scope |
| Provider failure | Medium | High | Adapter, retries, fake provider, checkpoints and deterministic availability | Queue/retry or operate without AI narrative |
| Database job contention | Low | High | Indexed SKIP LOCKED claim, heartbeats and bounded workers | Reduce worker count and repair stuck claims |
| SQLite parity gap | Medium | Medium | PostgreSQL CI is authoritative; SQLite single-worker only | Use local PostgreSQL profile |

## 31. Definition of Done

The product is done when:

- A user can create a constrained project, answer clarification, receive a structured draft, inspect assumptions and distinguish AI from deterministic results.
- Modules, milestones and actionable leaf tasks have deliverables, acceptance criteria, DoD, effort, workstream, source and valid references.
- Dependencies form a validated version-local DAG; schedule and priority are deterministic and explainable.
- The user can edit/lock content, validate, approve and activate an immutable version; selective regeneration affects only approved draft targets in the full version.
- Status changes append history and recalculate readiness, weighted progress, forecast and health.
- Blockers/overdue work yield evidence-grounded recommendations; decisions are audited and do not silently mutate the active plan.
- Reports derive from stored state/events, survive reload and export safe Markdown; full version exports matching PDF.
- What-if scenarios and change impact never modify active data.
- Agent runs expose state, retries, validation, usage and safe failures without chain-of-thought.
- Security, accessibility, performance, backup/restore, deterministic, workflow, contract, E2E and evaluation gates pass.
- Five MVP fixtures and all eight university evaluation fixtures meet thresholds.
- A clean environment can deploy and run the demonstration using documented commands.
- Every Must backlog item, and every Should item required for the university version, meets its acceptance criteria and tests.

## 32. University Demonstration Script

Scenario: “Build an e-commerce website in six weeks with a three-person team.”

1. Log in as the seeded owner and create the project with 120 team-hours/week, Monday–Friday calendar and Africa/Cairo timezone.
2. Enter required catalog, cart, checkout, authentication, testing and deployment; exclude marketplace and native mobile apps.
3. Start planning and show the persisted run ID plus step progress.
4. Answer whether payment is real or sandbox and whether inventory is manual.
5. Show analysis: shoppers/admin, MVP boundary, confirmed requirements, explicit assumptions and open questions.
6. Show modules such as foundation, catalog, commerce, operations and quality—not generic “backend/frontend” tasks.
7. Show deliverable-based milestones in dependency order.
8. Open TASK-001-style tasks with one deliverable, 0.5–3 day estimate, criteria and DoD.
9. Show dependency validation and legal topological order.
10. Show capacity schedule, project buffer and deadline feasibility/warning.
11. Inspect deterministic priority factor breakdown.
12. Inspect initial risk warnings tied to deadline/payment facts.
13. Edit one acceptance criterion and verify source becomes user.
14. Lock that task.
15. Selectively regenerate a different milestone; show protected item unchanged.
16. Compare proposed diff/impact and apply it only to the draft.
17. Validate, approve and activate the exact content hash.
18. Complete two ready tasks; show immutable events and weighted progress increase.
19. Block a critical task with a reason; show downstream readiness and forecast update.
20. Show health change to At risk with rule code and task/dependency evidence.
21. Open the grounded recommendation, alternatives and verification step; defer it and show audit event.
22. Generate the weekly report; verify task IDs, progress and blocker facts against activity.
23. Export Markdown (and PDF in full version), reload the browser and confirm active version, history, recommendation decision and report persist.

Representative expected records:

- Analysis: “Six-week owner-operated commerce MVP for shoppers and an administrator”; assumption “sandbox payment provider until Q-001 is answered”; excluded “marketplace, native apps”.
- Milestone MS-002: “Purchasing flow demonstrable”; deliverable “A tested cart-to-sandbox-checkout vertical slice”; acceptance “A seeded shopper can add two products, refresh, check out in sandbox and see a persisted order.”
- Task TASK-014: “Persist idempotent checkout result”; likely effort 16 hours; predecessor TASK-011 “Define order/payment state contract”; acceptance includes duplicate provider callback and failed-payment cases.
- Dependency: TASK-011 → TASK-014 because persistence cannot be implemented safely before order/payment states are defined; the edge is still accepted only after deterministic DAG validation.
- Health: At risk; code BLOCKED_CRITICAL_TASK; evidence TASK-014, its downstream path and the recalculated forecast—not a probability.
- Recommendation: resolve or reduce the blocked checkout contract in a new draft; approval_required=true; verification requires TASK-014 readiness and an updated schedule.
- Report statement: “Weighted project progress is 18%” cites the stored METRIC-PROGRESS snapshot; “TASK-003 and TASK-004 completed” cites their status-event IDs.

Expected sample outputs are fixture assertions, not fixed model prose: required module coverage ≥85%, zero accepted invalid/cyclic edges, all report facts supported, impossible schedule surfaced if the confirmed payment scope exceeds capacity, and the locked task identical before/after regeneration.

## 33. Future Integrations

Integrations are separate adapters behind approval-gated commands and are not MVP dependencies:

- GitHub: import issues/PR evidence and propose status mappings; writes require per-action approval.
- Jira: map projects/issues/dependencies with conflict handling and source provenance.
- Slack and Microsoft Teams: prepare notification drafts; sending requires approval and audited destination preview.
- Google Calendar and Outlook Calendar: read working constraints or propose milestone events; creation/update requires approval.
- Email: prepare weekly report delivery; recipient/content confirmation precedes sending.
- Resource assignment: named-member skills/capacity with privacy and fairness review.
- Budget tracking: planned/actual cost without unsupported forecasting.
- Portfolio management: cross-project capacity and risk only after workspace tenancy exists.
- Webhooks/MCP: signed, least-privilege integrations with replay protection, rate limits and scoped credentials.

Each integration requires threat model, permission matrix, idempotency, reconciliation, revocation, audit, failure recovery and a no-write dry-run mode. The active plan remains authoritative until an owner approves an explicitly shown synchronization change.
