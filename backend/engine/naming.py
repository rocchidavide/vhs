"""Built-in file naming templates (§17). The platform ID is always part of the name."""

import re
import unicodedata
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath

from engine.metadata import VideoMetadata


class NamingTemplate(StrEnum):
    STANDARD = "standard"
    TV_SHOW = "tvshow"


MAX_TITLE_LENGTH = 120
MAX_CHANNEL_LENGTH = 80
UNKNOWN_CHANNEL = "Unknown channel"
UNKNOWN_DATE = "unknown-date"

_INVALID = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def sanitize_component(value: str, max_length: int) -> str:
    text = unicodedata.normalize("NFC", value or "")
    text = _INVALID.sub(" ", text)
    text = " ".join(text.split())
    text = text[:max_length].strip()
    return text.strip(". ") or "_"


def build_basename(template: NamingTemplate, metadata: VideoMetadata) -> PurePosixPath:
    """Relative path without extension, e.g. youtube/Channel/2024-03-15 - Title [id]."""
    channel = metadata.channel.name if metadata.channel else UNKNOWN_CHANNEL
    folder = PurePosixPath(
        sanitize_component(metadata.platform, 40), sanitize_component(channel, MAX_CHANNEL_LENGTH)
    )
    title = sanitize_component(metadata.title, MAX_TITLE_LENGTH)
    platform_id = sanitize_component(metadata.platform_id, 64)
    uploaded = metadata.upload_date

    if NamingTemplate(template) is NamingTemplate.TV_SHOW:
        if uploaded is None:
            return folder / "Season unknown" / f"{UNKNOWN_DATE} - {title} [{platform_id}]"
        episode = f"s{uploaded.year}.e{uploaded:%m%d}"
        return folder / f"Season {uploaded.year}" / f"{episode} - {title} [{platform_id}]"

    return folder / f"{_format_date(uploaded)} - {title} [{platform_id}]"


def with_suffix(basename: PurePosixPath, suffix: str) -> PurePosixPath:
    """Append a suffix such as '.mp4' or '.info.json' to a basename (titles may contain dots)."""
    return basename.with_name(basename.name + suffix)


def _format_date(value: date | None) -> str:
    return value.isoformat() if value else UNKNOWN_DATE
