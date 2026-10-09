"""URL validation and canonicalization. Only the hosts of supported platforms are accepted."""

from urllib.parse import urlsplit

from engine.errors import EngineError, ErrorCode
from engine.platforms import platform_for_host

MAX_URL_LENGTH = 2048


def normalize_url(url: str) -> str:
    """Return the canonical URL of a single video, or raise EngineError."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL is missing or too long.")

    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Only http and https URLs are supported.")
    if parts.username or parts.password:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL cannot contain credentials.")
    try:
        port = parts.port
    except ValueError:
        port = -1
    if port not in (None, 80, 443):
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Unsupported port.")

    platform = platform_for_host(parts.hostname or "")
    if platform is None:
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Unsupported platform.")
    return platform.canonical_url(parts)
