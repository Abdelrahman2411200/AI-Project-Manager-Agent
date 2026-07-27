# MVP Operator Runbook

## Start and health

Copy `.env.example` to `.env`, set production secrets, then run `docker compose up -d
--build`. Apply migrations before exposing traffic. `/api/v1/health/live` proves the process
is alive; `/api/v1/health/ready` proves startup and database connectivity. Run one API and at
least one worker. Scale API processes freely; keep SQLite to one worker only.

## Incident actions

| Symptom | Immediate action | Recovery proof |
|---|---|---|
| API latency alert | Check saturation and slow database spans; reduce traffic | p95 back below 300/600 ms |
| Queue age alert | Check worker health, lease expiry, database locks, provider availability | Oldest job decreases; no duplicate claim |
| Provider outage | Preserve checkpoints, allow bounded retry, keep deterministic features available | Resumed run completes from checkpoint |
| Cost/quota alert | Pause nonessential AI starts; inspect typed usage by run/owner | Start returns safe 429 or usage falls below threshold |
| Database unavailable | Remove API from readiness, restore service or fail over | Readiness 200 and migration head matches |
| Backup failure | Rerun encrypted backup and isolated restore verification | Verifier JSON is `ok: true` |
| Suspected credential leak | Revoke/rotate immediately; invalidate sessions if relevant | Secret scan clean and credential replaced |

Do not manually mark failed runs complete, modify immutable plan/report history, or bypass
owner authorization. Correct the cause and resume through the supported job/run controls.

## Safe rollback

Application rollback is allowed only when the existing schema remains compatible. Never
downgrade a destructive migration without a verified backup and migration-specific plan.
Deploy the previous image, verify readiness, worker leasing, login, active-plan reads, and
report download. Forward-fix data integrity defects.

## Release and recovery

Use `docs/release/mvp-checklist.md` as the authoritative gate. Run the encrypted backup and
isolated restore procedure in `docs/operations/backup-restore.md`. Treat Critical/High
security findings, failed owner isolation, failed PostgreSQL integration, and failed restore
verification as unconditional blockers.
