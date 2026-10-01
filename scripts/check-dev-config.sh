#!/usr/bin/env bash
# Check the MERGED Compose configuration (not the files one by one): published ports, builds,
# images, mounts, commands, users and project name, for development and for an installation.
#
# Usage: scripts/check-dev-config.sh
#
# Development: docker-compose.yml + docker-compose.dev.yml with .env.dev.example.
# Installation: docker-compose.yml alone and with docker-compose.prod.yml, with .env.example.
# Overrides add ports and volumes to the main file, so a missing "!override" would silently
# publish more than intended: this is what the script catches.

set -euo pipefail
cd "$(dirname "$0")/.."

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# A library path that exists, so that the check does not depend on this machine.
mkdir -p "$TMP/library"

config() { # <env-file> <compose files...>
  local env_file=$1
  shift
  local args=()
  for file in "$@"; do args+=(-f "$file"); done
  env -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME VHS_HOST_LIBRARY="$TMP/library" \
    docker compose --env-file "$env_file" "${args[@]}" config --format json
}

config .env.dev.example docker-compose.yml docker-compose.dev.yml >"$TMP/dev.json"
config .env.example docker-compose.yml >"$TMP/base.json"
config .env.example docker-compose.yml docker-compose.prod.yml >"$TMP/prod.json"

docker run --rm -i -e REPO="$PWD" -v "$TMP:/check:ro" python:3.13-slim python - <<'PY'
import json, os, sys

REPO = os.environ["REPO"]
failures = []


def load(name):
    with open(f"/check/{name}.json") as handle:
        return json.load(handle)


def ports(service):
    return sorted(
        f"{p.get('host_ip', '0.0.0.0') or '0.0.0.0'}:{p['published']}->{p['target']}"
        for p in service.get("ports", [])
    )


def mounts(service):
    return sorted(
        (m["type"], m.get("source", "").replace("/check/", "").rstrip("/"), m["target"], bool(m.get("read_only")))
        for m in service.get("volumes", [])
    )


def expect(label, actual, wanted):
    ok = actual == wanted
    print(f"  {'ok ' if ok else 'ERR'} {label}: {actual}")
    if not ok:
        print(f"      expected: {wanted}")
        failures.append(label)


def library_source(config):
    for service in config["services"].values():
        for m in service.get("volumes", []):
            if m["target"] == "/srv/video-library":
                return m["source"]


print("== Development (docker-compose.yml + docker-compose.dev.yml, .env.dev.example)")
dev = load("dev")
lib = library_source(dev)
s = dev["services"]
expect("project", dev["name"], "vhs-dev")
expect("services", sorted(s), ["backend", "db", "frontend", "migrate", "nginx", "worker"])
published = {name: ports(svc) for name, svc in s.items() if ports(svc)}
expect("published ports", published, {"nginx": ["127.0.0.1:8081->80"]})
for name in ("migrate", "backend", "worker"):
    svc = s[name]
    expect(f"{name}: build target", svc.get("build", {}).get("target"), "dev")
    expect(f"{name}: image", svc.get("image"), "vhs-backend-dev")
    expect(f"{name}: user", svc.get("user"), "1000:1000")
    targets = {m[2]: m for m in mounts(svc)}
    expect(f"{name}: repository mounted", targets.get("/app", (None, None))[:2], ("bind", REPO))
    expect(f"{name}: library writable", targets.get("/srv/video-library", (0, 0, 0, None))[3], False)
expect("backend: command", s["backend"].get("command"), ["python", "manage.py", "runserver", "0.0.0.0:8000"])
expect("worker: command", s["worker"].get("command")[:1], ["watchfiles"])
expect("nginx: build", "build" in s["nginx"], False)
expect("nginx: image", s["nginx"].get("image"), "nginx:alpine")
expect("nginx: mounts", [m[2:] for m in mounts(s["nginx"])], [("/etc/nginx/conf.d/default.conf", True), ("/srv/video-library", True)])
expect("frontend: ports", ports(s["frontend"]), [])

for label, name in (("Installation (docker-compose.yml, .env.example)", "base"),
                    ("Installation (docker-compose.yml + docker-compose.prod.yml, .env.example)", "prod")):
    print(f"== {label}")
    cfg = load(name)
    s = cfg["services"]
    expect("project", cfg["name"], "vhs")
    expect("services", sorted(s), ["backend", "db", "migrate", "nginx", "worker"])
    published = {n: ports(svc) for n, svc in s.items() if ports(svc)}
    wanted = {"nginx": ["0.0.0.0:8080->80"]} if name == "base" else {"nginx": ["0.0.0.0:443->443", "0.0.0.0:80->80"]}
    expect("published ports", published, wanted)
    for n in ("migrate", "backend", "worker"):
        svc = s[n]
        expect(f"{n}: build target", svc.get("build", {}).get("target"), "prod")
        expect(f"{n}: image", svc.get("image"), "vhs-backend")
        expect(f"{n}: repository mounted", any(m[2] == "/app" for m in mounts(svc)), False)
    expect("nginx: SPA build", "build" in s["nginx"], True)
    lib_mounts = {n: [m[3] for m in mounts(svc) if m[2] == "/srv/video-library"] for n, svc in s.items()}
    expect("library read-only per service", lib_mounts, {"backend": [False], "db": [], "migrate": [False], "nginx": [True], "worker": [False]})

print()
if failures:
    print(f"CONFIGURATION NOT AS EXPECTED: {len(failures)} checks failed.")
    sys.exit(1)
print("Merged configuration as expected.")
PY
