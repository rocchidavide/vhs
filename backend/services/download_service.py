"""Download use cases: request, execute, retry and reconcile (§9, §16, §36)."""

import json
import logging
import shutil
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from core.models import (
    ACTIVE_STATUSES,
    RETRYABLE_STATUSES,
    RUNNING_STATUSES,
    Channel,
    Download,
    DownloadStatus,
    LocalStatus,
    PlaybackAction,
    SourceStatus,
    Video,
)
from engine.audio import downloaded_audio_format
from engine.downloader.base import BaseDownloader, DownloadResult, Progress, describe_media
from engine.errors import EngineError, ErrorCode, sanitize_message
from engine.metadata import ChannelMetadata, VideoMetadata, build_snapshot, estimate_size
from engine.naming import NamingTemplate, build_basename, with_suffix
from engine.platforms import get_platform, platform_for_info
from engine.urls import normalize_url
from services.dependencies import get_downloader, get_storage
from services.jobs import Heartbeat, enqueue_task
from services.library_service import MESSAGES, LibraryState, prepare_for_write
from services.playback_service import enqueue_analysis
from storage import Storage, StorageError

logger = logging.getLogger("vhs.downloads")

DOWNLOAD_TASK = "tasks.downloads.download_task"
SPACE_SAFETY_FACTOR = 1.2
# 100% is recorded only once the file is archived: the transfer alone never reaches it.
MAX_TRANSFER_PERCENT = 99.0
ENQUEUE_GRACE = timedelta(seconds=60)
INTERRUPTED_MESSAGE = gettext_lazy(
    "The download was interrupted: the worker was restarted or is not responding."
)


class AlreadyArchived(Exception):
    """The video already has an available local copy: it is never downloaded again."""

    def __init__(self, video: Video):
        super().__init__(gettext("This video is already archived."))
        self.video = video


class InvalidDownloadState(Exception):
    """The requested operation is not allowed in the current download state."""


def enqueue_download(download_id: int) -> None:
    enqueue_task(DOWNLOAD_TASK, download_id, task_name=f"download-{download_id}")


