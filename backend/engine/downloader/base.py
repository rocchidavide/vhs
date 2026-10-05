from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Progress:
    """Transfer progress over all the streams of a download seen so far.

    A download can be several streams fetched one after the other (e.g. video, then audio):
    total_bytes covers only the streams already started, and stream_eta only the current
    stream. Neither is an overall figure; the caller combines them with its own estimate.
    """

    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    stream_eta: int | None = None


@dataclass(frozen=True)
class MediaDetails:
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    resolution: str = ""


@dataclass(frozen=True)
class DownloadResult:
    media: Path
    info_json: Path | None = None
    thumbnail: Path | None = None
    info: dict = field(default_factory=dict)


def describe_media(info: dict, media_name: str) -> MediaDetails:
    """Container and codecs as reported by the source (verified with ffprobe in phase 2)."""
    width, height = info.get("width"), info.get("height")
    return MediaDetails(
        container=Path(media_name).suffix.lstrip(".").lower(),
        video_codec=_codec(info.get("vcodec")),
        audio_codec=_codec(info.get("acodec")),
        resolution=f"{width}x{height}" if width and height else "",
    )


def _codec(value: str | None) -> str:
    return "" if value in (None, "none") else str(value)


ProgressCallback = Callable[[Progress], None]
ActivityCallback = Callable[[], None]
ProcessingCallback = Callable[[], None]
ThumbnailCallback = Callable[[Path], None]


class BaseDownloader(ABC):
    @property
    def version(self) -> str:
        """Version of the download tool, recorded with every attempt; empty if unknown."""
        return ""

    @abstractmethod
    def extract_info(self, url: str) -> dict:
        """Return raw metadata for a single video without downloading it."""

    @abstractmethod
    def download(
        self,
        url: str,
        work_dir: Path,
        on_progress: ProgressCallback,
        on_activity: ActivityCallback,
        on_thumbnail: ThumbnailCallback | None = None,
        on_processing: ProcessingCallback | None = None,
    ) -> DownloadResult:
        """Download the video and its sidecars into work_dir (never into the library).

        on_thumbnail receives the converted thumbnail as soon as it exists, before the
        media transfer starts, so it can be shown while the download is running.
        on_processing is called once, when the transfer is over and post-processing (e.g.
        merging video and audio) starts: no more bytes arrive from then on.
        """
