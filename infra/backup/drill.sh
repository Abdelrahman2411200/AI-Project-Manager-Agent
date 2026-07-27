#!/usr/bin/env sh
set -eu

: "${ADMIN_DATABASE_URL:?ADMIN_DATABASE_URL is required}"
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"

case "$RESTORE_DATABASE_URL" in
  *"_restore_check"*) ;;
  *) echo "RESTORE_DATABASE_URL must target a dedicated *_restore_check database" >&2; exit 2 ;;
esac

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
native_admin_url="$(printf '%s' "$ADMIN_DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
restore_database_name="$(
  printf '%s' "$RESTORE_DATABASE_URL" |
    sed 's#[?].*$##; s#/$##; s#.*/##'
)"

case "$restore_database_name" in
  "" | *[!A-Za-z0-9_]*) echo "Unsafe restore database name: $restore_database_name" >&2; exit 2 ;;
  *"_restore_check") ;;
  *) echo "Restore database name must end in _restore_check" >&2; exit 2 ;;
esac

drill_dir="$(mktemp -d)"
cleanup() {
  dropdb --if-exists --force --maintenance-db="$native_admin_url" "$restore_database_name"
  rm -rf "$drill_dir"
}
trap cleanup EXIT

createdb --maintenance-db="$native_admin_url" "$restore_database_name"
backup_file="$(
  BACKUP_DIR="$drill_dir" sh "$script_dir/backup.sh" |
    tail -n 1
)"
BACKUP_FILE="$backup_file" sh "$script_dir/restore-verify.sh"
