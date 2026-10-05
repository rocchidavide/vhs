"""Versions of VHS and its tools, and whether a newer VHS release exists."""

import json
import logging
import re
import shutil
import subprocess
import tomllib
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from services.dependencies import get_downloader

logger = logging.getLogger("vhs.system")

UPDATE_CHECK_URL = "https://api.github.com/repos/rocchidavide/vhs/releases/latest"
UPDATE_CHECK_TIMEOUT = 3
UPDATE_CACHE_KEY = "vhs:latest-release"
UPDATE_CHECK_INTERVAL = 12 * 60 * 60
UPDATE_RETRY_AFTER_FAILURE = 60 * 60
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class Release:
    version: str
    url: str


@lru_cache(maxsize=1)
def vhs_version() -> str:
    """The version in pyproject.toml, which is part of the image."""
    try:
        with open(settings.PROJECT_DIR / "pyproject.toml", "rb") as file:
            return str(tomllib.load(file)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return ""


@lru_cache(maxsize=1)
def deno_version() -> str:
    deno = shutil.which("deno")
    if not deno:
        return ""
    try:
        output = subprocess.run(
            [deno, "--version"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    match = re.match(r"deno (\S+)", output)
    return match.group(1) if match else ""


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.match(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def latest_release() -> Release | None:
    """The latest published release, asked to GitHub at most every 12 hours.

    Never raises: a failed check is remembered for an hour and reported as "unknown".
    """
    if not settings.VHS_UPDATE_CHECK:
        return None
    cached = cache.get(UPDATE_CACHE_KEY)
    if cached is not None:
        return Release(**cached) if cached else None
    release = _fetch_latest_release()
    if release is None:
        cache.set(UPDATE_CACHE_KEY, {}, UPDATE_RETRY_AFTER_FAILURE)
        return None
    cache.set(
        UPDATE_CACHE_KEY, {"version": release.version, "url": release.url}, UPDATE_CHECK_INTERVAL
    )
    return release


def _fetch_latest_release() -> Release | None:
    request = urllib.request.Request(
        UPDATE_CHECK_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"VHS/{vhs_version() or 'unknown'}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=UPDATE_CHECK_TIMEOUT) as r:
            data = json.load(r)
    except (OSError, ValueError) as exc:
        logger.info("update check failed: %s", exc)
        return None
    tag, url = str(data.get("tag_name") or ""), str(data.get("html_url") or "")
    if parse_version(tag) is None or not url.startswith("https://github.com/"):
        return None
    return Release(version=tag.lstrip("v"), url=url)


def update_available(current: str, release: Release | None) -> bool:
    current_version, latest = parse_version(current), release and parse_version(release.version)
    return bool(current_version and latest and latest > current_version)


def system_info() -> dict:
    current = vhs_version()
    release = latest_release()
    return {
        "vhs_version": current,
        "ytdlp_version": get_downloader().version,
        "deno_version": deno_version(),
        "ytdlp_auto_update": settings.VHS_YTDLP_AUTO_UPDATE,
        "latest_version": release.version if release else None,
        "latest_release_url": release.url if release else None,
        "update_available": update_available(current, release),
    }
