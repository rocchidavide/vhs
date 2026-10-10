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

# The version of VHS in a docker-compose.yml: the tag of its published images.
compose_version() {
  sed -nE 's#^[[:space:]]*image: ghcr\.io/rocchidavide/vhs-backend:([^[:space:]]+).*#\1#p' "$1" | head -n 1
}

# Whether version $1 is newer than $2 (X.Y.Z or X.Y.Z-rc.N). sort -V alone puts a release
# candidate after its own release.
newer_version() {
  [ "$1" != "$2" ] || return 1
  if [ "${1%%-*}" = "${2%%-*}" ]; then
    case "$1" in *-*) ;; *) return 0 ;; esac
    case "$2" in *-*) ;; *) return 1 ;; esac
  fi
  [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
}

ask() {
  local answer
  read -r -p "$1 [y/N] " answer || answer=""
  case "$answer" in
    y | Y | yes | YES) return 0 ;;
    *) return 1 ;;
  esac
}

# The database lives in a Docker volume that outlives this folder, and every installation on
# the machine gets the same one (Compose project "vhs"). .vhs-database records the volume this
# folder uses, so that a new folder never takes over the database of a previous installation
# in silence, and a database that disappeared is never replaced by an empty one in silence.
DB_RECORD=.vhs-database

compose_project() {
  docker compose config 2>/dev/null | sed -n 's/^name: //p' | head -n 1
}

db_volume() {
  docker volume ls -q --filter "label=com.docker.compose.project=$1" \
    --filter "label=com.docker.compose.volume=pgdata" | head -n 1
}

volume_created() {
  docker volume inspect --format '{{.CreatedAt}}' "$1"
}

# 2026-10-08T22:03:10Z -> 2026-10-08 22:03
show_date() {
  local date=${1/T/ }
  echo "${date:0:16}"
}

# Compose labels each container with the folder it was started from.
started_here() {
  local dir here
  here=$(pwd -P)
  while read -r dir; do
    [ -n "$dir" ] && [ "$(cd "$dir" 2>/dev/null && pwd -P)" = "$here" ] && return 0
  done < <(docker ps -a --filter "label=com.docker.compose.project=$1" \
    --format '{{.Label "com.docker.compose.project.working_dir"}}')
  return 1
}

# Before starting: stop and ask when the database is not the one this folder used.
check_database() {
  local assume_yes=$1 project volume created="" recorded="" recorded_created="" question
  project=$(compose_project)
  [ -n "$project" ] || return 0 # docker compose itself reports what is wrong
  volume=$(db_volume "$project")
  [ -z "$volume" ] || created=$(volume_created "$volume")
  if [ -f "$DB_RECORD" ]; then
    recorded=$(sed -n 's/^volume=//p' "$DB_RECORD")
    recorded_created=$(sed -n 's/^created=//p' "$DB_RECORD")
  fi

  if [ -z "$volume" ] && [ -z "$recorded" ]; then
    return 0 # a new installation
  elif [ -n "$volume" ] && [ "$volume" = "$recorded" ] && [ "$created" = "$recorded_created" ]; then
    return 0
  elif [ -n "$volume" ] && [ -z "$recorded" ] && started_here "$project"; then
    return 0 # installed before VHS 0.2.2, which writes the record
  fi

  echo >&2
  if [ -z "$volume" ]; then
    cat >&2 <<EOF
The database of this installation (created $(show_date "$recorded_created")) no longer exists.
Starting creates a new, empty database, without the users, videos, tags and collections of
this installation; the files in the video library are not touched.
EOF
    question="Start with a new, empty database?"
  elif [ -z "$recorded" ]; then
    cat >&2 <<EOF
A VHS database already exists on this machine (created $(show_date "$created")), not started
from this folder: probably a previous installation. If you continue, this installation uses
it, with its users, videos, tags and collections.
EOF
    question="Continue with the existing database?"
  else
    cat >&2 <<EOF
The database is not the one this installation used: it was created on $(show_date "$created"),
the one of this installation on $(show_date "$recorded_created"). If you continue, this
installation uses it, with its users, videos, tags and collections.
EOF
    question="Continue with this database?"
  fi
  echo "Before answering, see docs/installation.md, \"Troubleshooting\"." >&2
  echo >&2
  [ "$assume_yes" = "--yes" ] || ask "$question" || die "nothing was started or changed (to continue anyway, add --yes)."
}

