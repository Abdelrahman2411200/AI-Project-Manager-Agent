# MVP Release Checklist

Release candidate: 0.10.0. All boxes must be supported by CI or attached operator evidence.

## Mandatory gates

- [ ] Locked dependencies install from `uv.lock` and `package-lock.json`.
- [ ] Ruff format/lint, strict mypy, ESLint, TypeScript, backend tests with PostgreSQL,
      frontend tests, Playwright, and production builds pass.
- [ ] Deterministic domain branch coverage is at least 90%; full backend coverage does not
      regress below the repository threshold.
- [ ] 1,000-task/approximately 3,000-edge calculation fixture completes under two seconds.
- [ ] 50-concurrent reference read/write p95 is under 300/600 ms.
- [ ] Eight evaluation scenarios run; the five `mvp_release` fixtures all meet their hard
      thresholds.
- [ ] Required-node failure, provider failure, retry, checkpoint resume, duplicate claim,
      idempotency, and budget exhaustion tests pass.
- [ ] CSP, request/body/time/rate limits, owner isolation, CSRF, sanitized Markdown, safe
      errors, secret scan, SAST, and dependency scans pass with no Critical/High finding.
- [ ] Encrypted PostgreSQL backup and isolated restore verifier pass; elapsed restore is below
      four hours and the last scheduled backup is less than 24 hours old.
- [ ] Keyboard, automated accessibility, and 360 px primary-flow gates pass.
- [ ] Clean Compose configuration, migration-to-head, liveness/readiness, worker, and
      create-to-report lifecycle pass.
- [ ] Architecture and threat reviews have no unresolved Must issue.

## Requirement-to-evidence matrix

| Requirement | Release evidence |
|---|---|
| FR-001–004 | Project/intake API tests, planning schema/clarification workflow, create-to-approval E2E |
| FR-005–008 | Plan contract/database/version-isolation tests, DAG/cycle tests, review E2E |
| FR-009–010 | Priority/scheduler unit tests, calendar/deadline fixtures, calculation benchmark |
| FR-011–013 | Draft edit/lock/concurrency/lifecycle/approval tests, owner-isolation tests |
| FR-014 | Full-version deferred; no MVP route mutates active plan through regeneration |
| FR-015–018 | Status/event/readiness/progress/monitoring/health tests, execution E2E |
| FR-019–020 | Evidence validator, deduplication, recommendation-decision API/E2E |
| FR-021–022 | Full-version deferred; MVP API exposes no active mutation path |
| FR-023–026 | Report factuality/sanitization/export, trace, provider usage, audit tests and report E2E |
| FR-027 | Full-version deferred; immutable version snapshots retained |
| FR-028 | Dashboard/overview component, empty/error/permission and responsive tests |
| NFR-001–002 | Threat model, auth/CSRF/owner tests, security scans, provider payload/store/redaction tests |
| NFR-003–005 | Workflow failure/resume, DB constraints, priority/health/evidence snapshots |
| NFR-006 | axe, semantic/keyboard component and Playwright tests |
| NFR-007 | 50-concurrent ASGI latency gate |
| NFR-008 | 1,000-task/3,000-edge domain benchmark |
| NFR-009 | Run-start/progress polling tests and evaluation timing evidence |
| NFR-010 | Stateless API review plus PostgreSQL atomic job-claim tests |
| NFR-011 | Strict typing, domain docs, deterministic branch coverage gate |
| NFR-012 | Request/run/node/provider correlation tests and SLO dashboard/alert tests |
| NFR-013 | Per-run and daily owner run/token budget tests and quota endpoint |
| NFR-014 | Provider interface, fake-provider parity, offline workflow tests |
| NFR-015 | Start/mutation idempotency and payload-conflict tests |
| NFR-016 | Encrypted PostgreSQL backup and isolated restore drill |
| NFR-017 | 360 px Playwright and responsive component tests |
| NFR-018 | Calendar, DST, nonworking-day, UTC event fixtures |
| NFR-019 | Problem Details, correlation ID, timeout/body/rate and redaction tests |
| NFR-020 | OpenAPI `/api/v1` compatibility test and migration review |

## Sign-off

Record commit SHA, CI run URL, scan summaries, backup checksum, restore verifier JSON and
elapsed time. The release owner signs only after every mandatory box is satisfied.
