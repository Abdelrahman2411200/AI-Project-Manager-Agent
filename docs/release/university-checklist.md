# University release checklist

Release: `0.13.0`

## Source and scope

- [ ] Release commit recorded.
- [ ] `IMPLEMENTATION%20PLAN.MD` SHA-256 is
  `03e80036926b25cc16d6b7b5891a859047ad493cc4b983455142033682166e27`.
- [ ] Final architecture review reports no unresolved Must/Should inconsistency.
- [ ] Exactly 72 backlog identifiers are accounted for.
- [ ] Version is `0.13.0` in backend, frontend, settings, and release examples.

## Verification

- [ ] Backend format, lint, mypy, ≥85% branch coverage, and PostgreSQL tests pass.
- [ ] Reference API load gate passes at 50-way concurrency.
- [ ] Frontend lint, type, unit, build, accessibility, and browser acceptance pass.
- [ ] Dependency, source, history-secret, and request-hardening scans pass.
- [ ] All eight university fixture assertions pass with zero provider calls.
- [ ] Every fixture retains one generated draft based on one active version; all
  sixteen plan content hashes verify.
- [ ] The representative scenario is immutable and the selective-regeneration
  proposal is pending on a draft without changing the active hash or TASK-003.
- [ ] Clean Compose demo build/migration/seed/API/PDF rehearsal passes.
- [ ] Browser/service restart preserves plan hash, events, recommendation decision,
  report, and exports.
- [ ] Encrypted backup and isolated restore meet RPO 24h/RTO 4h procedure.
- [ ] Production Compose configuration resolves from the documented environment.

## Demo and documentation

- [ ] A new engineer follows the operator/developer guide without undocumented steps.
- [ ] The exact 23 presentation steps are rehearsed.
- [ ] Expected records and evidence checklist match stored fixture output.
- [ ] The impossible deadline remains infeasible; no estimate compression occurs.
- [ ] TASK-003 remains user-sourced, locked, and protected.
- [ ] Active/draft version isolation survives API reload and service restart.
- [ ] Every recommendation claim has stored evidence.
- [ ] Every report fact derives from persisted state/events.
- [ ] Markdown/PDF exports and reload persistence are demonstrated.

## GitHub evidence

- [ ] Phase 13 pull request URL:
- [ ] Pull-request `continuous-verification` run:
- [ ] Pull-request `university-release` run:
- [ ] Merge commit:
- [ ] Post-merge `continuous-verification` run:
- [ ] Post-merge `university-release` run:

## Approval

- [ ] No failing, skipped-required, or pending gate.
- [ ] No uncommitted release change.
- [ ] Branch merged to `origin/main`.
- [ ] Post-merge runs pass on the exact main commit.
