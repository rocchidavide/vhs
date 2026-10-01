"""Mapping from raw downloader info to platform-neutral metadata."""

from dataclasses import dataclass, field
from datetime import date, datetime

# Keys that are bulky, short-lived or may carry credentials: never persisted in snapshots.
SNAPSHOT_EXCLUDED_KEYS = {
    "formats",
    "requested_formats",
    "requested_downloads",
    "requested_subtitles",
    "thumbnails",
    "subtitles",
    "automatic_captions",
    "http_headers",
    "cookies",
    "url",
    "manifest_url",
    "fragments",
    "heatmap",
    "_format_sort_fields",
}


@dataclass(frozen=True)
class ChannelMetadata:
    platform: str
    platform_id: str
    name: str
    url: str = ""


@dataclass(frozen=True)
class VideoMetadata:
    platform: str
    platform_id: str
    title: str
    source_url: str
    description: str = ""
    duration: int | None = None
    upload_date: date | None = None
    thumbnail_url: str = ""
    channel: ChannelMetadata | None = None
    is_short: bool | None = None
    estimated_size: int | None = None
    platform_metadata: dict = field(default_factory=dict)
    snapshot: dict = field(default_factory=dict)


class MetadataExtractor:
    platform = "generic"

    def map(self, info: dict) -> VideoMetadata:
        return VideoMetadata(
            platform=self.platform,
            platform_id=str(info["id"]),
            title=info.get("title") or str(info["id"]),
            source_url=info.get("webpage_url") or info.get("original_url") or "",
            description=info.get("description") or "",
            duration=_to_int(info.get("duration")),
            upload_date=parse_upload_date(info.get("upload_date")),
            thumbnail_url=info.get("thumbnail") or "",
            channel=self.map_channel(info),
            is_short=self.is_short(info),
            estimated_size=estimate_size(info),
            platform_metadata=self.platform_metadata(info),
            snapshot=build_snapshot(info),
        )

    def map_channel(self, info: dict) -> ChannelMetadata | None:
        channel_id = info.get("channel_id") or info.get("uploader_id")
        name = info.get("channel") or info.get("uploader")
        if not channel_id or not name:
            return None
        return ChannelMetadata(
            platform=self.platform,
            platform_id=str(channel_id),
            name=name,
            url=info.get("channel_url") or info.get("uploader_url") or "",
        )

    def is_short(self, info: dict) -> bool | None:
        return None

    def platform_metadata(self, info: dict) -> dict:
        keys = ("tags", "categories", "live_status", "availability", "age_limit", "extractor")
        return {key: info[key] for key in keys if info.get(key) is not None}


def parse_upload_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def estimate_size(info: dict) -> int | None:
    """Best-effort size of the selected formats; None when the source does not say."""
    requested = info.get("requested_formats") or [info]
    sizes = [fmt.get("filesize") or fmt.get("filesize_approx") for fmt in requested]
    if not sizes or any(size is None for size in sizes):
        return None
    return int(sum(sizes))


def build_snapshot(info: dict) -> dict:
    return {key: value for key, value in info.items() if key not in SNAPSHOT_EXCLUDED_KEYS}


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
