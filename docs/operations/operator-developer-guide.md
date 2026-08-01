# Operator and developer guide

Version: `0.13.0`

This is the command-level handoff for a new engineer. Architecture rationale lives
in [architecture](../architecture.md), advanced behavior in
[advanced architecture](../architecture-advanced.md), and release deployment in
[vendor-neutral deployment](../deploy.md).

## Repository areas

| Area | Responsibility |
|---|---|
| `backend/app/api/v1/` | Versioned REST transport and authentication dependencies |
| `backend/app/services/` | Transactions, authorization-aware use cases, audit |
| `backend/app/domain/` | Deterministic graph, schedule, progress, priority, health |
| `backend/app/workflows/` | Persisted planning, monitoring, and reporting state machines |
| `backend/app/ai/` | Provider adapter, schemas, prompts, validation, usage accounting |
| `frontend/src/` | Accessible React application and API adapters |
| `backend/migrations/` | Ordered PostgreSQL/SQLite schema history |
| `infra/` | Backup, observability, and clean-release verification |

The model may propose structured content. Authorization, identifiers, graph
validation, scheduling, progress, priority, health, evidence, and activation remain
deterministic server responsibilities.

## Development setup

Prerequisites: Python 3.12, `uv` 0.11.29, Node 24, npm, Docker, Compose, and Ollama for live local planning.

```sh
cd backend
uv sync --locked --group dev
uv run playwright install chromium
uv run alembic upgrade head
uv run pytest

cd ../frontend
npm ci
npm run typecheck
npm run test:run
npm run build
```

Or start the development stack:

```sh
docker compose up --build
```

The development API is `http://localhost:8000`; Vite is
`http://localhost:5173`. Development defaults must never be reused in production.

## Configuration

Settings are environment variables validated by `backend/app/core/config.py`.

| Group | Required behavior |
|---|---|
| Database | PostgreSQL is mandatory in production; SQLite is single-worker local only |
| Sessions | unique 32+ character hash secret, Argon2 passwords, HttpOnly session cookie |
| Browser | exact CORS origin, CSRF cookie/header, `COOKIE_SECURE=true` in production |
| Provider | local Ollama by default; configurable URL, model, context, timeout, schema repair, and budgets |
| Worker | database leases, heartbeat, retry limits, resumable checkpoints |
| PDF | Chromium timeout, output limit, and concurrency bound |
| Observability | safe structured attributes; no prompts, cookies, passwords, or raw PII |

Use `.env.example` for development, `.env.demo.example` for the synthetic demo,
and `.env.production.example` only as a template.

The frontend serves `index.html` with `Cache-Control: no-cache`, caches
content-hashed assets for one year, and returns HTTP 404 for missing assets.
Already-open tabs recover once from Vite preload errors after a deployment; a
cooldown prevents reload loops and a route-level fallback keeps raw developer
errors out of the user experience.

## Routine verification commands

```sh
cd backend
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest --cov=app --cov-branch --cov-fail-under=85

cd ../frontend
npm run lint
npm run typecheck
npm run test:run
npm run build
npm run test:e2e

cd ..
docker compose -f compose.demo.yaml config --quiet
sh infra/release/verify-demo.sh
```

The source specification `IMPLEMENTATION%20PLAN.MD` is immutable. The release test
pins its SHA-256 digest.

## Application workflows

- Project creation persists owner-scoped intake, requirements, constraints, and
  calendar facts.
- Planning starts an idempotent database job and exposes run/step progress.
- Every AI result passes schema, reference, permission, and deterministic business
  validation before a draft transaction.
- Draft edits use row versions. User edits and locks are protected.
- The university fixtures retain a generated draft beside each independently
  approved active plan so version isolation can be inspected after reload.
- Approval binds the exact persisted content hash and creates an immutable active
  version plus execution projections.
- Task mutations append events, update readiness, and trigger deterministic
  monitoring.
- Recommendations cite stored evidence and never mutate an active plan.
- Reports aggregate persisted state/events; narrative failure leaves a complete
  factual Markdown report.
