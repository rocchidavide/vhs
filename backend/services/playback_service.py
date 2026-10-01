"""Browser playback: analysis with ffprobe, automatic remux, transcode on request (§18, §24)."""

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from core.models import (
    ACTIVE_PREPARATION_STATUSES,
    LocalStatus,
    PlaybackAction,
    PlaybackPreparation,
    PreparationKind,
    PreparationStatus,
    Video,
)
from engine.errors import EngineError, ErrorCode, sanitize_message
from engine.media import ffmpeg
from engine.media.compat import plan_playback
from engine.media.probe import MediaProbe, probe
from services.dependencies import get_storage
from services.jobs import Heartbeat, enqueue_task, touch
from services.library_service import MESSAGES, LibraryState, prepare_for_write
from storage import Storage, StorageError

logger = logging.getLogger("vhs.playback")

ANALYZE_TASK = "tasks.playback.analyze_task"
PLAYBACK_TASK = "tasks.playback.playback_task"
# Browser copies live in a separate tree, so a media server scanning the library only sees
# the archived originals (a video keeps a single file in its channel folder).
DERIVED_ROOT = ".browser"
WORK_DIR_PREFIX = "prep-"
SPACE_FACTOR = {PreparationKind.REMUX: 1.2, PreparationKind.TRANSCODE: 1.5}
ENQUEUE_GRACE = timedelta(seconds=60)
ANALYSIS_BATCH = 100
INTERRUPTED_MESSAGE = gettext_lazy(
    "The preparation was interrupted: the worker was restarted or is not responding."
)
# Issue code of a failed analysis (the others come from engine.media.compat.IssueCode).
ANALYSIS_FAILED = "analysis_failed"
NOT_ARCHIVED = "not_archived"


class PlaybackStatus:
    READY = "ready"
    PREPARING = "preparing"
    UNAVAILABLE = "unavailable"


class InvalidPlaybackState(Exception):
    """The requested playback operation is not allowed for this video."""


@dataclass(frozen=True)
class PlaybackState:
    status: str
    source: str | None
    action: str
    # Stable codes for the UI message, and an English diagnostic detail.
    issues: list[dict]
    reason: str
    can_prepare: bool
    preparation: PlaybackPreparation | None


def enqueue_analysis(video_id: int) -> None:
    enqueue_task(ANALYZE_TASK, video_id, task_name=f"analyze-{video_id}")


def enqueue_preparation(preparation_id: int) -> None:
    enqueue_task(PLAYBACK_TASK, preparation_id, task_name=f"playback-{preparation_id}")


def derived_path(file_path: str) -> PurePosixPath:
    """The browser copy mirrors the original's path under .browser/, as an MP4 (§17, §18)."""
    return PurePosixPath(DERIVED_ROOT, *PurePosixPath(file_path).with_suffix(".mp4").parts)


def ready_q() -> Q:
    return ~Q(playback_path="") | Q(playback_action=PlaybackAction.NATIVE)


def with_active_preparation(queryset: QuerySet) -> QuerySet:
    active = PlaybackPreparation.objects.filter(
        video=OuterRef("pk"), status__in=ACTIVE_PREPARATION_STATUSES
    )
    return queryset.annotate(has_active_preparation=Exists(active))


def filter_by_playback_status(queryset: QuerySet, status: str) -> QuerySet:
    """Same rules as PlaybackService.state, as a query (expects with_active_preparation)."""
    available = Q(local_status=LocalStatus.AVAILABLE)
    preparing = Q(has_active_preparation=True) | Q(
        playback_action=PlaybackAction.NOT_ANALYZED, probed_at__isnull=True
    )
    if status == PlaybackStatus.READY:
        return queryset.filter(available & ready_q())
    if status == PlaybackStatus.PREPARING:
        return queryset.filter(available & preparing).exclude(ready_q())
    return queryset.exclude(available & (ready_q() | preparing))


