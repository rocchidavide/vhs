#!/usr/bin/env bash
# Backup of a Docker installation of VHS: database and video library, together and consistent.
#
# Usage: scripts/backup.sh <destination-folder>
#
# Run on the host, from anywhere; it works on the Compose project of this repository. Extra
# Compose files (e.g. docker-compose.prod.yml) are taken from COMPOSE_FILE, in the environment
# or in .env, like any docker compose command.
#
# Creates <destination>/vhs-backup-YYYYMMDD-HHMMSS/ with database.dump, library/,
# verify-at-backup.json and manifest.txt. It is written as a hidden ".partial" folder and
# renamed only when every step succeeded. The worker (the only service that writes library
# files) is stopped during the backup and started again only if it was running before.
# See docs/installation.md, "Backup and restore".

set -euo pipefail

cd "$(dirname "$0")/.."

die() { echo "ERROR: $*" >&2; exit 1; }
say() { echo "==> $*"; }

[ $# -eq 1 ] || die "usage: scripts/backup.sh <destination-folder>"
command -v rsync >/dev/null || die "rsync is not installed."
[ -d "$1" ] || die "the destination folder $1 does not exist."
DEST=$(cd "$1" && pwd -P)

# Host folder bound to /srv/video-library, as resolved by Compose.
library_path() {
  docker compose config 2>/dev/null | awk '
    $1 == "source:" { source = substr($0, index($0, $2)) }
    $1 == "target:" && $2 == "/srv/video-library" { gsub(/^"|"$/, "", source); print source; exit }'
}

manage() { docker compose exec -T backend python manage.py "$@"; }

# Problems in a verify_library JSON report read from stdin: "count" or "list".
PROBLEMS_PY=$(cat <<'PY'
import json, sys
problems = json.load(sys.stdin)["problems"]
if sys.argv[1] == "count":
    print(len(problems))
else:
    for p in problems:
        detail = f"  ({p['detail']})" if p["detail"] else ""
        print(f"  - [{p['kind']}] {p['path']}{detail}")
PY
)
problems() { docker compose exec -T backend python -c "$PROBLEMS_PY" "$1"; }

running_jobs() {
  manage shell -v 0 -c "
from core.models import Download, PlaybackPreparation
print(Download.objects.filter(status__in=['downloading', 'processing']).count()
      + PlaybackPreparation.objects.filter(status='running').count())" | tail -n 1
}

LIBRARY=$(library_path)
[ -n "$LIBRARY" ] || die "cannot read VHS_HOST_LIBRARY from the Compose configuration."
[ -d "$LIBRARY" ] || die "the library folder $LIBRARY does not exist."
LIBRARY=$(cd "$LIBRARY" && pwd -P)
case "$DEST/" in
  "$LIBRARY/"*) die "the destination $DEST is inside the library: the backup would copy itself." ;;
esac

docker compose ps --services --status running | grep -qx backend \
  || die "the backend is not running: start VHS (./vhs start) and try again."

say "Checking the library"
set +e
manage verify_library --json >/dev/null 2>&1
status=$?
set -e
[ "$status" -ne 2 ] || die "incomplete library check (library not available?). \
Run 'docker compose exec backend python manage.py verify_library' for details."

[ "$(running_jobs)" = "0" ] \
  || die "downloads or conversions are running: try again when they have finished."

WORKER_WAS_RUNNING=0
WORKER_ID=$(docker compose ps -q --status running worker)
if [ -n "$WORKER_ID" ]; then
  WORKER_WAS_RUNNING=1
fi
NAME="vhs-backup-$(date +%Y%m%d-%H%M%S)"
PARTIAL="$DEST/.$NAME.partial"
FINAL="$DEST/$NAME"
DONE=0

finish() {
  if [ "$WORKER_WAS_RUNNING" = 1 ]; then
    say "Restarting the worker"
    # The container itself: "docker compose start" would also rerun the migrate service
    # it depends on, and with it a reconciliation.
    docker start "$WORKER_ID" >/dev/null
  fi
  if [ "$DONE" != 1 ] && [ -e "$PARTIAL" ]; then
    echo "BACKUP NOT COMPLETED: the partial folder $PARTIAL is not a usable backup." >&2
  fi
}
trap finish EXIT

if [ "$WORKER_WAS_RUNNING" = 1 ]; then
  say "Stopping the worker"
  docker compose stop worker >/dev/null 2>&1
fi
# A job may have started between the check and the stop: the stop interrupted it.
[ "$(running_jobs)" = "0" ] || die "a job started while the worker was stopping: \
no backup created. The worker resumes and handles it; try again later."

mkdir "$PARTIAL"

say "Verifying with checksums (reads the whole library)"
set +e
manage verify_library --checksums --json >"$PARTIAL/verify-at-backup.json" 2>/dev/null
status=$?
set -e
[ "$status" -ne 2 ] || die "the checksum verification is incomplete: no backup created."
PROBLEMS=$(problems count <"$PARTIAL/verify-at-backup.json")

# Database first, then files: a file added after the dump can only be unreferenced, never
# missing. The worker is stopped, so nothing writes to the library meanwhile anyway.
say "Dumping the database"
# shellcheck disable=SC2016  # expanded inside the db container
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  >"$PARTIAL/database.dump"

say "Copying the library from $LIBRARY"
rsync -a --exclude=/.incomplete/ "$LIBRARY/" "$PARTIAL/library/"

say "Writing the manifest"
{
  echo "VHS backup"
  echo "Date:               $(date '+%Y-%m-%d %H:%M:%S %z')"
  manage shell -v 0 -c "
from django.db.migrations.recorder import MigrationRecorder
from core.models import LocalStatus, Video
from services.system_service import vhs_version
print('VHS version:       ', vhs_version() or 'unknown')
last = MigrationRecorder.Migration.objects.filter(app='core').order_by('-id').first()
print('Last migration:    ', last.name if last else '-')
print('Archived videos:   ', Video.objects.filter(local_status=LocalStatus.AVAILABLE).count())"
  echo "Files copied:       $(find "$PARTIAL/library" -type f | wc -l | tr -d ' ')"
  echo "Existing problems:  $PROBLEMS (verify-at-backup.json)"
  echo "Library:            $LIBRARY"
} >"$PARTIAL/manifest.txt"

mv "$PARTIAL" "$FINAL"
DONE=1

echo
cat "$FINAL/manifest.txt"
echo
if [ "$PROBLEMS" = "0" ]; then
  echo "BACKUP COMPLETED: $FINAL"
else
  echo "BACKUP COMPLETED: $FINAL"
  echo "The library already had problems ($PROBLEMS), recorded in the backup (verify-at-backup.json):"
  problems list <"$FINAL/verify-at-backup.json"
fi
echo "Also keep a separate copy of the .env file (secrets and passwords): the backup does not include it."
