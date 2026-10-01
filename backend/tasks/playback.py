"""Thin django-q2 adapters around PlaybackService."""

from services.playback_service import PlaybackService


def analyze_task(video_id: int) -> None:
    PlaybackService().analyze(video_id)


def playback_task(preparation_id: int) -> None:
    PlaybackService().execute(preparation_id)