- Scenarios are immutable calculations and cannot write into active data.
- Selective-regeneration proposals target draft fields only, preserve locked and
  protected content, and require a separate owner decision before any draft change.

## Demo reset

Run only against the dedicated demo database:

```sh
cp .env.demo.example .env.demo
docker compose --env-file .env.demo -f compose.demo.yaml up -d db
docker compose --env-file .env.demo -f compose.demo.yaml run --rm migrate
docker compose --env-file .env.demo -f compose.demo.yaml --profile reset run --rm seed
docker compose --env-file .env.demo -f compose.demo.yaml up -d api worker frontend
```

On Windows, start the local Ollama-backed demo from the repository root:

```powershell
& .\infra\release\start-local-ollama.ps1
```

The helper keeps Ubuntu WSL alive, confirms `llama3.1:8b` is installed, updates the
ignored demo environment, starts the containers, and performs one schema-constrained
probe through the worker. If Ollama is unavailable, project-only saves remain
available and planning admission is rejected before a run or quota reservation.

Known synthetic credentials:

- Email: `demo.owner@example.com`
- Password: `SyntheticDemoOnly!2026`

These values are public demonstration data, not secrets. The reset command deletes
all rows in the dedicated demo database. It refuses production/staging, a database
without `demo` in its name, a missing password environment variable, or an
incorrect confirmation literal.

## Troubleshooting

| Symptom | Check | Resolution |
|---|---|---|
| API not ready | `docker compose ... logs migrate api` | Fix migration/config; do not bypass the gate |
| Login is 403 | request `Origin` and `CORS_ORIGINS` | Use one exact scheme/host/port |
| Login loops in production | TLS and `COOKIE_SECURE` | Terminate HTTPS before the bound frontend |
| Jobs remain queued | worker logs, DB connectivity, lease age | Restore worker; expired leases are reclaimable |
| Ollama planning is unavailable | WSL keepalive, `systemctl status ollama`, installed model, worker `OLLAMA_BASE_URL` | Run `start-local-ollama.ps1`, then start a new audited run |
| Planning fails safely | run steps and validation codes | Correct input/provider issue and retry idempotently |
| PDF fails | Chromium availability, timeout, `/tmp`, size | Restore the release image/runtime limits |
| Hash conflict | reload plan and compare row/content versions | Do not overwrite; review the current immutable state |
| Demo reset refuses | APP_ENV, database name, confirmation | Use only the dedicated demo profile |
| Database pressure | SLO dashboard, pool timeout, slow endpoints | Reduce load and investigate before raising limits |

Safe failure codes and run traces expose purposes, input/output references,
validation, usage, retries, and timing—not hidden reasoning.

## Recovery

1. Stop writes if database integrity is uncertain.
2. Capture application/database logs and the failing request/run identifiers.
3. Keep the source database unchanged.
4. Restore the newest encrypted backup into a new `_restore_check` database.
5. Run `python -m app.cli.verify_restore`.
6. Compare the verified recovery point with the declared RPO.
7. Promote only after owner/operator approval and record the recovery evidence.

The complete drill, key separation, retention, and evidence record are in
[backup and restore](backup-restore.md).

## Security operations

- Never put secrets in Git, Compose files, fixture JSON, logs, screenshots, or
  audit payloads.
- Rotate database, session, provider, and backup secrets independently.
- Keep the frontend behind TLS in production.
- Restrict database and backup volumes to operators.
- Review dependency/security workflow results before merging.
- Treat report Markdown as untrusted plain text; rendering and filenames are
  sanitized.
- Do not add external integrations without scoped credentials, replay protection,
  approval previews, reconciliation, revocation, and an updated threat model.

## Release and incident handoff

Record the release commit, image IDs, Alembic revision, environment owner, health
results, backup manifest, restore result, GitHub run URLs, and known deviations.
Open incidents for failed Must/Should gates; do not waive them silently.