class PlaybackService:
    def __init__(
        self,
        storage: Storage | None = None,
        prober=probe,
        runner=ffmpeg.run,
        enqueue_preparation=enqueue_preparation,
        enqueue_analysis=enqueue_analysis,
    ):
        self.storage = storage or get_storage()
        self._probe = prober
        self._run = runner
        self._enqueue_preparation = enqueue_preparation
        self._enqueue_analysis = enqueue_analysis

    # State ------------------------------------------------------------------------------

    def state(self, video: Video) -> PlaybackState:
        latest = video.preparations.first()
        active = latest if latest and latest.status in ACTIVE_PREPARATION_STATUSES else None
        action = video.playback_action

        issues = list(video.playback_issues or [])
        if video.local_status != LocalStatus.AVAILABLE:
            return PlaybackState(
                PlaybackStatus.UNAVAILABLE,
                None,
                action,
                [{"code": NOT_ARCHIVED}],
                gettext("The video is not archived."),
                False,
                latest,
            )
        if video.playback_path:
            return PlaybackState(PlaybackStatus.READY, "derived", action, [], "", False, latest)
        if action == PlaybackAction.NATIVE:
            return PlaybackState(PlaybackStatus.READY, "original", action, [], "", False, latest)
        if active or (action == PlaybackAction.NOT_ANALYZED and video.probed_at is None):
            return PlaybackState(
                PlaybackStatus.PREPARING, None, action, issues, video.playback_reason, False, latest
            )
        return PlaybackState(
            PlaybackStatus.UNAVAILABLE,
            None,
            action,
            issues,
            video.playback_reason,
            action == PlaybackAction.TRANSCODE,
            latest,
        )

    # Analysis ---------------------------------------------------------------------------

    def analyze(self, video_id: int) -> Video | None:
        """Probe the archived file and decide what the browser needs. Never fails the video."""
        video = Video.objects.filter(pk=video_id).first()
        if video is None or video.local_status != LocalStatus.AVAILABLE or not video.file_path:
            return None
        try:
            media = self._probe_file(video.file_path)
        except (EngineError, StorageError) as exc:
            logger.warning("analysis of video %s failed: %s", video_id, exc)
            message = exc.message if isinstance(exc, EngineError) else str(exc)
            Video.objects.filter(pk=video_id).update(
                probed_at=timezone.now(),
                playback_action=PlaybackAction.NOT_ANALYZED,
                playback_issues=[{"code": ANALYSIS_FAILED}],
                playback_reason=sanitize_message(
                    self.storage.redact_paths(f"File analysis failed: {message}")
                )[:500],
            )
            return None

        plan = plan_playback(media)
        with transaction.atomic():
            video = Video.objects.select_for_update().get(pk=video_id)
            video.media_probe = media.to_dict()
            video.probed_at = timezone.now()
            video.playback_action = plan.action
            # Replaced, never appended: issues of an earlier analysis must not linger.
            video.playback_issues = list(plan.issues)
            video.playback_reason = plan.reason[:500]
            video.video_codec = media.video.codec if media.video else ""
            video.audio_codec = media.audio.codec if media.audio else ""
            video.resolution = media.resolution or video.resolution
            video.save()
            if plan.action == PlaybackAction.REMUX and not video.playback_path:
                self._create_preparation(video, PreparationKind.REMUX)
        logger.info("video %s analyzed: %s", video_id, plan.action)
        return video

    def _probe_file(self, relative_path: str) -> MediaProbe:
        path = self.storage.get_media_path(relative_path)
        return self._probe(path, timeout=settings.VHS_MEDIA_TOOL_TIMEOUT)

    # Preparations -----------------------------------------------------------------------

    def request_transcode(self, video_id: int) -> tuple[PlaybackPreparation, bool]:
        """Start the conversion the user asked for; only when re-encoding is really needed."""
        with transaction.atomic():
            video = Video.objects.select_for_update().get(pk=video_id)
            active = video.preparations.filter(status__in=ACTIVE_PREPARATION_STATUSES).first()
            if active:
                return active, False
            if video.local_status != LocalStatus.AVAILABLE:
                raise InvalidPlaybackState(gettext("The video is not archived."))
            if video.playback_path:
                raise InvalidPlaybackState(gettext("The browser copy is already ready."))
            if video.playback_action != PlaybackAction.TRANSCODE:
                raise InvalidPlaybackState(gettext("This video does not need a conversion."))
            return self._create_preparation(video, PreparationKind.TRANSCODE)

    def _create_preparation(
        self, video: Video, kind: PreparationKind
    ) -> tuple[PlaybackPreparation, bool]:
        try:
            with transaction.atomic():
                preparation = PlaybackPreparation.objects.create(video=video, kind=kind)
        except IntegrityError:
            return video.preparations.get(status__in=ACTIVE_PREPARATION_STATUSES), False
        transaction.on_commit(lambda: self.enqueue(preparation.pk))
        return preparation, True

    def enqueue(self, preparation_id: int) -> None:
        try:
            self._enqueue_preparation(preparation_id)
        except Exception:
            logger.exception("could not enqueue preparation %s", preparation_id)
            return
        PlaybackPreparation.objects.filter(
            pk=preparation_id, status=PreparationStatus.QUEUED
        ).update(enqueued_at=timezone.now())

    def execute(self, preparation_id: int) -> None:
        """Build the browser copy. Safe to call again: only a queued attempt is claimed."""
        now = timezone.now()
        claimed = PlaybackPreparation.objects.filter(
            pk=preparation_id, status=PreparationStatus.QUEUED
        ).update(
            status=PreparationStatus.RUNNING,
            started_at=now,
            last_heartbeat_at=now,
            error_code="",
            error_message="",
        )
        if not claimed:
            logger.info("preparation %s is not queued, nothing to do", preparation_id)
            return

        preparation = PlaybackPreparation.objects.select_related("video").get(pk=preparation_id)
        work_name = f"{WORK_DIR_PREFIX}{preparation_id}"
        logger.info("preparation %s started (%s)", preparation_id, preparation.kind)
        try:
            info = prepare_for_write(self.storage)
            if not info.usable or not self.storage.is_available():
                message = info.message or str(MESSAGES[LibraryState.MISSING])
                raise EngineError(ErrorCode.STORAGE, message)
            self._build(preparation, work_name)
            logger.info("preparation %s completed", preparation_id)
        except EngineError as exc:
            self._fail(preparation_id, exc.code, exc.message)
        except StorageError as exc:
            self._fail(preparation_id, ErrorCode.STORAGE, str(exc))
        except Exception as exc:
            logger.exception("preparation %s failed unexpectedly", preparation_id)
            self._fail(preparation_id, ErrorCode.UNKNOWN, str(exc))
        finally:
            self.storage.remove_work_dir(work_name)

    def _build(self, preparation: PlaybackPreparation, work_name: str) -> None:
        video = preparation.video
        source = self.storage.get_media_path(video.file_path)
        media = self._probe(source, timeout=settings.VHS_MEDIA_TOOL_TIMEOUT)
        plan = plan_playback(media)
        if plan.action not in (PlaybackAction.REMUX, PlaybackAction.TRANSCODE):
            raise EngineError(
                ErrorCode.PROCESSING, gettext("The file does not need a browser copy.")
            )
        if preparation.kind == PreparationKind.REMUX and plan.needs_encoding:
            raise EngineError(ErrorCode.PROCESSING, gettext("The file needs a full conversion."))

        self._check_space(source.stat().st_size, preparation.kind)
        output = self.storage.work_dir(work_name) / "browser.mp4"
        options = ffmpeg.EncodeOptions(
            preset=settings.VHS_TRANSCODE_PRESET,
            crf=settings.VHS_TRANSCODE_CRF,
            audio_bitrate=settings.VHS_TRANSCODE_AUDIO_BITRATE,
            threads=settings.VHS_FFMPEG_THREADS,
        )
        reporter = PreparationProgress(preparation.pk)
        with Heartbeat(PlaybackPreparation, preparation.pk, (PreparationStatus.RUNNING,)):
            self._run(
                ffmpeg.build_command(source, output, plan, options),
                media.duration,
                reporter.progress,
                reporter.activity,
                settings.VHS_MEDIA_TOOL_TIMEOUT,
            )
            result = self._probe(output, timeout=settings.VHS_MEDIA_TOOL_TIMEOUT)
            if plan_playback(result).action != PlaybackAction.NATIVE:
                raise EngineError(
                    ErrorCode.PROCESSING,
                    gettext("The generated copy cannot be played in the browser."),
                )
            target = derived_path(video.file_path)
            # A browser copy is regenerable: replacing it never touches the original.
            self.storage.finalize(output, target, replace=True)

        with transaction.atomic():
            updated = PlaybackPreparation.objects.filter(
                pk=preparation.pk, status=PreparationStatus.RUNNING
            ).update(status=PreparationStatus.COMPLETED, completed_at=timezone.now(), progress=100)
            if updated:
                Video.objects.filter(pk=video.pk).update(playback_path=str(target))

    def _check_space(self, source_size: int, kind: str) -> None:
        needed = int(source_size * SPACE_FACTOR[kind]) + settings.VHS_MIN_FREE_BYTES
        available = self.storage.available_space()
        if available < needed:
            raise EngineError(
                ErrorCode.STORAGE,
                gettext("Not enough space: {needed} MiB needed, {available} MiB available.").format(
                    needed=needed // 1024**2, available=available // 1024**2
                ),
            )

    def _fail(self, preparation_id: int, code: ErrorCode, message: str) -> None:
        # The archived video stays valid: only the preparation attempt fails.
        logger.warning("preparation %s failed: %s", preparation_id, code)
        PlaybackPreparation.objects.filter(
            pk=preparation_id, status=PreparationStatus.RUNNING
        ).update(
            status=PreparationStatus.FAILED,
            error_code=str(code),
            error_message=sanitize_message(self.storage.redact_paths(message)),
            completed_at=timezone.now(),
        )

    # Reconcile --------------------------------------------------------------------------

    def reconcile(self) -> dict[str, int | str]:
        if not self.storage.is_available():
            logger.warning("playback reconciliation skipped: library not available")
            return {"skipped": "storage_unavailable"}
        work_dirs = {
            name for name in self.storage.work_dir_names() if name.startswith(WORK_DIR_PREFIX)
        }
        now = timezone.now()
        stats = {"requeued": 0, "interrupted": 0, "analysis_queued": 0, "cleaned": 0}

        redelivery = timedelta(seconds=settings.Q_CLUSTER["retry"])
        lost = PlaybackPreparation.objects.filter(status=PreparationStatus.QUEUED).filter(
            Q(enqueued_at__isnull=True, created_at__lt=now - ENQUEUE_GRACE)
            | Q(enqueued_at__lt=now - redelivery)
        )
        for preparation_id in lost.values_list("pk", flat=True):
            self.enqueue(preparation_id)
            stats["requeued"] += 1

        cutoff = now - timedelta(seconds=settings.VHS_HEARTBEAT_TIMEOUT_SECONDS)
        stale = PlaybackPreparation.objects.filter(status=PreparationStatus.RUNNING).filter(
            Q(last_heartbeat_at__lt=cutoff) | Q(last_heartbeat_at__isnull=True)
        )
        for preparation_id in stale.values_list("pk", flat=True):
            self._fail(preparation_id, ErrorCode.INTERRUPTED, str(INTERRUPTED_MESSAGE))
            stats["interrupted"] += 1

        pending = (
            Video.objects.filter(local_status=LocalStatus.AVAILABLE, probed_at__isnull=True)
            .exclude(file_path="")
            .values_list("pk", flat=True)[:ANALYSIS_BATCH]
        )
        for video_id in pending:
            self._enqueue_analysis(video_id)
            stats["analysis_queued"] += 1

        active = {
            f"{WORK_DIR_PREFIX}{pk}"
            for pk in PlaybackPreparation.objects.filter(
                status__in=ACTIVE_PREPARATION_STATUSES
            ).values_list("pk", flat=True)
        }
        for name in work_dirs - active:
            self.storage.remove_work_dir(name)
            stats["cleaned"] += 1

        if any(stats.values()):
            logger.info("playback reconciliation: %s", stats)
        return stats


class PreparationProgress:
    """Throttled progress writes for a running preparation."""

    def __init__(self, preparation_id: int):
        self.preparation_id = preparation_id
        self.throttle = settings.VHS_PROGRESS_THROTTLE_SECONDS
        self._last_write = 0.0

    def _due(self) -> bool:
        now = time.monotonic()
        if now - self._last_write < self.throttle:
            return False
        self._last_write = now
        return True

    def progress(self, percent: float) -> None:
        if self._due():
            touch(
                PlaybackPreparation,
                self.preparation_id,
                (PreparationStatus.RUNNING,),
                progress=round(percent, 1),
            )

    def activity(self) -> None:
        if self._due():
            touch(PlaybackPreparation, self.preparation_id, (PreparationStatus.RUNNING,))
