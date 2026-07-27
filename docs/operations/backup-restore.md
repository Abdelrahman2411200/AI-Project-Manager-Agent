# Backup and Restore Procedure

Reference objectives are RPO 24 hours and RTO 4 hours. Run an encrypted PostgreSQL backup
nightly, retain it according to deployment policy, and complete a restore drill quarterly and
before an MVP release.

## Backup

The operator needs PostgreSQL client tools, OpenSSL, `DATABASE_URL`, and a passphrase from a
secret manager. The passphrase must not be stored beside the backup.

```sh
BACKUP_DIR=/secure/backups \
BACKUP_PASSPHRASE='from-secret-manager' \
DATABASE_URL='postgresql://…' \
./infra/backup/backup.sh
```

The script creates an encrypted `.dump.enc` and a SHA-256 manifest. Copy both to restricted,
versioned storage. Record completion time and artifact identifier, never the passphrase.

## Isolated restore verification

Create a disposable empty database whose name ends in `_restore_check`; the guard prevents
accidental restore into a normal database.

```sh
RESTORE_DATABASE_URL='postgresql+psycopg://…/project_manager_restore_check' \
BACKUP_FILE='/secure/backups/project_manager-….dump.enc' \
BACKUP_PASSPHRASE='from-secret-manager' \
./infra/backup/restore-verify.sh
```

For the complete repeatable drill, supply an administrative maintenance URL and let the
orchestrator create and remove the validated disposable database:

```sh
ADMIN_DATABASE_URL='postgresql+psycopg://…/postgres' \
DATABASE_URL='postgresql+psycopg://…/project_manager' \
RESTORE_DATABASE_URL='postgresql+psycopg://…/project_manager_restore_check' \
BACKUP_PASSPHRASE='from-secret-manager' \
./infra/backup/drill.sh
```

The reference release builds `infra/backup/Dockerfile` and runs the resulting recovery image.
It pins PostgreSQL 18 client tools to the reference PostgreSQL 18 server and bundles the
Python invariant verifier, avoiding unsafe host-client version drift.

The procedure verifies the manifest, decrypts to a temporary file, restores with
`pg_restore`, then checks required tables, row counts, one-active-plan invariants, and recent
report content hashes. The temporary plaintext dump is removed on exit.

## Evidence and failure handling

Retain the timestamp, source database identifier, encrypted artifact checksum, verifier JSON,
elapsed time, and operator identity. Delete the disposable database after capturing evidence.
Any checksum, decrypt, restore, schema, invariant, or report-hash failure is a release blocker.
If RTO exceeds four hours, open an incident and rehearse the slow step before release.
