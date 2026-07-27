#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"

backup_dir="${BACKUP_DIR:-./backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
encrypted="$backup_dir/project-manager-$timestamp.dump.enc"
manifest="$encrypted.sha256"
native_database_url="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"

pg_dump --format=custom --no-owner --no-acl "$native_database_url" |
  openssl enc -aes-256-cbc -salt -pbkdf2 -pass env:BACKUP_PASSPHRASE -out "$encrypted"
sha256sum "$encrypted" > "$manifest"
printf '%s\n' "$encrypted"
