from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.video import Video


class DownloadStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    DOWNLOADING = "downloading", _("Downloading")
    PROCESSING = "processing", _("Processing")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


ACTIVE_STATUSES = (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING)
RUNNING_STATUSES = (DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING)
RETRYABLE_STATUSES = (DownloadStatus.FAILED, DownloadStatus.CANCELLED)


class Download(models.Model):
    """One attempt to obtain a local copy of a Video. Attempts are kept as history."""

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="downloads")
    status = models.CharField(
        max_length=16, choices=DownloadStatus.choices, default=DownloadStatus.QUEUED
    )
    progress = models.FloatField(null=True, blank=True)
    downloaded_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    total_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    eta = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)
    # Version of the download tool that ran this attempt (empty for attempts made before
    # VHS 0.1.1): a failed download says which yt-dlp it failed with.
    ytdlp_version = models.CharField(max_length=32, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    enqueued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_progress_at = models.DateTimeField(null=True, blank=True)

    # Written before promotion so recovery can recognize an already finalized file.
    target_path = models.CharField(max_length=1024, blank=True)
    # The registered file came back (e.g. the library folder was restored): completed
    # without a transfer.
    recovered_existing = models.BooleanField(default=False)
    checksum_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["video"],
                condition=models.Q(status__in=ACTIVE_STATUSES),
                name="one_active_download_per_video",
            )
        ]
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"Download #{self.pk} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_stalled(self) -> bool:
        """Running, but no real progress for a while (the worker may still be alive)."""
        if self.status != DownloadStatus.DOWNLOADING:
            return False
        reference = self.last_progress_at or self.started_at
        if reference is None:
            return False
        threshold = timedelta(seconds=settings.VHS_DOWNLOAD_STALL_SECONDS)
        return timezone.now() - reference > threshold
