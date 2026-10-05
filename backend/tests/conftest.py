import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from engine.downloader.base import BaseDownloader, DownloadResult, Progress
from engine.errors import EngineError
from storage import FilesystemStorage

PASSWORD = "correct-horse-battery"


@pytest.fixture
def admin_user(db):
    return get_user_model().objects.create_superuser("admin", "admin@example.com", PASSWORD)


@pytest.fixture
def regular_user(db):
    return get_user_model().objects.create_user("guest", "guest@example.com", PASSWORD)


@pytest.fixture
def csrf_client():
    """Client that enforces CSRF checks like a real browser."""
    return Client(enforce_csrf_checks=True)


def fetch_csrf_token(client: Client) -> str:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 204
    return response.cookies["csrftoken"].value


def login(client: Client, username: str, password: str = PASSWORD):
    token = fetch_csrf_token(client)
    return client.post(
        "/api/v1/auth/login",
        {"username": username, "password": password},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


# Download pipeline ------------------------------------------------------------------------


FIXTURES = Path(__file__).parent / "fixtures"


def youtube_info(video_id: str = "jNQXAC9IVRw", **overrides) -> dict:
    info = json.loads((FIXTURES / "youtube_video.json").read_text())
    if video_id != info["id"]:
        info |= {
            "id": video_id,
            "title": f"Video {video_id}",
            "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        }
    return info | overrides


class FakeDownloader(BaseDownloader):
    """Deterministic downloader: writes small files into the work dir."""

    def __init__(self):
        self.extract_calls: list[str] = []
        self.download_calls: list[str] = []
        self.extract_error: EngineError | None = None
        self.download_error: Exception | None = None
        self.content = b"fake-video-content"
        # Hook for tests to inspect state right after the early thumbnail callback.
        self.on_thumbnail_probe = lambda: None
        self.thumbnail_seen_during_download = None

    @property
    def version(self) -> str:
        return "2026.1.2-test"

    def extract_info(self, url: str) -> dict:
        self.extract_calls.append(url)
        if self.extract_error:
            raise self.extract_error
        return youtube_info(url.rsplit("v=", 1)[-1])

    def download(
        self, url, work_dir, on_progress, on_activity, on_thumbnail=None, on_processing=None
    ) -> DownloadResult:
        self.download_calls.append(url)
        video_id = url.rsplit("v=", 1)[-1]
        thumbnail = work_dir / f"{video_id}.webp"
        thumbnail.write_bytes(b"thumbnail")
        if on_thumbnail:
            on_thumbnail(thumbnail)
            self.thumbnail_seen_during_download = self.on_thumbnail_probe()
        on_progress(Progress(downloaded_bytes=0, total_bytes=len(self.content)))
        if self.download_error:
            (work_dir / f"{video_id}.mp4.part").write_bytes(b"partial")
            raise self.download_error
        media = work_dir / f"{video_id}.mp4"
        media.write_bytes(self.content)
        info_json = work_dir / f"{video_id}.info.json"
        info = youtube_info(video_id)
        info_json.write_text(json.dumps(info))
        on_progress(Progress(downloaded_bytes=len(self.content), total_bytes=len(self.content)))
        on_activity()
        return DownloadResult(media=media, info_json=info_json, thumbnail=thumbnail, info=info)


class RecordingEnqueue:
    def __init__(self):
        self.calls: list[int] = []

    def __call__(self, download_id: int) -> None:
        self.calls.append(download_id)


@pytest.fixture
def media_root(tmp_path):
    root = tmp_path / "library"
    with override_settings(
        VHS_MEDIA_ROOT=root,
        VHS_MIN_FREE_BYTES=0,
        VHS_HEARTBEAT_INTERVAL_SECONDS=3600,
        VHS_PROGRESS_THROTTLE_SECONDS=0,
    ):
        yield root


@pytest.fixture
def fake_downloader():
    return FakeDownloader()


@pytest.fixture
def storage(media_root):
    """An initialized library (root and .vhs-library marker)."""
    library = FilesystemStorage(media_root)
    library.create_marker(create_root=True)
    return library


@pytest.fixture
def enqueue():
    return RecordingEnqueue()


@pytest.fixture
def analysis_queue():
    return RecordingEnqueue()


@pytest.fixture
def service(fake_downloader, storage, enqueue, analysis_queue):
    from services.download_service import DownloadService

    return DownloadService(
        downloader=fake_downloader, storage=storage, enqueue=enqueue, on_archived=analysis_queue
    )


def ago(**kwargs):
    from django.utils import timezone

    return timezone.now() - timedelta(**kwargs)
