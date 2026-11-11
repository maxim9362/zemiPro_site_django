#!/bin/sh
# Back up ONLY the dedicated, isolated ZemiPro staging PostgreSQL service.
set -eu
umask 077

if [ "${PGHOST:-}" != "db" ] ||
   [ "${PGDATABASE:-}" != "zemipro_staging" ] ||
   [ "${PGUSER:-}" != "zemipro_staging" ] ||
   [ -z "${PGPASSWORD:-}" ]; then
    echo "SAFE_ABORT: isolated staging PostgreSQL settings required" >&2
    exit 2
fi

if [ ! -d /backups ]; then
    echo "SAFE_ABORT: staging backup volume unavailable" >&2
    exit 2
fi

# The private .partial file is created exclusively inside the staging volume.
# No password, SQL text or customer data is printed to stdout.
temporary=$(mktemp /backups/.zemipro-pending-XXXXXXXX)
trap 'rm -f "$temporary"' EXIT HUP INT TERM

pg_dump --no-password --format=custom --no-owner --no-acl --file="$temporary"
test -s "$temporary"
pg_restore --list "$temporary" >/dev/null

archive="/backups/zemipro-staging-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
if [ -e "$archive" ]; then
    echo "SAFE_ABORT: backup archive already exists" >&2
    exit 2
fi
mv "$temporary" "$archive"
sha256sum "$archive" > "${archive}.sha256"
trap - EXIT HUP INT TERM

echo "staging_backup=PASS"
