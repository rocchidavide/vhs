"""yt-dlp backed downloader, used through its Python API."""

import logging
import shutil
from pathlib import Path

import yt_dlp
from yt_dlp.postprocessor import FFmpegThumbnailsConvertorPP
from yt_dlp.utils import DownloadError, ExtractorError, PostProcessingError, replace_extension
from yt_dlp.version import __version__ as YTDLP_VERSION

from engine.downloader.base import (
    ActivityCallback,
    BaseDownloader,
    DownloadResult,
    ProcessingCallback,
    Progress,
    ProgressCallback,
    ThumbnailCallback,
)
from engine.errors import EngineError, ErrorCode
from engine.platforms import Platform, platform_for_url, ytdlp_extractors

logger = logging.getLogger("vhs.engine.ytdlp")

# Never an audio description: YouTube marks it "<language>-desc", RaiPlay "des".
_NO_AUDIO_DESCRIPTION = "[language!*=?desc][language!=?des]"

# Provisional v1 policy: prefer H.264/AAC in MP4 for HTML5 playback, fall back to the best.
DEFAULT_FORMAT = (
    f"bv*[vcodec^=avc1][ext=mp4]+ba[acodec^=mp4a][ext=m4a]{_NO_AUDIO_DESCRIPTION}"
    f"/b[vcodec^=avc1][ext=mp4]/bv*+ba{_NO_AUDIO_DESCRIPTION}/b"
)


def format_selector(audio_language: str | None = None) -> str:
    """DEFAULT_FORMAT, asking first for the audio track in a language (§18, audio track).

    Without a language, yt-dlp's own order decides: on YouTube it puts the original track
    first. A platform that marks no track (RaiPlay) gives the language of its default one.
    """
    if not audio_language:
        return DEFAULT_FORMAT
    audio = f"[language^={audio_language}]{_NO_AUDIO_DESCRIPTION}"
    return f"bv*[vcodec^=avc1][ext=mp4]+ba[acodec^=mp4a]{audio}/bv*+ba{audio}/{DEFAULT_FORMAT}"


THUMBNAIL_POSTPROCESSOR = "ThumbnailsConvertor"


class _ThumbnailToWebp(FFmpegThumbnailsConvertorPP):
    """yt-dlp's thumbnail conversion to WebP, which never fails a download.

    ffmpeg reads the image as it is, not as its extension says: RaiPlay serves JPEG images
    named .png, which yt-dlp's own conversion refuses. If the conversion still fails, the
    video is downloaded without a thumbnail.
    """

    @classmethod
    def pp_key(cls):
        return THUMBNAIL_POSTPROCESSOR

    def convert_thumbnail(self, thumbnail_filename, target_ext):
        converted = replace_extension(thumbnail_filename, target_ext)
        try:
            self.real_run_ffmpeg(
                [(thumbnail_filename, [])], [(converted, self._options(target_ext))]
            )
        except PostProcessingError:
            # No half-written image left behind to be taken for the thumbnail.
            Path(converted).unlink(missing_ok=True)
            raise
        return converted

    def run(self, info):
        try:
            return super().run(info)
        except PostProcessingError as exc:
            logger.warning("video %s: no thumbnail (%s)", info.get("id"), exc)
            return [], info


_DRM_MARKERS = ("drm protected",)
_GEO_MARKERS = ("geo restriction", "geo-restrict", "in your country", "from your location")
_AUTH_MARKERS = ("sign in", "confirm your age", "login required", "members-only", "cookies")
_UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "is not available",
    "has been removed",
    "been terminated",
    "copyright",
    "no longer available",
    "does not exist",
)
_NETWORK_MARKERS = (
    "http error",
    "timed out",
    "timeout",
    "connection",
    "network",
    "temporary failure",
    "name resolution",
    "unable to download",
)


