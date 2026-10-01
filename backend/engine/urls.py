"""URL validation and canonicalization. Only allowlisted platform hosts are accepted."""

import re
from urllib.parse import parse_qs, urlsplit

from engine.errors import EngineError, ErrorCode

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
YOUTUBE_SHORT_HOSTS = {"youtu.be"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_URL_LENGTH = 2048


def normalize_url(url: str) -> str:
    """Return the canonical URL of a single video, or raise EngineError."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "URL mancante o troppo lunga.")

    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Sono supportati solo URL http e https.")
    if parts.username or parts.password:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL cannot contain credentials.")
    try:
        port = parts.port
    except ValueError:
        port = -1
    if port not in (None, 80, 443):
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Unsupported port.")

    host = (parts.hostname or "").lower().rstrip(".")
    if host in YOUTUBE_SHORT_HOSTS:
        return _youtube_watch_url(parts.path.strip("/").split("/")[0])
    if host in YOUTUBE_HOSTS:
        return _normalize_youtube(parts.path, parse_qs(parts.query))

    raise EngineError(ErrorCode.UNSUPPORTED_URL, "Unsupported platform.")


def _normalize_youtube(path: str, query: dict[str, list[str]]) -> str:
    segments = [segment for segment in path.split("/") if segment]
    if segments[:1] == ["watch"] and query.get("v"):
        return _youtube_watch_url(query["v"][0])
    if len(segments) >= 2 and segments[0] in {"shorts", "live", "embed", "v"}:
        return _youtube_watch_url(segments[1])
    if segments[:1] == ["playlist"] or query.get("list"):
        raise EngineError(ErrorCode.PLAYLIST, "Playlists are not supported yet.")
    if segments and (segments[0].startswith("@") or segments[0] in {"channel", "c", "user"}):
        raise EngineError(ErrorCode.PLAYLIST, "Channels are not supported yet.")
    raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL does not identify a video.")


def _youtube_watch_url(video_id: str) -> str:
    if not _VIDEO_ID.match(video_id):
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Invalid video ID.")
    return f"https://www.youtube.com/watch?v={video_id}"