class DownloadService:
    def __init__(
        self,
        downloader: BaseDownloader | None = None,
        storage: Storage | None = None,
        enqueue=enqueue_download,
        on_archived=None,
    ):
        self.downloader = downloader or get_downloader()
        self.storage = storage or get_storage()
        self._enqueue = enqueue
        # Called with the video ID once a copy is archived: triggers the playback analysis.
        self._on_archived = on_archived or enqueue_analysis

    # Request ----------------------------------------------------------------------------

    def request(self, url: str) -> tuple[Download, bool]:
        """Create (or return) the download for a video URL. Returns (download, created)."""
        canonical = normalize_url(url)
        info = self.downloader.extract_info(canonical)
        platform = platform_for_info(info)
        if platform is None:
            raise EngineError(ErrorCode.UNSUPPORTED_URL, gettext("Unsupported platform."))
        metadata = platform.map(info)

        with transaction.atomic():
            video = self._upsert_video(metadata)
            return self._create_attempt(video, estimated_size=metadata.estimated_size)

    def retry(self, download_id: int) -> tuple[Download, bool]:
        """Start a new attempt for a failed or cancelled download, keeping the old one."""
        previous = Download.objects.select_related("video").get(pk=download_id)
        self._check_retryable(previous)
        # Outside the transaction: it is a network call.
        estimated = self._current_estimate(previous.video)
        with transaction.atomic():
            previous = Download.objects.select_for_update().get(pk=download_id)
            self._check_retryable(previous)
            # The previous size is only a fallback: the selected formats may have changed.
            return self._create_attempt(
                previous.video, estimated_size=estimated or previous.total_bytes
            )

    @staticmethod
    def _check_retryable(download: Download) -> None:
        if download.status not in RETRYABLE_STATUSES:
            raise InvalidDownloadState(
                gettext("Only failed or cancelled downloads can be retried.")
            )

    def _current_estimate(self, video: Video) -> int | None:
        """Size of the formats the source offers now; None when it cannot be asked."""
        try:
            info = self.downloader.extract_info(video.source_url)
        except EngineError as exc:
            logger.info("video %s: no current size estimate (%s)", video.platform_id, exc.code)
            return None
        return estimate_size(info)

    def _upsert_video(self, metadata: VideoMetadata) -> Video:
        channel = self._upsert_channel(metadata.channel)
        video, _ = Video.objects.update_or_create(
            platform=metadata.platform,
            platform_id=metadata.platform_id,
            defaults={
                "title": metadata.title[:500],
                "description": metadata.description,
                "duration": metadata.duration,
                "thumbnail_url": metadata.thumbnail_url,
                "source_url": metadata.source_url,
                "upload_date": metadata.upload_date,
                "channel": channel,
                "platform_metadata": {**metadata.platform_metadata, "is_short": metadata.is_short},
                "source_status": SourceStatus.AVAILABLE,
            },
        )
        return video

    def _upsert_channel(self, metadata: ChannelMetadata | None) -> Channel | None:
        if metadata is None or get_platform(metadata.platform) is None:
            return None
        channel, _ = Channel.objects.update_or_create(
            platform=metadata.platform,
            platform_id=metadata.platform_id,
            defaults={"name": metadata.name[:255], "url": metadata.url},
        )
        return channel

    def _create_attempt(self, video: Video, estimated_size: int | None) -> tuple[Download, bool]:
        """One active attempt per video; an archived video is never downloaded again."""
        video = Video.objects.select_for_update().get(pk=video.pk)

        active = video.downloads.filter(status__in=ACTIVE_STATUSES).first()
        if active:
            return active, False
        if video.local_status == LocalStatus.AVAILABLE:
            # The guard is the state of the file, not the existence of a completed attempt:
            # an archived video without one (registered by hand, imported) is not re-downloaded.
            latest = video.downloads.filter(status=DownloadStatus.COMPLETED).first()
            if latest:
                return latest, False
            raise AlreadyArchived(video)

        try:
            with transaction.atomic():
                download = Download.objects.create(video=video, total_bytes=estimated_size)
        except IntegrityError:
            return video.downloads.get(status__in=ACTIVE_STATUSES), False

        transaction.on_commit(lambda: self.enqueue(download.pk))
        return download, True

    def enqueue(self, download_id: int) -> None:
        try:
            self._enqueue(download_id)
        except Exception:
            # Reconciliation picks up queued downloads that were never enqueued.
            logger.exception("could not enqueue download %s", download_id)
            return
        Download.objects.filter(pk=download_id, status=DownloadStatus.QUEUED).update(
            enqueued_at=timezone.now()
        )

    # Execute ----------------------------------------------------------------------------

    def execute(self, download_id: int) -> None:
        """Run one attempt. Safe to call again: only a queued attempt is ever claimed."""
        now = timezone.now()
        claimed = Download.objects.filter(pk=download_id, status=DownloadStatus.QUEUED).update(
            status=DownloadStatus.DOWNLOADING,
            started_at=now,
            last_heartbeat_at=now,
            error_code="",
            error_message="",
            ytdlp_version=self.downloader.version[:32],
        )
        if not claimed:
            logger.info("download %s is not queued, nothing to do", download_id)
            return

        download = Download.objects.select_related("video", "video__channel").get(pk=download_id)
        logger.info("download %s started for video %s", download_id, download.video.platform_id)
        try:
            self._ensure_library()
            if self._recover_existing(download):
                return
            self._check_space(download)
            work_dir = self.storage.work_dir(download_id)
            reporter = ProgressReporter(download_id, estimated_total=download.total_bytes)
            with Heartbeat(Download, download_id, RUNNING_STATUSES):
                result = self.downloader.download(
                    download.video.source_url,
                    work_dir,
                    reporter.progress,
                    reporter.activity,
                    on_thumbnail=lambda path: self._publish_thumbnail(download, path),
                    # Merging can take a while without new bytes: it is not a stall.
                    on_processing=lambda: self._set_status(download_id, DownloadStatus.PROCESSING),
                )
                self._set_status(download_id, DownloadStatus.PROCESSING)
                self._finalize(download, result)
            logger.info("download %s completed", download_id)
        except EngineError as exc:
            self._fail(download_id, exc.code, exc.message)
        except StorageError as exc:
            self._fail(download_id, ErrorCode.STORAGE, str(exc))
        except OSError as exc:
            # Filesystem errors (e.g. the library vanished mid-transfer) are storage failures.
            self._fail(download_id, ErrorCode.STORAGE, str(exc))
        except Exception as exc:
            logger.exception("download %s failed unexpectedly", download_id)
            self._fail(download_id, ErrorCode.UNKNOWN, str(exc))
        finally:
            self.storage.remove_work_dir(download_id)

    def _ensure_library(self) -> None:
        """Before touching storage: set up a brand-new local library, or refuse to write."""
        info = prepare_for_write(self.storage)
        if not info.usable or not self.storage.is_available():
            message = info.message or str(MESSAGES[LibraryState.MISSING])
            raise EngineError(ErrorCode.STORAGE, message)

    def _recover_existing(self, download: Download) -> bool:
        """The registered file came back (e.g. the library folder was restored): no transfer."""
        video = download.video
        if not video.file_path or not video.checksum_sha256:
            return False
        try:
            path = self.storage.get_media_path(video.file_path)
            if self.storage.checksum(path) != video.checksum_sha256:
                return False
        except (OSError, StorageError):
            return False
        now = timezone.now()
        with transaction.atomic():
            updated = Download.objects.filter(pk=download.pk, status__in=RUNNING_STATUSES).update(
                status=DownloadStatus.COMPLETED,
                completed_at=now,
                progress=100.0,
                speed=None,
                eta=None,
                recovered_existing=True,
                target_path=video.file_path,
                checksum_sha256=video.checksum_sha256,
            )
            if updated:
                Video.objects.filter(pk=video.pk).update(local_status=LocalStatus.AVAILABLE)
                if video.probed_at is None:
                    video_id = video.pk
                    transaction.on_commit(lambda: self._notify_archived(video_id))
        logger.info("download %s: registered file found again, no transfer", download.pk)
        return True

    def _check_space(self, download: Download) -> None:
        estimated = int((download.total_bytes or 0) * SPACE_SAFETY_FACTOR)
        needed = estimated + settings.VHS_MIN_FREE_BYTES
        available = self.storage.available_space()
        if available < needed:
            raise EngineError(
                ErrorCode.STORAGE,
                gettext("Not enough space: {needed} MiB needed, {available} MiB available.").format(
                    needed=needed // 1024**2, available=available // 1024**2
                ),
            )

    def _basename(self, download: Download) -> PurePosixPath:
        """The path is decided once: a video already registered keeps its basename, whatever
        its current title or channel name (a new download never moves or orphans the file)."""
        if download.video.file_path:
            return PurePosixPath(download.video.file_path).with_suffix("")
        return build_basename(
            NamingTemplate(settings.VHS_NAMING_TEMPLATE), metadata_from_video(download.video)
        )

    def _publish_thumbnail(self, download: Download, path: Path) -> None:
        """Make the thumbnail visible while the media is still downloading (§22).

        A copy is promoted, so yt-dlp keeps its own file. Never fails the download.
        """
        try:
            early = path.with_name(f"{path.stem}.early{path.suffix}")
            shutil.copyfile(path, early)
            target = with_suffix(self._basename(download), ".webp")
            self.storage.finalize(early, target, replace=True)
            Video.objects.filter(pk=download.video_id).update(thumbnail_path=str(target))
        except (OSError, StorageError):
            logger.warning("could not publish the thumbnail of download %s early", download.pk)

    def _finalize(self, download: Download, result: DownloadResult) -> None:
        basename = self._basename(download)
        media_path = with_suffix(basename, result.media.suffix.lower())
        checksum = self.storage.checksum(result.media)
        Download.objects.filter(pk=download.pk).update(
            target_path=str(media_path), checksum_sha256=checksum, last_heartbeat_at=timezone.now()
        )

        # Sidecars first, media last: a registered media file always has its sidecars.
        sidecars = ((result.info_json, ".info.json"), (result.thumbnail, ".webp"))
        for sidecar, suffix in sidecars:
            if sidecar:
                self.storage.finalize(sidecar, with_suffix(basename, suffix), replace=True)
        self.storage.finalize(result.media, media_path)

        self._register(download.pk, media_path, checksum, result.info)

    def _register(
        self, download_id: int, media_path: PurePosixPath, checksum: str, info: dict
    ) -> None:
        """Mark the archived copy available, only after the file has been promoted."""
        now = timezone.now()
        details = describe_media(info, media_path.name)
        with transaction.atomic():
            download = Download.objects.select_for_update().get(pk=download_id)
            if download.status not in RUNNING_STATUSES:
                return
            video = Video.objects.select_for_update().get(pk=download.video_id)
            if video.file_path and video.file_path != str(media_path):
                # Recorded whether or not the old file exists now: it may reappear later.
                video.superseded_files = [
                    *(video.superseded_files or []),
                    {
                        "path": video.file_path,
                        "checksum_sha256": video.checksum_sha256,
                        "replaced_at": now.isoformat(),
                    },
                ]
            video.file_path = str(media_path)
            thumbnail = media_path.with_suffix(".webp")
            video.thumbnail_path = str(thumbnail) if self.storage.exists(thumbnail) else ""
            video.file_size = self.storage.size(media_path)
            video.checksum_sha256 = checksum
            video.container = details.container
            video.video_codec = details.video_codec
            video.audio_codec = details.audio_codec
            video.resolution = details.resolution
            platform = get_platform(video.platform)
            audio = platform.audio_track(downloaded_audio_format(info)) if platform else None
            video.audio_language = audio.language if audio else ""
            video.audio_kind = audio.kind if audio else ""
            video.downloaded_at = now
            video.acquired_at = video.acquired_at or now
            if info:
                video.source_metadata_snapshot = build_snapshot(info)
            video.local_status = LocalStatus.AVAILABLE
            video.source_status = SourceStatus.AVAILABLE
            # A newly registered file needs a fresh playback analysis and browser copy.
            video.media_probe = {}
            video.probed_at = None
            video.playback_action = PlaybackAction.NOT_ANALYZED
            video.playback_issues = []
            video.playback_reason = ""
            video.playback_path = ""
            video.save()

            download.status = DownloadStatus.COMPLETED
            download.completed_at = now
            download.progress = 100.0
            # The archived file is what this attempt produced (same checksum).
            download.total_bytes = download.downloaded_bytes = video.file_size
            download.speed = None
            download.eta = None
            download.save()
            video_id = video.pk
            transaction.on_commit(lambda: self._notify_archived(video_id))

    def _notify_archived(self, video_id: int) -> None:
        # A failed analysis must never affect the completed download.
        try:
            self._on_archived(video_id)
        except Exception:
            logger.exception("could not start the analysis of video %s", video_id)

    def _set_status(self, download_id: int, status: DownloadStatus) -> None:
        Download.objects.filter(pk=download_id, status__in=RUNNING_STATUSES).update(
            status=status, last_heartbeat_at=timezone.now(), speed=None, eta=None
        )

    def _fail(self, download_id: int, code: ErrorCode, message: str) -> None:
        logger.warning("download %s failed: %s", download_id, code)
        with transaction.atomic():
            updated = Download.objects.filter(pk=download_id, status__in=RUNNING_STATUSES).update(
                status=DownloadStatus.FAILED,
                error_code=str(code),
                error_message=sanitize_message(self.storage.redact_paths(message)),
                completed_at=timezone.now(),
                speed=None,
                eta=None,
            )
            # A temporary failure never marks the source as unavailable or deleted.
            if updated and code == ErrorCode.SOURCE_UNAVAILABLE:
                Video.objects.filter(downloads__pk=download_id).update(
                    source_status=SourceStatus.UNAVAILABLE
                )

    # Reconcile --------------------------------------------------------------------------

    def reconcile(self) -> dict[str, int | str]:
        """Recover from lost enqueues, crashed workers and leftover work directories."""
        if not self.storage.is_available():
            # Nothing can be verified or cleaned where the library is not.
            logger.warning("download reconciliation skipped: library not available")
            return {"skipped": "storage_unavailable"}
        # List work dirs before reading active downloads, so a newly started one is kept.
        work_dirs = self.storage.work_dir_ids()
        now = timezone.now()
        stats = {"requeued": 0, "recovered": 0, "interrupted": 0, "cleaned": 0}

        redelivery = timedelta(seconds=settings.Q_CLUSTER["retry"])
        lost = Download.objects.filter(status=DownloadStatus.QUEUED).filter(
            Q(enqueued_at__isnull=True, created_at__lt=now - ENQUEUE_GRACE)
            | Q(enqueued_at__lt=now - redelivery)
        )
        for download_id in lost.values_list("pk", flat=True):
            self.enqueue(download_id)
            stats["requeued"] += 1

        heartbeat_cutoff = now - timedelta(seconds=settings.VHS_HEARTBEAT_TIMEOUT_SECONDS)
        stale = Download.objects.filter(status__in=RUNNING_STATUSES).filter(
            Q(last_heartbeat_at__lt=heartbeat_cutoff) | Q(last_heartbeat_at__isnull=True)
        )
        for download in stale:
            if self._recover_promoted(download):
                stats["recovered"] += 1
            else:
                self._fail(download.pk, ErrorCode.INTERRUPTED, str(INTERRUPTED_MESSAGE))
                stats["interrupted"] += 1

        active = set(
            Download.objects.filter(status__in=ACTIVE_STATUSES).values_list("pk", flat=True)
        )
        for download_id in work_dirs - active:
            self.storage.remove_work_dir(download_id)
            stats["cleaned"] += 1

        if any(stats.values()):
            logger.info("reconciliation: %s", stats)
        return stats

    def _recover_promoted(self, download: Download) -> bool:
        """A crash after promotion leaves a complete, verified file: register it."""
        if not download.target_path or not download.checksum_sha256:
            return False
        media_path = PurePosixPath(download.target_path)
        try:
            if not self.storage.exists(media_path):
                return False
            if self.storage.checksum(self.storage.get_path(media_path)) != download.checksum_sha256:
                return False
            info = self._read_info_sidecar(media_path)
        except (OSError, StorageError):
            logger.exception("could not verify promoted file for download %s", download.pk)
            return False
        self._register(download.pk, media_path, download.checksum_sha256, info)
        logger.info("download %s recovered from an already promoted file", download.pk)
        return True

    def _read_info_sidecar(self, media_path: PurePosixPath) -> dict:
        sidecar = media_path.with_suffix(".info.json")
        if not self.storage.exists(sidecar):
            return {}
        try:
            return json.loads(self.storage.get_path(sidecar).read_text())
        except (OSError, ValueError):
            return {}


