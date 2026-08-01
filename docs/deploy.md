# Vendor-neutral deployment

Version: `0.13.0`
Scope: Phase 13 production and university-demo packaging

The release is a Docker Compose application with PostgreSQL, a FastAPI API, a
database-backed worker, and an Nginx-served React application. It requires no
vendor-specific runtime or external message broker.

## Prerequisites

- A current Linux host with Docker Engine 27+ and Docker Compose v2.30+.
- At least 4 CPU cores, 8 GiB RAM, and 15 GiB free space for the application,
  Chromium, database, images, and initial backup.
- A DNS name and a TLS-terminating reverse proxy or load balancer.
- A host-owned directory for checked-out source and a mode-`0600` environment file.
- An independently stored database backup passphrase.

The committed Python and npm lockfiles are authoritative. Do not regenerate
dependencies during deployment.

## Production configuration

1. Copy `.env.production.example` to a host-owned file outside the repository.
2. Generate independent, high-entropy values for `POSTGRES_PASSWORD`,
   `SESSION_HASH_SECRET`, and `BACKUP_PASSPHRASE`.
3. Make `DATABASE_URL` use the same URL-safe database password.
4. Set `PUBLIC_ORIGIN` and `CORS_ORIGINS` to the exact HTTPS origin.
5. Set `AI_PROVIDER`. Use `ollama` with a worker-reachable `OLLAMA_BASE_URL` and an
   installed `OLLAMA_MODEL`, or select another configured adapter explicitly.
6. Restrict the environment file to the deployment account.

The frontend binds to `127.0.0.1:8080` by default. Terminate TLS in the host
reverse proxy and forward to that address. The application intentionally requires
secure cookies in production; exposing the bound HTTP port directly is unsupported.

## First deployment

From a clean checkout at the release commit:

```sh
docker compose \
  --env-file /secure/path/ai-project-manager.env \
  -f compose.production.yaml \
  --profile production \
  config --quiet

docker compose \
  --env-file /secure/path/ai-project-manager.env \
  -f compose.production.yaml \
  --profile production \
  up -d --build

curl --fail https://project-manager.example.edu/healthz
curl --fail https://project-manager.example.edu/api/v1/health/ready
```

`migrate` is an ordered one-shot service. API and worker startup is blocked until
the database is healthy and Alembic reaches the repository head.

Inspect the exact state:

```sh
docker compose \
  --env-file /secure/path/ai-project-manager.env \
  -f compose.production.yaml \
  --profile production \
  ps

docker compose \
  --env-file /secure/path/ai-project-manager.env \
  -f compose.production.yaml \
  --profile production \
  logs --no-color --tail=200 api worker
```

Expected steady state: `db`, `api`, `worker`, and `frontend` are running; `migrate`
has exited with code zero.

## Upgrade

1. Take and verify a pre-upgrade encrypted backup.
2. Fetch the reviewed release commit.
3. Run `config --quiet`.
4. Build images before stopping the previous release.
5. Run `up -d`; the migration gate runs before the new API and worker.
6. Verify both health endpoints, authentication, project list, and one stored report.
7. Retain the previous application image and backup until the observation window ends.

Database migrations are forward-only unless a migration explicitly documents a
downgrade. Application rollback after a schema change therefore uses the verified
pre-upgrade backup, not an assumed automatic downgrade.

## Backup and restore

Create an encrypted backup in the managed `production_backups` volume:

```sh
docker compose \
  --env-file /secure/path/ai-project-manager.env \
  -f compose.production.yaml \
  --profile production \
  --profile operations \
  run --rm backup
```

Copy the encrypted dump and adjacent `.sha256` manifest to independent storage.
Restore is always rehearsed into a dedicated database ending in `_restore_check`.
Follow [backup and restore](operations/backup-restore.md) exactly.

Targets:

- RPO: 24 hours.
- RTO: 4 hours.
- Restore evidence: checksum, migration revision, relational invariants, immutable
  hashes, and completion timestamp.

## Clean university-demo deployment

The following command builds release images, migrates a dedicated demo database,
loads the eight synthetic fixtures, verifies the public API and both exports,
restarts services, and proves persistence:

```sh
sh infra/release/verify-demo.sh
```

The reset command is deliberately destructive only inside a database whose name
contains `demo`, only in `development`, `demo`, or `test`, and only with the exact
confirmation `RESET-DEMO-DATA`. It refuses production and staging.

## Shutdown and data ownership

Stopping containers preserves named volumes:

```sh
docker compose -f compose.production.yaml --profile production down
```

Do not add `--volumes` during an ordinary stop. Volume removal destroys the
database and backups and is outside the documented production workflow.

## Release acceptance

A deployment is accepted only when:

- Compose configuration resolves without placeholders or warnings.
- Migration exits zero and every long-running service is healthy.
- The TLS origin can authenticate with secure cookies.
- A stored project, plan hash, task history, recommendation evidence, and report
  survive service restart.
- The seeded release exposes eight active plans and eight retained drafts with
  valid independent hashes; its scenario and regeneration proposal remain bound
  to their original active and draft baselines.
- Encrypted backup and isolated restore verification meet the RPO/RTO procedure.
- Both continuous-verification and university-release GitHub workflows pass on the
  exact release commit.
