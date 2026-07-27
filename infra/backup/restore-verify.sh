#!/usr/bin/env sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repository_root="$(CDPATH= cd -- "$script_dir/../.." && pwd)"

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"

case "$RESTORE_DATABASE_URL" in
  *"_restore_check"*) ;;
  *) echo "RESTORE_DATABASE_URL must target a dedicated *_restore_check database" >&2; exit 2 ;;
esac

temporary_dump="$(mktemp)"
trap 'rm -f "$temporary_dump"' EXIT
native_restore_url="$(printf '%s' "$RESTORE_DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
sha256sum -c "$BACKUP_FILE.sha256"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE \
  -in "$BACKUP_FILE" -out "$temporary_dump"
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname "$native_restore_url" "$temporary_dump"
(
  cd "$repository_root/backend"
  DATABASE_URL="$RESTORE_DATABASE_URL" uv run --no-dev python -m app.cli.verify_restore
)