def metadata_from_video(video: Video) -> VideoMetadata:
    channel = None
    if video.channel:
        channel = ChannelMetadata(
            platform=video.channel.platform,
            platform_id=video.channel.platform_id,
            name=video.channel.name,
        )
    return VideoMetadata(
        platform=video.platform,
        platform_id=video.platform_id,
        title=video.title,
        source_url=video.source_url,
        upload_date=video.upload_date,
        channel=channel,
    )


class ProgressReporter:
    """Writes progress to the database with throttling (§20).

    The progress of the whole download, over all its streams: the percentage never goes
    back and stays below 100% until the file is archived. The total is the larger of the
    size estimated before starting (every selected format) and what the transfer reports
    (only the streams started so far).
    """

    def __init__(self, download_id: int, estimated_total: int | None = None):
        self.download_id = download_id
        self.estimated_total = estimated_total
        self.throttle = settings.VHS_PROGRESS_THROTTLE_SECONDS
        self._last_write = 0.0
        self._last_bytes = -1
        self._percent = 0.0

    def progress(self, progress: Progress) -> None:
        now = time.monotonic()
        if now - self._last_write < self.throttle:
            return
        self._last_write = now

        downloaded = progress.downloaded_bytes
        total = max(self.estimated_total or 0, progress.total_bytes or 0) or None
        timestamp = timezone.now()
        fields = {
            "downloaded_bytes": downloaded,
            "speed": progress.speed,
            "eta": self._eta(total, downloaded, progress.speed),
            "last_heartbeat_at": timestamp,
        }
        if total:
            fields["total_bytes"] = total
            if downloaded is not None:
                percent = min(MAX_TRANSFER_PERCENT, 100.0 * downloaded / total)
                self._percent = max(self._percent, percent)
                fields["progress"] = self._percent
        downloaded = downloaded or 0
        if downloaded > self._last_bytes:
            self._last_bytes = downloaded
            fields["last_progress_at"] = timestamp
        Download.objects.filter(pk=self.download_id, status__in=RUNNING_STATUSES).update(**fields)

    def _eta(self, total: int | None, downloaded: int | None, speed: float | None) -> int | None:
        """Estimated remaining time of the whole download, at the current speed. The ETA
        yt-dlp reports covers only the current stream, and the reported total only the
        streams started so far: only a total estimated before starting covers them all."""
        if not self.estimated_total or not total or downloaded is None or not speed:
            return None
        return max(0, round((total - downloaded) / speed))

    def activity(self) -> None:
        now = time.monotonic()
        if now - self._last_write < self.throttle:
            return
        self._last_write = now
        Download.objects.filter(pk=self.download_id, status__in=RUNNING_STATUSES).update(
            last_heartbeat_at=timezone.now()
        )
