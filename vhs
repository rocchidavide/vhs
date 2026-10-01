#!/usr/bin/env bash
# Commands for a VHS installation (docs/installation.md). Each command prints what it
# runs, so it can always be used without this script. Development has its own script,
# ./dev. Nothing here deletes data: no "down -v", no database reset.

set -euo pipefail

cd "$(dirname "$0")"

die() { echo "vhs: $*" >&2; exit 1; }

# Only an installation: its .env is based on .env.example, never on the development one.
[ -f .env ] || die "no .env file. Create it first: cp .env.example .env (see docs/installation.md, step 3)."
if grep -Eq '^COMPOSE_FILE=.*docker-compose\.dev\.yml' .env; then
  die ".env is the development one (COMPOSE_FILE loads docker-compose.dev.yml). Use ./dev in development; an installation starts from .env.example."
fi

run() {
  echo "+ $*" >&2
  "$@"
}

manage() {
  run docker compose exec backend python manage.py "$@"
}

usage() {
  cat <<'EOF'
Usage: ./vhs <command> [arguments]

  start                 start VHS
  stop                  stop VHS (videos and database are kept)
  status                show the services
  logs [service]        follow the logs (all services or one)
  create-user           create a user to sign in with
  storage-status        show the state of the video library
  verify [--checksums]  compare the database with the video library (read-only)
  init-library          mark an existing VHS library folder (checks its videos first)
  backup <folder>       back up database and videos into <folder>
  restore <backup>      restore a backup into a new, never-started installation
  update [--yes]        update VHS (git pull and rebuild); make a backup first
  manage <command>      any Django command (manage.py)
  help                  this list

On Linux run backup and restore with sudo, so that file owners are preserved.
EOF
}

command=${1:-help}
[ $# -gt 0 ] && shift

case "$command" in
  start)
    run docker compose up -d
    ;;

  stop)
    run docker compose stop
    ;;

  status)
    run docker compose ps
    ;;

  logs)
    run docker compose logs -f "$@"
    ;;

  create-user)
    manage createsuperuser "$@"
    ;;

  storage-status)
    manage storage_status
    ;;

  verify)
    manage verify_library "$@"
    ;;

  init-library)
    manage init_library "$@"
    ;;

  backup)
    [ $# -eq 1 ] || die "usage: ./vhs backup <folder>"
    run scripts/backup.sh "$1"
    ;;

  restore)
    [ $# -eq 1 ] || die "usage: ./vhs restore <backup-folder>"
    run scripts/restore.sh "$1"
    ;;

  update)
    if [ "${1:-}" != "--yes" ]; then
      echo "Updating downloads the new version and rebuilds the images; the database is"
      echo "migrated at startup. Make a backup first: ./vhs backup <folder>"
      read -r -p "Update now? [y/N] " answer || answer=""
      case "$answer" in
        y | Y | yes | YES) ;;
        *) die "update cancelled." ;;
      esac
    fi
    run git pull --ff-only
    run docker compose up -d --build
    ;;

  manage)
    [ $# -gt 0 ] || die "usage: ./vhs manage <command> [arguments]"
    manage "$@"
    ;;

  help | -h | --help)
    usage
    ;;

  *)
    usage >&2
    die "unknown command: $command"
    ;;
esac
