# MVP Observability and SLOs

Every HTTP response carries `X-Request-ID`. Audit events, task events, workflow runs/steps,
provider usage, and product metrics preserve the related request/run identifiers. Never put
passwords, cookies, CSRF values, authorization headers, provider payloads, project prose, or
database URLs into telemetry.

## Service-level objectives

| Signal | Target | Alert |
|---|---|---|
| Non-AI read latency | p95 < 300 ms at 50 concurrent | `API_P95_HIGH` |
| Non-AI write latency | p95 < 600 ms at 50 concurrent | `API_P95_HIGH` |
| Oldest queued job | below configured threshold | `QUEUE_AGE_HIGH` |
| Provider failure ratio | below configured ratio | `PROVIDER_FAILURE_RATE_HIGH` |
| Daily estimated model cost | below configured warning fraction and hard budget | `DAILY_COST_BUDGET_HIGH` |
| Duplicate job claims | zero | `DUPLICATE_JOB_CLAIM` |
| Scheduled backup | successful and fresh | `BACKUP_FAILED` |

`app.observability.slo.evaluate_slos` owns alert thresholds and deterministic actions.
Controlled unit tests exercise every alert and the healthy state. Owner daily run/token
quota is available at `GET /api/v1/usage/quota`; rejected starts return a safe 429 and do not
consume or mutate a run.

## Deployment

`infra/observability/otel-collector.yaml` accepts OTLP HTTP/gRPC, batches telemetry, exports
Prometheus-compatible metrics on port 8889, and emits redacted debug telemetry for a local
reference deployment. Replace the debug exporter with the deployment's authenticated trace
backend. The included Grafana dashboard is a portable starting point; adapt metric names to
the selected OpenTelemetry SDK/exporter without changing the SLO thresholds.

## Triage

1. Use the request ID from the user-safe error to locate the route, audit, run, and step.
2. Check database health, queue age, lease heartbeats, and duplicate-claim count.
3. For provider incidents, group only by typed outcome/model/prompt version; do not inspect
   or export raw project content.
4. For cost alerts, stop nonessential AI starts, inspect usage by owner/run, and keep
   deterministic execution/report facts available.
5. For backup alerts, rerun the backup and perform a restore verification before release.
