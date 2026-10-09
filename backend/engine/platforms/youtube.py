import re
from urllib.parse import SplitResult, parse_qs

from engine.errors import EngineError, ErrorCode
from engine.platforms.base import Platform

_SHORT_HOSTS = frozenset({"youtu.be"})
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTube(Platform):
    key = "youtube"
    name = "YouTube"
    hosts = frozenset(
        {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"} | _SHORT_HOSTS
    )
    extractor_keys = frozenset({"youtube"})
    ytdlp_extractors = (r"youtube",)

    def canonical_url(self, parts: SplitResult) -> str:
        if (parts.hostname or "").lower().rstrip(".") in _SHORT_HOSTS:
            return _watch_url(parts.path.strip("/").split("/")[0])
        segments = [segment for segment in parts.path.split("/") if segment]
        query = parse_qs(parts.query)
        if segments[:1] == ["watch"] and query.get("v"):
            return _watch_url(query["v"][0])
        if len(segments) >= 2 and segments[0] in {"shorts", "live", "embed", "v"}:
            return _watch_url(segments[1])
        if segments[:1] == ["playlist"] or query.get("list"):
            raise EngineError(ErrorCode.PLAYLIST, "Playlists are not supported yet.")
        if segments and (segments[0].startswith("@") or segments[0] in {"channel", "c", "user"}):
            raise EngineError(ErrorCode.PLAYLIST, "Channels are not supported yet.")
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL does not identify a video.")

    def is_short(self, info: dict) -> bool | None:
        url = info.get("webpage_url") or info.get("original_url") or ""
        if "/shorts/" in url:
            return True
        width, height, duration = info.get("width"), info.get("height"), info.get("duration")
        if width is None or height is None or duration is None:
            return None
        return height > width and duration <= 180


def _watch_url(video_id: str) -> str:
    if not _VIDEO_ID.match(video_id):
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "Invalid video ID.")
    return f"https://www.youtube.com/watch?v={video_id}"
