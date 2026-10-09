"""What VHS needs to know about a platform: one subclass per platform, listed in engine.platforms.

A platform is enabled explicitly, never by accepting any URL yt-dlp understands (§39).
"""

from urllib.parse import SplitResult

from engine.metadata import (
    ChannelMetadata,
    VideoMetadata,
    build_snapshot,
    estimate_size,
    parse_upload_date,
    to_int,
)


class Platform:
    # Stored in the database and used as the library folder: never change it.
    key: str = ""
    # Shown to people.
    name: str = ""
    # Hosts whose URLs belong to the platform (lowercase, without a trailing dot).
    hosts: frozenset[str] = frozenset()
    # yt-dlp's extractor_key of the platform's videos, lowercase.
    extractor_keys: frozenset[str] = frozenset()
    # Regexes for yt-dlp's allowed_extractors: the only extractors VHS lets it use.
    ytdlp_extractors: tuple[str, ...] = ()

    def canonical_url(self, parts: SplitResult) -> str:
        """The canonical URL of a single video, or raise EngineError. Deduplication relies on it."""
        raise NotImplementedError

    def map(self, info: dict) -> VideoMetadata:
        """Platform-neutral metadata from yt-dlp's info.

        The fields read here are yt-dlp's common ones, the same for every extractor. What
        differs between platforms goes in the methods a subclass overrides: map_channel(),
        is_short() and platform_metadata().
        """
        return VideoMetadata(
            platform=self.key,
            platform_id=str(info["id"]),
            title=info.get("title") or str(info["id"]),
            source_url=info.get("webpage_url") or info.get("original_url") or "",
            description=info.get("description") or "",
            duration=to_int(info.get("duration")),
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
            platform=self.key,
            platform_id=str(channel_id),
            name=name,
            url=info.get("channel_url") or info.get("uploader_url") or "",
        )

    def is_short(self, info: dict) -> bool | None:
        return None

    def platform_metadata(self, info: dict) -> dict:
        keys = ("tags", "categories", "live_status", "availability", "age_limit", "extractor")
        return {key: info[key] for key in keys if info.get(key) is not None}
