"""Which archived file may be served for a video, as a path relative to the library."""

from pathlib import PurePosixPath

from django.utils.translation import gettext

from core.models import LocalStatus, PlaybackAction, Video
from services.dependencies import get_storage
from storage import Storage, StorageError


class MediaUnavailable(Exception):
    """No servable local copy for this video."""

    def __init__(self, message: str, code: str = "media_unavailable"):
        super().__init__(message)
        self.code = code


class MediaService:
    def __init__(self, storage: Storage | None = None):
        self.storage = storage or get_storage()

    def _require_library(self) -> None:
        if not self.storage.is_available():
            raise MediaUnavailable(gettext("The library is not available."), "storage_unavailable")

    def stream_path(self, video: Video) -> PurePosixPath:
        """The browser copy when present, otherwise the archived file only if playable (§24).

        A video not analyzed yet is served as is, so it can be watched right after download.
        """
        self._require_library()
        if video.local_status != LocalStatus.AVAILABLE:
            raise MediaUnavailable(gettext("The video is not archived."))
        if video.playback_path:
            relative = video.playback_path
        elif video.playback_action == PlaybackAction.NATIVE or (
            video.playback_action == PlaybackAction.NOT_ANALYZED and video.probed_at is None
        ):
            relative = video.file_path
        else:
            raise MediaUnavailable(
                gettext("The video cannot be played in the browser."), "not_playable"
            )
        if not relative:
            raise MediaUnavailable(gettext("The video has no file."))
        try:
            self.storage.get_media_path(relative)
        except StorageError as exc:
            raise MediaUnavailable(gettext("The video file is not available.")) from exc
        return PurePosixPath(relative)

    def thumbnail_path(self, video: Video) -> PurePosixPath:
        """The archived thumbnail; the source thumbnail_url is never proxied."""
        self._require_library()
        if not video.thumbnail_path:
            raise MediaUnavailable(gettext("The video has no archived thumbnail."))
        try:
            self.storage.get_media_path(video.thumbnail_path)
        except StorageError as exc:
            raise MediaUnavailable(gettext("The thumbnail is not available.")) from exc
        return PurePosixPath(video.thumbnail_path)
