#!/usr/bin/env bash
# Pre-release check (docs/architecture.md §39): Nginx never serves a symbolic link from the
# library through /media-internal/, even when an X-Accel-Redirect points straight at it.
#
# Django already refuses symlinks before redirecting (get_media_path(), covered by pytest).
# This checks the second line of defense on its own: the real Nginx configs
# (docker/nginx.conf and docker/nginx.dev.conf) run against a stub backend that redirects
# to any path it is asked for. A control run with "disable_symlinks off" must serve the
# outside file through every link: it proves the links work, so a broken link can never
# make the check pass. Everything runs in throwaway containers on a private network, with
# a temporary library; nothing of the development environment is touched.
#
# Usage: scripts/check-nginx-symlinks.sh    (exit code 0 = every check passed)

set -euo pipefail

cd "$(dirname "$0")/.."

NGINX_IMAGE=nginx:alpine
STUB_IMAGE=python:3.13-slim
RUN_ID="vhs-symlink-check-$$"
SECRET="SECRET-OUTSIDE-THE-LIBRARY"

WORK=$(mktemp -d)
cleanup() {
  docker rm -f "$RUN_ID-nginx" "$RUN_ID-backend" >/dev/null 2>&1 || true
  docker network rm "$RUN_ID" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# A library with a regular file (positive control) and every kind of symlink, plus a file
# outside the library that must never be served.
mkdir -p "$WORK/library/youtube/channel" "$WORK/library/.incomplete/1" "$WORK/outside"
echo "REAL-VIDEO" >"$WORK/library/youtube/channel/real.mp4"
echo "PARTIAL" >"$WORK/library/.incomplete/1/partial.mp4"
echo "$SECRET" >"$WORK/outside/secret.mp4"
# Paths as seen inside the Nginx container: the library on /srv/video-library, the
# outside folder on /srv/outside.
ln -s /srv/outside/secret.mp4 "$WORK/library/youtube/channel/absolute-link.mp4"
ln -s ../../../outside/secret.mp4 "$WORK/library/youtube/channel/relative-link.mp4"
ln -s real.mp4 "$WORK/library/youtube/channel/inside-link.mp4"
ln -s /srv/outside "$WORK/library/youtube/linked-dir"

# Stub backend: GET /api/redirect?path=<p> answers with X-Accel-Redirect: /media-internal/<p>.
cat >"$WORK/stub.py" <<'EOF'
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = parse_qs(urlparse(self.path).query).get("path", [""])[0]
        self.send_response(200)
        self.send_header("X-Accel-Redirect", "/media-internal/" + path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
EOF

docker network create "$RUN_ID" >/dev/null
docker run -d --name "$RUN_ID-backend" --network "$RUN_ID" --network-alias backend \
  -v "$WORK/stub.py:/stub.py:ro" "$STUB_IMAGE" python /stub.py >/dev/null

failures=0
check() { # check <description> <expected status> <body must contain|-> <url path>
  # The outside file must never be served, except in the control run, where it must be.
  local description=$1 expected=$2 needle=$3 path=$4 status body
  body=$(docker exec "$RUN_ID-nginx" sh -c \
    "wget -S -q -O - 'http://127.0.0.1$path' 2>/tmp/headers; cat /tmp/headers >&2" \
    2>"$WORK/headers" || true)
  # The last HTTP status line: "HTTP/1.1 200 OK", or "... error: HTTP/1.1 403 Forbidden".
  status=$(grep -o 'HTTP/[0-9.]* [0-9]*' "$WORK/headers" | tail -n 1 | awk '{print $2}')
  local ok=1
  [ "$status" = "$expected" ] || ok=0
  if [ "$needle" != "$SECRET" ]; then
    case "$body" in *"$SECRET"*) ok=0 ;; esac
  fi
  if [ "$needle" != "-" ]; then
    case "$body" in *"$needle"*) ;; *) ok=0 ;; esac
  fi
  if [ $ok = 1 ]; then
    printf '  ok    %-48s %s\n' "$description" "$status"
  else
    printf '  FAIL  %-48s status %s (expected %s)%s\n' "$description" "${status:-none}" "$expected" \
      "$(case "$body" in *"$SECRET"*) echo ', OUTSIDE FILE SERVED' ;; esac)"
    failures=$((failures + 1))
  fi
}

start_nginx() { # start_nginx <config file>
  docker run -d --name "$RUN_ID-nginx" --network "$RUN_ID" \
    -v "$1:/etc/nginx/conf.d/default.conf:ro" \
    -v "$WORK/library:/srv/video-library:ro" \
    -v "$WORK/outside:/srv/outside:ro" \
    "$NGINX_IMAGE" >/dev/null
  for _ in $(seq 1 50); do
    docker exec "$RUN_ID-nginx" sh -c 'wget -q -O /dev/null http://127.0.0.1/api/redirect?path=youtube/channel/real.mp4' \
      >/dev/null 2>&1 && break
    sleep 0.2
  done
}

redirect="/api/redirect?path="

for config in docker/nginx.conf docker/nginx.dev.conf; do
  echo "== $config"
  start_nginx "$PWD/$config"
  check "regular file through the redirect (control)" 200 REAL-VIDEO "${redirect}youtube/channel/real.mp4"
  # A symlinked file: open() with O_NOFOLLOW fails with ELOOP, and Nginx answers 403.
  check "absolute symlink to a file outside" 403 - "${redirect}youtube/channel/absolute-link.mp4"
  check "relative symlink to a file outside" 403 - "${redirect}youtube/channel/relative-link.mp4"
  check "symlink to a file inside the library" 403 - "${redirect}youtube/channel/inside-link.mp4"
  # A symlinked directory is not walked: ENOTDIR, and Nginx answers 404.
  check "file under a symlinked directory" 404 - "${redirect}youtube/linked-dir/secret.mp4"
  check "work area of in-progress downloads" 404 - "${redirect}.incomplete/1/partial.mp4"
  check "direct request to /media-internal/" 404 - "/media-internal/youtube/channel/real.mp4"
  docker rm -f "$RUN_ID-nginx" >/dev/null
done

echo "== control: docker/nginx.conf with disable_symlinks off (every link must work)"
sed 's/disable_symlinks on;/disable_symlinks off;/' docker/nginx.conf >"$WORK/control.conf"
grep -q 'disable_symlinks off;' "$WORK/control.conf" || { echo "control config not built" >&2; exit 1; }
start_nginx "$WORK/control.conf"
check "absolute symlink is followed" 200 "$SECRET" "${redirect}youtube/channel/absolute-link.mp4"
check "relative symlink is followed" 200 "$SECRET" "${redirect}youtube/channel/relative-link.mp4"
check "symlinked directory is followed" 200 "$SECRET" "${redirect}youtube/linked-dir/secret.mp4"
docker rm -f "$RUN_ID-nginx" >/dev/null

if [ "$failures" -gt 0 ]; then
  echo "Symlink check FAILED: $failures check(s) did not pass." >&2
  exit 1
fi
echo "Symlink check passed: Nginx serves no symbolic link from the library."
