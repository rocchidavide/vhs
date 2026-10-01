#!/usr/bin/env bash
# Restore a VHS backup (scripts/backup.sh) into a NEW Docker installation.
#
# Usage: scripts/restore.sh <backup-folder>
#
# Refuses unless the library folder (VHS_HOST_LIBRARY) is empty and the database has no
# tables: it never overwrites an installation in use. The worker stays stopped until the
# outcome is recorded, so queued jobs in the dump cannot change anything before the check.
# Extra Compose files are taken from COMPOSE_FILE, like any docker compose command.
#
# Exit codes:
#   0  restore succeeded: the verification found no problem
#   3  data restored, with problems already present in the backup (and only those)
#   1  restore failed (new problems, incomplete verification) or refused
# See docs/installation.md, "Backup and restore".

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT=$(pwd -P)

die() { echo "ERROR: $*" >&2; exit 1; }
say() { echo "==> $*"; }

[ $# -eq 1 ] || die "usage: scripts/restore.sh <backup-folder>"
command -v rsync >/dev/null || die "rsync is not installed."
[ -d "$1" ] || die "the backup folder $1 does not exist."
BACKUP=$(cd "$1" && pwd -P)

case "$(basename "$BACKUP")" in
  *.partial) die "$BACKUP is an unfinished backup: it cannot be restored." ;;
esac
for item in manifest.txt database.dump verify-at-backup.json library; do
  [ -e "$BACKUP/$item" ] || die "$BACKUP is not a complete backup: $item is missing."
done

library_path() {
  docker compose config 2>/dev/null | awk '
    $1 == "source:" { source = substr($0, index($0, $2)) }
    $1 == "target:" && $2 == "/srv/video-library" { gsub(/^"|"$/, "", source); print source; exit }'
}
# Compose progress messages go to a log, shown only if the command fails.
COMPOSE_LOG=$(mktemp)
trap 'rm -f "$COMPOSE_LOG"' EXIT
quiet() { "$@" 2>"$COMPOSE_LOG" || { cat "$COMPOSE_LOG" >&2; return 1; }; }
oneshot() { quiet docker compose run --rm --no-deps -T "$@"; }

LIBRARY=$(library_path)
[ -n "$LIBRARY" ] || die "cannot read VHS_HOST_LIBRARY from the Compose configuration."
[ -d "$LIBRARY" ] || die "the library folder $LIBRARY does not exist: create it empty (docs/installation.md)."
[ -z "$(ls -A "$LIBRARY")" ] || die "the library folder $LIBRARY is not empty: \
restore into a new installation."

for service in backend worker migrate nginx; do
  if docker compose ps --services --status running | grep -qx "$service"; then
    die "the $service service is running: stop VHS (./vhs stop) and try again."
  fi
done

say "Starting the database only"
quiet docker compose up -d --wait db

# shellcheck disable=SC2016  # expanded inside the db container
TABLES=$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "select count(*) from information_schema.tables where table_schema = current_schema()"')
[ "$TABLES" = "0" ] || die "the database already has $TABLES tables: \
restore into an empty database (new volume)."

cat "$BACKUP/manifest.txt"
echo

say "Restoring the database"
# shellcheck disable=SC2016
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' \
  <"$BACKUP/database.dump"

say "Restoring the library into $LIBRARY"
rsync -a "$BACKUP/library/" "$LIBRARY/"

# Not the migrate service: it also runs reconcile_downloads, which changes the database and
# the work dirs. Nothing but the migrations and the read-only verification runs before the
# outcome is known.
say "Applying migrations"
oneshot backend python manage.py migrate --noinput >/dev/null

say "Verifying with checksums (reads the whole library)"
STAMP=$(date +%Y%m%d-%H%M%S)
REPORTS="$PROJECT/restore-reports"
mkdir -p "$REPORTS"
AFTER="$REPORTS/restore-$STAMP.json"
set +e
oneshot backend python manage.py verify_library --checksums --json >"$AFTER" 2>/dev/null
set -e

set +e
OUTCOME=$(oneshot \
  -v "$BACKUP/verify-at-backup.json:/check/baseline.json:ro" \
  -v "$AFTER:/check/restored.json:ro" \
  -v "$PROJECT/scripts/compare_reports.py:/check/compare_reports.py:ro" \
  backend python /check/compare_reports.py /check/baseline.json /check/restored.json)
CODE=$?
set -e

{
  echo "VHS restore of $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "Backup:   $BACKUP"
  echo "Library:  $LIBRARY"
  echo
  echo "$OUTCOME"
} >"$REPORTS/restore-$STAMP.txt"

echo
echo "$OUTCOME"
echo
echo "Outcome recorded in $REPORTS/restore-$STAMP.txt"

case "$CODE" in
  0 | 3)
    say "Starting the stack"
    quiet docker compose up -d
    echo "Stack started. The worker resumes the jobs that were queued in the backup."
    exit "$CODE"
    ;;
  *)
    echo "The stack was NOT started (only the database is running)."
    echo "Check the problems listed above. To start it anyway: ./vhs start"
    exit 1
    ;;
esac
