from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.channel import Channel


class LocalStatus(models.TextChoices):
    ABSENT = "absent", _("Absent")
    AVAILABLE = "available", _("Available")
    MISSING = "missing", _("Missing")


class SourceStatus(models.TextChoices):
    UNKNOWN = "unknown", _("Unknown")
    AVAILABLE = "available", _("Available")
    UNAVAILABLE = "unavailable", _("Unavailable")
    DELETED = "deleted", _("Deleted")


class PlaybackAction(models.TextChoices):
    """What the archived file needs to play in a browser, decided by ffprobe (§18)."""

    NOT_ANALYZED = "", _("Not analyzed")
    NATIVE = "native", _("Playable")
    REMUX = "remux", _("Container change")
    TRANSCODE = "transcode", _("Conversion")
    UNSUPPORTED = "unsupported", _("Unsupported")


class Video(models.Model):
    """Content known to VHS. Not a download attempt (see Download)."""

    # A key of engine.platforms, checked by the services: no choices, so that a new platform
    # needs no migration.
    platform = models.CharField(max_length=32)
    platform_id = models.CharField(max_length=128)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(max_length=2048, blank=True)
    source_url = models.URLField(max_length=2048)
    upload_date = models.DateField(null=True, blank=True)
    channel = models.ForeignKey(
        Channel, null=True, blank=True, on_delete=models.SET_NULL, related_name="videos"
    )
    platform_metadata = models.JSONField(default=dict, blank=True)

    # Archived copy and provenance. Paths are relative to VHS_MEDIA_ROOT.
    file_path = models.CharField(max_length=1024, blank=True)
    playback_path = models.CharField(max_length=1024, blank=True)
    thumbnail_path = models.CharField(max_length=1024, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    container = models.CharField(max_length=32, blank=True)
    video_codec = models.CharField(max_length=64, blank=True)
    audio_codec = models.CharField(max_length=64, blank=True)
    resolution = models.CharField(max_length=32, blank=True)
    # The audio track of the archived copy (engine.audio): BCP 47 language and AudioKind, ""
    # when unknown (videos archived before VHS recorded them).
    audio_language = models.CharField(max_length=35, blank=True)
    audio_kind = models.CharField(max_length=16, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    acquired_at = models.DateTimeField(null=True, blank=True)
    source_metadata_snapshot = models.JSONField(default=dict, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    # Previous main files replaced by a new download with a different path (e.g. another
    # extension): kept on record, whether or not the file exists, so it is never lost.
    superseded_files = models.JSONField(default=list, blank=True)

    # Browser playback, from ffprobe on the archived file. Never affects local_status.
    media_probe = models.JSONField(default=dict, blank=True)
    probed_at = models.DateTimeField(null=True, blank=True)
    playback_action = models.CharField(
        max_length=16,
        choices=PlaybackAction.choices,
        default=PlaybackAction.NOT_ANALYZED,
        blank=True,
    )
    # Why direct playback is not possible: stable codes and parameters the UI translates,
    # e.g. [{"code": "video_codec", "codec": "VP9"}]. Replaced by every analysis.
    playback_issues = models.JSONField(default=list, blank=True)
    # English diagnostic detail (older rows may hold Italian text).
    playback_reason = models.CharField(max_length=500, blank=True)

    local_status = models.CharField(
        max_length=16, choices=LocalStatus.choices, default=LocalStatus.ABSENT
    )
    source_status = models.CharField(
        max_length=16, choices=SourceStatus.choices, default=SourceStatus.UNKNOWN
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "platform_id"], name="unique_video_per_platform"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} [{self.platform_id}]"
