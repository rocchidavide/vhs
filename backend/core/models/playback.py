from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.video import Video


class PlaybackProgress(models.Model):
    """Where a user stopped watching a video (§13). Independent of the streaming system."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="playback_progress"
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="playback_progress")
    position_seconds = models.FloatField(default=0)
    duration = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "video"], name="one_progress_per_user_video")
        ]

    def __str__(self):
        return f"{self.user} @ {self.video_id}: {self.position_seconds:.0f}s"


class PreparationKind(models.TextChoices):
    REMUX = "remux", _("Container change")
    TRANSCODE = "transcode", _("Conversion")


class PreparationStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    RUNNING = "running", _("Running")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


ACTIVE_PREPARATION_STATUSES = (PreparationStatus.QUEUED, PreparationStatus.RUNNING)


class PlaybackPreparation(models.Model):
    """One attempt to build the browser copy of a video. The original is never modified."""

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="preparations")
    kind = models.CharField(max_length=16, choices=PreparationKind.choices)
    status = models.CharField(
        max_length=16, choices=PreparationStatus.choices, default=PreparationStatus.QUEUED
    )
    progress = models.FloatField(null=True, blank=True)
    error_code = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    enqueued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["video"],
                condition=models.Q(status__in=ACTIVE_PREPARATION_STATUSES),
                name="one_active_preparation_per_video",
            )
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Preparation #{self.pk} ({self.kind}, {self.status})"
