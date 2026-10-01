"""Thin django-q2 adapters around DownloadService."""

from services.download_service import DownloadService
from services.playback_service import PlaybackService


def download_task(download_id: int) -> None:
    DownloadService().execute(download_id)


def reconcile_task() -> dict[str, dict[str, int]]:
    return {
        "downloads": DownloadService().reconcile(),
        "playback": PlaybackService().reconcile(),
    }
