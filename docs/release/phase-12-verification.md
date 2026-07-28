# Phase 12 Full-Version Experience Verification

Version: `0.12.0`

Scope: Implementation Plan Phase 12

Exit statement: advanced results are understandable without color or drag, and
PDF exports match immutable stored report facts.

## Deliverable matrix

| Backlog item | Implementation evidence | Verification evidence | Status |
|---|---|---|---|
| ARCH-005 visualization/PDF architecture | `docs/architecture-ui.md`; React Flow choice, table fallbacks, lazy loading, Chromium isolation, alternatives and cost | architecture review; dependency lock; Compose build | Complete |
| BE-012 risk, evaluation and PDF APIs | full draft risk CRUD in `advanced.py`; verified evaluation baseline; hash-bound `ReportService.export_pdf`; isolated Playwright worker | API ownership/concurrency tests; baseline parity; real Chromium smoke; hash, timeout, filename and fallback tests | Complete |
| FE-010 full-version visual experience | Intelligence route; dependency graph/table; timeline/Gantt/table; risk register; scenario comparison; evaluation dashboard; report PDF action | component, keyboard, axe, snapshot, responsive desktop/360 px and download E2E | Complete |
| TEST-008 full-version verification | advanced component/API/PDF tests, large-graph layout test, Playwright journey and reviewed snapshot | commands below and ordered CI | Complete |

## Requirement coverage

| Requirement | Evidence |
|---|---|
| FR-021 risk management | list/single/create/update/delete endpoints, deterministic severity, version-local relations, draft-only mutations and risk-register UI |
| FR-022 what-if | immutable scenario result, explicit baseline labels, metric bars plus exact table, active-plan isolation tests |
| FR-024 PDF export | same immutable `Report` representation, canonical hash recheck, authenticated download, safe filename and Markdown fallback |
| NFR-002 security | owner-safe 404, CSRF on writes, no request-controlled renderer paths, escaped content, no JS/network/downloads, sanitized child environment, bounded output |
| NFR-006 accessibility | no serious automated axe violations; keyboard links/forms; graph, Gantt and chart table parity; text severity/direction labels |
| NFR-007 API performance | isolated CI job with fresh PostgreSQL plus a single-worker reference Uvicorn container topology in a separate process; three 50-concurrency rounds calculate p95 over 150 authenticated reads and 150 writes; shell `pipefail` preserves a failed benchmark exit |
| NFR-008 calculation performance | existing 1,000-task/approximately 3,000-edge backend gate under two seconds plus 1,000-node/2,994-edge frontend layout gate |
| NFR-015 reliability/idempotency | risk optimistic concurrency; report immutability; PDF failure does not alter the report or Markdown |
| NFR-017 responsive UI | desktop and 360 px Playwright journeys assert no page-level horizontal overflow |

## PDF security and factuality assertions

- The owner is resolved before a report row or renderer is accessed.
- The stored `data_json`, `narrative_json`, and Markdown are rehashed and must
  equal `Report.content_hash`.
- Stored Markdown is not interpreted as HTML. The print document is constructed
  from escaped validated fields.
- Chromium runs in a child process with JavaScript and downloads disabled,
  service workers blocked, all external schemes aborted, and no database,
  session, or OpenAI environment secrets.
- Concurrency, 60-second renderer timeout plus bounded HTTP response grace,
  maximum bytes, `%PDF-` signature, safe filename, source hash and PDF SHA-256
  are enforced.
- Success and failure produce safe audit/telemetry events. Failure returns a
  retryable response and Markdown remains available.

## Accessibility and visual assertions

- The dependency visualization has no graph-only command and every persisted
  edge appears in a captioned table.
- Plans above 200 nodes use responsive table mode rather than forcing the
  interactive canvas.
- Gantt position and color are supplementary; dates, duration, milestone,
  effort and status appear in a captioned table.
- Risk severity includes numeric and textual labels. Active/reviewed versions
  expose read-only controls.
- Scenario bars repeat exact values and “increased/decreased/unchanged” text.
- Evaluation results include per-fixture values, thresholds and provenance.
- Reduced motion is honored and visualization/table overflow stays inside its
  own scroll region.

## Local verification commands

Backend:

```powershell
Set-Location backend
uv sync --locked --group dev
uv run playwright install chromium
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest --cov=app --cov-branch --cov-fail-under=85
uvx --python 3.12 bandit -r app -ll
```

Frontend:

```powershell
Set-Location frontend
npm ci
npm run audit:ci
npm run lint
npm run typecheck
npm run test:run -- --coverage.enabled=false
npm run build
npm run test:e2e
```

Packaging:

```powershell
docker compose config --quiet
docker build --target development --tag aipm-phase12-backend ./backend
```

## Exit checklist

- [x] Every Phase 12 visual has a keyboard/table alternative.
- [x] No interaction depends only on color or drag.
- [x] Risk CRUD is owner-scoped, draft-only and concurrency protected.
- [x] All eight evaluation fixtures and thresholds are visible to an
      authenticated user.
- [x] Evaluation permissions fail closed.
- [x] PDF output is authenticated, hash-bound, network isolated, timeout
      bounded and factually sourced.
- [x] Markdown remains available after a PDF failure.
- [x] The live 50-concurrency API gate truthfully enforces read p95 below
      300 ms and write p95 below 600 ms over sustained samples.
- [x] Large-graph and deterministic calculation performance gates pass.
- [x] Desktop and 360 px browser flows, visual snapshot and PDF download pass.
- [x] Full ordered CI is green on the Phase 12 commit and merged `main`.

The last item is confirmed from the authoritative GitHub Actions runs at merge
time.
