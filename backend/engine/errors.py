"""Engine error model: a stable category plus a sanitized diagnostic message."""

import re
from enum import StrEnum


class ErrorCode(StrEnum):
    AUTHENTICATION = "authentication"
    SOURCE_UNAVAILABLE = "source_unavailable"
    GEO_RESTRICTED = "geo_restricted"
    DRM = "drm"
    NETWORK = "network"
    STORAGE = "storage"
    PROCESSING = "processing"
    UNSUPPORTED_URL = "unsupported_url"
    PLAYLIST = "playlist"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class EngineError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = ErrorCode(code)
        self.message = sanitize_message(message)
        super().__init__(f"{self.code}: {self.message}")


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_URL_QUERY = re.compile(r"(https?://[^\s?#'\"]+)[?#][^\s'\"]*")
_SECRET_PAIR = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|token|sig|signature|key|password|"
    r"sapisid|sid|hsid|ssid|apisid|__secure-[\w-]+)(\s*[=:]\s*)([^\s;,&'\"]+)"
)
_INCOMPLETE_PATH = re.compile(r"(?:/[^\s'\"]*)?/\.incomplete/[^\s'\"]*")

MAX_MESSAGE_LENGTH = 1000


def sanitize_message(message: str) -> str:
    """Strip terminal colors, URL query strings, credential-like values and work paths."""
    text = _ANSI.sub("", str(message))
    text = _URL_QUERY.sub(r"\1", text)
    text = _SECRET_PAIR.sub(r"\1\2[redacted]", text)
    text = _INCOMPLETE_PATH.sub("[work-dir]", text)
    text = " ".join(text.split())
    return text[:MAX_MESSAGE_LENGTH]
