#!/usr/bin/env bash
# Builds vhs.tar.gz: the files an installation keeps on the server, next to the images
# published for the same version (docs/installation.md). The release workflow attaches it to
# every GitHub release (.github/workflows/release.yml); ./vhs update downloads it.
#
# Usage: scripts/make-bundle.sh <version> <output.tar.gz>
#   <version>  the version of the published images, e.g. 0.2.0 or 0.2.0-rc.1

set -euo pipefail
cd "$(dirname "$0")/.."

[ $# -eq 2 ] || { echo "usage: scripts/make-bundle.sh <version> <output.tar.gz>" >&2; exit 1; }
version=$1
output=$2

FILES=(
  docker-compose.yml
  docker-compose.prod.yml
  .env.example
  vhs
  scripts/backup.sh
  scripts/restore.sh
  scripts/compare_reports.py
  LICENSE
)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for file in "${FILES[@]}"; do
  mkdir -p "$work/$(dirname "$file")"
  cp -p "$file" "$work/$file"
done

# The images of this version: a pre-release publishes them under its own tag.
sed -E "s#(image: ghcr\.io/rocchidavide/vhs-[a-z]+):[^[:space:]]+#\1:$version#" \
  docker-compose.yml >"$work/docker-compose.yml"

mkdir "$work/certs"
cat >"$work/certs/README.txt" <<TEXT
For HTTPS put the certificate and its key here, as fullchain.pem and privkey.pem, and set
VHS_HTTPS=true in .env (docs/installation.md, "HTTPS or HTTP on a local network").
TEXT

cat >"$work/README.txt" <<TEXT
VHS $version: the files of an installation. The VHS images are pulled from
ghcr.io/rocchidavide when VHS starts.

Installation guide: https://github.com/rocchidavide/vhs/blob/main/docs/installation.md
TEXT

# The files themselves, not ".": extracting must not change the folder they land in.
output=$(cd "$(dirname "$output")" && pwd)/$(basename "$output")
(cd "$work" && tar -czf "$output" "${FILES[@]}" README.txt certs/README.txt)
echo "$output: VHS $version"