# After starting: the database this folder now uses. Written only when it changes, so that a
# record written by "sudo ./vhs restore" does not need sudo afterwards.
record_database() {
  local project volume content
  project=$(compose_project)
  [ -n "$project" ] || return 0
  volume=$(db_volume "$project")
  [ -n "$volume" ] || return 0
  content=$(printf '# The database of this installation, written by ./vhs: do not edit.\nvolume=%s\ncreated=%s' \
    "$volume" "$(volume_created "$volume")")
  [ "$(cat "$DB_RECORD" 2>/dev/null)" = "$content" ] && return 0
  printf '%s\n' "$content" 2>/dev/null >"$DB_RECORD" \
    || echo "vhs: could not write $DB_RECORD in this folder (check its owner)." >&2
}

usage() {
  cat <<'EOF'
Usage: ./vhs <command> [arguments]

  start [--yes]         start VHS; asks first if the database is not this installation's
  stop                  stop VHS (videos and database are kept)
  status                show the services
  logs [service]        follow the logs (all services or one)
  create-user           create a user to sign in with
  storage-status        show the state of the video library
  verify [--checksums]  compare the database with the video library (read-only)
  init-library          mark an existing VHS library folder (checks its videos first)
  backup <folder>       back up database and videos into <folder>
  restore <backup>      restore a backup into a new, never-started installation
  update [--yes]        update VHS to the latest release; make a backup first
  manage <command>      any Django command (manage.py)
  help                  this list

On Linux run backup and restore with sudo, so that file owners are preserved.
EOF
}

command=${1:-help}
[ $# -gt 0 ] && shift

case "$command" in
  start)
    check_database "${1:-}"
    run docker compose up -d
    record_database
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
    status=0
    run scripts/restore.sh "$1" || status=$?
    # 0 and 3: the database was restored here, so it is this installation's.
    if [ "$status" -eq 0 ] || [ "$status" -eq 3 ]; then record_database; fi
    exit "$status"
    ;;

  update)
    # The files of the latest release (scripts/make-bundle.sh); VHS_RELEASE_URL is for tests.
    url=${VHS_RELEASE_URL:-https://github.com/rocchidavide/vhs/releases/latest/download/vhs.tar.gz}
    command -v curl >/dev/null || die "curl is not installed."
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    curl -fsSL "$url" -o "$work/vhs.tar.gz" || die "could not download $url"
    mkdir "$work/release"
    tar -xzf "$work/vhs.tar.gz" -C "$work/release" || die "$url is not a VHS release."
    current=$(compose_version docker-compose.yml)
    latest=$(compose_version "$work/release/docker-compose.yml")
    [ -n "$latest" ] || die "$url is not a VHS release."
    if [ "$latest" = "$current" ]; then
      echo "VHS $current is the latest release: nothing to update."
      exit 0
    fi
    # Forward only: the database migrations of a newer version cannot be undone.
    if [ -n "$current" ] && ! newer_version "$latest" "$current"; then
      die "this installation (VHS $current) is newer than the latest release ($latest): nothing to update."
    fi
    echo "VHS ${current:-?} -> $latest. Release notes: https://github.com/rocchidavide/vhs/releases/tag/v$latest"
    check_database "${1:-}"
    if [ "${1:-}" != "--yes" ]; then
      echo "Updating downloads the new images, replaces the VHS files in this folder (never .env)"
      echo "and restarts VHS; the database is migrated at startup. Make a backup first:"
      echo "./vhs backup <folder>"
      read -r -p "Update now? [y/N] " answer || answer=""
      case "$answer" in
        y | Y | yes | YES) ;;
        *) die "update cancelled." ;;
      esac
    fi
    # The images first: if one cannot be downloaded, the folder still is the previous release.
    while read -r image; do
      run docker pull -q "$image" >/dev/null \
        || die "could not download $image. Nothing was changed: this folder still has VHS ${current:-the previous release}. Check the connection and run ./vhs update again."
    done < <(sed -nE 's#^[[:space:]]*image:[[:space:]]*([^[:space:]]+).*#\1#p' \
      "$work/release/docker-compose.yml" | sort -u)
    # Each file is replaced by a rename, this script included: the running copy is not changed.
    (cd "$work/release" && find . -type f) | while read -r file; do
      mkdir -p "$(dirname "$file")"
      cp -p "$work/release/$file" "$file.new"
      mv -f "$file.new" "$file"
    done
    run docker compose up -d
    record_database
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