class _YtdlpLogger:
    def debug(self, msg):
        logger.debug(msg)

    def info(self, msg):
        logger.debug(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def available_js_runtimes() -> dict:
    """JavaScript runtimes yt-dlp needs for YouTube, in order of preference."""
    return {name: {} for name in ("deno", "node") if shutil.which(name)}


def classify_error(
    message: str, *, postprocessing: bool = False, platform: Platform | None = None
) -> ErrorCode:
    text = message.lower()
    if postprocessing or any(
        marker in text for marker in ("ffmpeg", "postprocessing", "preprocessing")
    ):
        return ErrorCode.PROCESSING
    if any(marker in text for marker in _DRM_MARKERS):
        return ErrorCode.DRM
    if any(marker in text for marker in _GEO_MARKERS):
        return ErrorCode.GEO_RESTRICTED
    if platform and (code := platform.classify_error(message)):
        return code
    if any(marker in text for marker in _AUTH_MARKERS):
        return ErrorCode.AUTHENTICATION
    if any(marker in text for marker in _UNAVAILABLE_MARKERS):
        return ErrorCode.SOURCE_UNAVAILABLE
    if any(marker in text for marker in _NETWORK_MARKERS):
        return ErrorCode.NETWORK
    if "unsupported url" in text:
        return ErrorCode.UNSUPPORTED_URL
    if "no space left" in text or "disk quota" in text:
        return ErrorCode.STORAGE
    return ErrorCode.UNKNOWN


class StreamProgress:
    """Sums the progress of the streams yt-dlp downloads one after the other.

    With separate video and audio formats yt-dlp reports each stream on its own, starting
    again from zero: reported as is, the progress would go back at every new stream.
    """

    def __init__(self):
        # Per stream (its file name): bytes downloaded and total, None when not known.
        self._streams: dict[str, tuple[int, int | None]] = {}

    def update(self, data: dict) -> Progress:
        name = data.get("filename") or data.get("tmpfilename") or ""
        downloaded = data.get("downloaded_bytes") or 0
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        if data.get("status") == "finished":
            downloaded = total = total or downloaded
        self._streams[name] = (downloaded, total)

        totals = [stream_total for _, stream_total in self._streams.values()]
        return Progress(
            downloaded_bytes=sum(done for done, _ in self._streams.values()),
            total_bytes=sum(totals) if all(totals) else None,
            speed=data.get("speed"),
            stream_eta=data.get("eta"),
        )

    @property
    def started(self) -> bool:
        return bool(self._streams)


class YTDLPDownloader(BaseDownloader):
    def __init__(self, format_selector: str | None = None, extra_options: dict | None = None):
        # None: the format of each URL's platform (format_selector()).
        self.format_selector = format_selector
        self.extra_options = extra_options or {}

    @property
    def version(self) -> str:
        # The version actually imported: the emergency update may override the image's one.
        return YTDLP_VERSION

    def _options(self, url: str, **overrides) -> dict:
        platform = platform_for_url(url)
        options = {
            "logger": _YtdlpLogger(),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "allowed_extractors": ytdlp_extractors(),
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "format": self.format_selector
            or format_selector(platform.default_audio_language if platform else None),
            "js_runtimes": available_js_runtimes(),
        }
        options.update(self.extra_options)
        options.update(overrides)
        return options

    def extract_info(self, url: str) -> dict:
        try:
            with yt_dlp.YoutubeDL(self._options(url)) as ydl:
                info = ydl.sanitize_info(ydl.extract_info(url, download=False))
        except (DownloadError, ExtractorError) as exc:
            code = classify_error(str(exc), platform=platform_for_url(url))
            raise EngineError(code, str(exc)) from exc
        if info.get("_type") in {"playlist", "multi_video"}:
            raise EngineError(ErrorCode.PLAYLIST, "The URL points to a playlist, not a video.")
        return info

    def download(
        self,
        url: str,
        work_dir: Path,
        on_progress: ProgressCallback,
        on_activity: ActivityCallback,
        on_thumbnail: ThumbnailCallback | None = None,
        on_processing: ProcessingCallback | None = None,
    ) -> DownloadResult:
        thumbnail_notified = False
        processing_notified = False
        streams = StreamProgress()

        def progress_hook(data: dict) -> None:
            status = data.get("status")
            if status in ("downloading", "finished"):
                progress = streams.update(data)
                if status == "downloading":
                    on_progress(progress)
                    return
            on_activity()

        def postprocessor_hook(data: dict) -> None:
            nonlocal thumbnail_notified, processing_notified
            on_activity()
            # Post-processors after the transfer (merging video and audio, moving the file):
            # the thumbnail conversion runs before it and does not count.
            if (
                on_processing
                and not processing_notified
                and streams.started
                and data.get("postprocessor") != THUMBNAIL_POSTPROCESSOR
                and data.get("status") == "started"
            ):
                processing_notified = True
                on_processing()
            # The thumbnail is converted before the media transfer starts (when="before_dl").
            if (
                on_thumbnail
                and not thumbnail_notified
                and data.get("postprocessor") == THUMBNAIL_POSTPROCESSOR
                and data.get("status") == "finished"
            ):
                video_id = (data.get("info_dict") or {}).get("id")
                thumbnail = work_dir / f"{video_id}.webp"
                if video_id and thumbnail.is_file():
                    thumbnail_notified = True
                    on_thumbnail(thumbnail)

        options = self._options(
            url,
            paths={"home": str(work_dir), "temp": str(work_dir)},
            outtmpl={"default": "%(id)s.%(ext)s"},
            overwrites=False,
            writeinfojson=True,
            writethumbnail=True,
            merge_output_format="mp4/mkv",
            progress_hooks=[progress_hook],
            postprocessor_hooks=[postprocessor_hook],
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.add_post_processor(_ThumbnailToWebp(ydl, format="webp"), when="before_dl")
                info = ydl.sanitize_info(ydl.extract_info(url, download=True))
        except PostProcessingError as exc:
            raise EngineError(ErrorCode.PROCESSING, str(exc)) from exc
        except (DownloadError, ExtractorError) as exc:
            code = classify_error(str(exc), platform=platform_for_url(url))
            raise EngineError(code, str(exc)) from exc
        except OSError as exc:
            raise EngineError(ErrorCode.STORAGE, str(exc)) from exc

        return self._result(info, work_dir)

    def _result(self, info: dict, work_dir: Path) -> DownloadResult:
        downloads = info.get("requested_downloads") or [{}]
        media = Path(downloads[0].get("filepath") or "")
        if not media.is_file():
            raise EngineError(ErrorCode.PROCESSING, "The downloaded file was not found.")

        stem = str(info["id"])
        info_json = work_dir / f"{stem}.info.json"
        thumbnail = work_dir / f"{stem}.webp"
        return DownloadResult(
            media=media,
            info_json=info_json if info_json.is_file() else None,
            thumbnail=thumbnail if thumbnail.is_file() else None,
            info=info,
        )
