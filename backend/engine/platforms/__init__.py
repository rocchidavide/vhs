"""The platforms VHS supports. To add one: a Platform subclass in this package, listed here."""

from engine.platforms.base import Platform
from engine.platforms.youtube import YouTube

PLATFORMS: tuple[Platform, ...] = (YouTube(),)

_BY_KEY = {platform.key: platform for platform in PLATFORMS}
_BY_HOST = {host: platform for platform in PLATFORMS for host in platform.hosts}
_BY_EXTRACTOR = {key: platform for platform in PLATFORMS for key in platform.extractor_keys}


def get_platform(key: str | None) -> Platform | None:
    return _BY_KEY.get(key or "")


def platform_for_host(host: str) -> Platform | None:
    return _BY_HOST.get(host.lower().rstrip("."))


def platform_for_info(info: dict) -> Platform | None:
    """The platform of a video as extracted by yt-dlp; None when VHS does not support it."""
    return _BY_EXTRACTOR.get((info.get("extractor_key") or "").lower())


def ytdlp_extractors() -> list[str]:
    return [pattern for platform in PLATFORMS for pattern in platform.ytdlp_extractors]


__all__ = [
    "PLATFORMS",
    "Platform",
    "get_platform",
    "platform_for_host",
    "platform_for_info",
    "ytdlp_extractors",
]
