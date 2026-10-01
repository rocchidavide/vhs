"""Per-user playback position (§13)."""

import math

from core.models import PlaybackProgress, Video


def get_progress(user, video: Video) -> PlaybackProgress | None:
    return PlaybackProgress.objects.filter(user=user, video=video).first()


def save_progress(
    user, video: Video, position_seconds: float, duration: float | None = None
) -> PlaybackProgress:
    if not math.isfinite(position_seconds) or position_seconds < 0:
        raise ValueError("position_seconds must be a finite, non-negative number")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        duration = None
    limit = duration or video.duration
    if limit:
        position_seconds = min(position_seconds, float(limit))
    progress, _ = PlaybackProgress.objects.update_or_create(
        user=user,
        video=video,
        defaults={"position_seconds": position_seconds, "duration": duration},
    )
    return progress
