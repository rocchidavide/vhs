"""Library availability: nothing is written where the library is not found (Phase 3).

Directories are real (tmp_path).
"""

import os
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from core.models import Download, DownloadStatus, LocalStatus, PlaybackPreparation, Video
from engine.errors import ErrorCode
from services import library_service as lib
from services.download_service import DownloadService
from services.playback_service import PlaybackService
from storage import FilesystemStorage, StorageUnavailable
from storage.filesystem import MARKER_NAME
from tests.conftest import RecordingEnqueue, ago

pytestmark = pytest.mark.django_db

URL = "https://youtu.be/jNQXAC9IVRw"


def listing(path: Path) -> list[str]:
    """Everything under path, relative (empty list for an empty or missing directory)."""
    if not path.exists():
        return []
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


def archived_video(platform_id="old", file_path="youtube/x/old [old].mp4", **fields):
    defaults = {
        "platform": "youtube",
        "title": "Old",
        "source_url": f"https://www.youtube.com/watch?v={platform_id}",
        "local_status": LocalStatus.AVAILABLE,
    }
    return Video.objects.create(platform_id=platform_id, file_path=file_path, **(defaults | fields))


def download_service(storage, fake_downloader):
    return DownloadService(
        downloader=fake_downloader,
        storage=storage,
        enqueue=RecordingEnqueue(),
        on_archived=RecordingEnqueue(),
    )


# Local mode: brand-new library ----------------------------------------------------------


def test_new_local_library_is_created_on_the_first_download(media_root, fake_downloader):
    storage = FilesystemStorage(media_root)
    service = download_service(storage, fake_downloader)
    assert lib.library_state(storage).state == lib.LibraryState.NEW

    download, _ = service.request(URL)
    service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    assert (media_root / MARKER_NAME).is_file()


def test_health_check_and_reconciliation_never_initialize(client, media_root):
    storage = FilesystemStorage(media_root)
    media_root.mkdir()

    client.get("/api/v1/health")
    call_command("check")
    DownloadService(storage=storage, enqueue=RecordingEnqueue()).reconcile()
    PlaybackService(storage=storage).reconcile()

    assert listing(media_root) == []
    assert lib.library_state(storage).state == lib.LibraryState.NEW


# Local mode: populated library that disappeared ------------------------------------------


@pytest.mark.parametrize("root_exists", [True, False], ids=["empty-dir", "no-dir"])
def test_populated_local_library_that_disappeared_is_blocked(
    media_root, fake_downloader, root_exists
):
    if root_exists:
        media_root.mkdir()
    archived_video()
    storage = FilesystemStorage(media_root)
    service = download_service(storage, fake_downloader)

    assert lib.library_state(storage).state == lib.LibraryState.MISSING
    download, _ = service.request(URL)
    service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert "Library not found" in download.error_message
    assert fake_downloader.download_calls == []
    assert listing(media_root) == []
    assert media_root.exists() == root_exists  # never created


def test_non_empty_folder_without_marker_needs_explicit_init(media_root, fake_downloader):
    archived_video(file_path="youtube/x/old [old].mp4")
    existing = media_root / "youtube" / "x" / "old [old].mp4"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"archived")
    storage = FilesystemStorage(media_root)
    service = download_service(storage, fake_downloader)

    assert lib.library_state(storage).state == lib.LibraryState.NOT_INITIALIZED
    download, _ = service.request(URL)
    service.execute(download.pk)
    assert Download.objects.get(pk=download.pk).error_code == ErrorCode.STORAGE
    assert listing(media_root) == ["youtube", "youtube/x", "youtube/x/old [old].mp4"]

    call_command("init_library")

    assert (media_root / MARKER_NAME).is_file()
    assert lib.library_state(storage).state == lib.LibraryState.OK


def test_init_library_refusals(media_root):
    with pytest.raises(CommandError, match="does not exist"):
        call_command("init_library")

    media_root.mkdir()
    with pytest.raises(CommandError, match="is empty"):
        call_command("init_library")

    archived_video()
    with pytest.raises(CommandError, match="No option overrides"):
        call_command("init_library", "--allow-empty")
    assert listing(media_root) == []


def test_init_library_is_idempotent(storage):
    call_command("init_library")
    call_command("init_library")

    assert (Path(storage.root) / MARKER_NAME).is_file()


# Storage never writes without a library ---------------------------------------------------


def test_storage_refuses_every_write_without_marker(tmp_path):
    root = tmp_path / "mnt"
    root.mkdir()
    storage = FilesystemStorage(root)
    src = tmp_path / "video.mp4"
    src.write_bytes(b"x")

    with pytest.raises(StorageUnavailable):
        storage.work_dir(1)
    with pytest.raises(StorageUnavailable):
        storage.finalize(src, "youtube/x/video.mp4")
    with pytest.raises(StorageUnavailable):
        storage.delete("youtube/x/video.mp4")
    storage.remove_work_dir(1)
    assert storage.work_dir_names() == set()
    assert listing(root) == []


def test_available_space_never_creates_the_root(tmp_path):
    storage = FilesystemStorage(tmp_path / "absent")

    with pytest.raises(StorageUnavailable):
        storage.available_space()
    assert not (tmp_path / "absent").exists()


# Startup ---------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["missing", "not_initialized"])
def test_startup_check_warns_without_writing(tmp_path, case):
    from core.checks import library_available_check

    root = tmp_path / "library"
    root.mkdir()
    if case == "missing":
        archived_video()
    else:
        (root / "something").write_text("x")
    before = listing(root)

    with override_settings(VHS_MEDIA_ROOT=root):
        warnings = library_available_check(None)

    assert [w.id for w in warnings] == ["vhs.W002"]
    assert case in warnings[0].msg
    assert listing(root) == before


# Preparations and streaming --------------------------------------------------------------


def test_preparation_fails_without_writing_when_the_library_is_missing(media_root):
    media_root.mkdir()
    video = archived_video(file_path="youtube/x/v [v].mkv", playback_action="transcode")
    preparation = PlaybackPreparation.objects.create(video=video, kind="transcode")
    service = PlaybackService(storage=FilesystemStorage(media_root))

    service.execute(preparation.pk)

    preparation.refresh_from_db()
    assert preparation.status == "failed"
    assert preparation.error_code == ErrorCode.STORAGE
    assert listing(media_root) == []


def test_stream_and_thumbnail_answer_503(client, admin_user, media_root):
    media_root.mkdir()
    video = archived_video(thumbnail_path="youtube/x/old [old].webp", playback_action="native")
    client.force_login(admin_user)

    stream = client.get(f"/api/v1/videos/{video.pk}/stream")
    thumbnail = client.get(f"/api/v1/videos/{video.pk}/thumbnail")

    assert (stream.status_code, stream.json()["code"]) == (503, "storage_unavailable")
    assert thumbnail.status_code == 503
    assert "X-Accel-Redirect" not in stream


# Library disappearing during a download --------------------------------------------------


def replace_library_during_transfer(media_root, moved, recreate_work_dir, work_name):
    def replace():
        # The library goes away (folder moved, disk disconnected): an empty directory is
        # left at the configured path.
        os.rename(media_root, moved)
        media_root.mkdir()
        if recreate_work_dir:
            # yt-dlp creates missing output directories by itself (makedirs).
            (media_root / ".incomplete" / work_name).mkdir(parents=True)

    return replace


def test_library_disappearing_when_writes_fail_leaves_nothing(
    tmp_path, media_root, storage, fake_downloader
):
    service = download_service(storage, fake_downloader)
    download, _ = service.request(URL)
    moved = tmp_path / "library-moved-away"
    fake_downloader.on_thumbnail_probe = replace_library_during_transfer(
        media_root, moved, recreate_work_dir=False, work_name=str(download.pk)
    )

    service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert listing(media_root) == []
    assert (moved / MARKER_NAME).is_file()

    # Reconciliation waits for the library to come back before acting.
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.DOWNLOADING, last_heartbeat_at=ago(minutes=30)
    )
    assert service.reconcile() == {"skipped": "storage_unavailable"}
    assert Download.objects.get(pk=download.pk).status == DownloadStatus.DOWNLOADING

    media_root.rmdir()
    os.rename(moved, media_root)
    assert service.reconcile()["interrupted"] == 1


def test_library_disappearing_when_the_downloader_recreates_its_directory(
    tmp_path, media_root, storage, fake_downloader
):
    """Documented limit: a transfer already running can write temporary files where the
    library was; the check before promotion keeps them out of the library and the DB."""
    service = download_service(storage, fake_downloader)
    download, _ = service.request(URL)
    moved = tmp_path / "library-moved-away"
    fake_downloader.on_thumbnail_probe = replace_library_during_transfer(
        media_root, moved, recreate_work_dir=True, work_name=str(download.pk)
    )

    service.execute(download.pk)

    download.refresh_from_db()
    video = Video.objects.get(pk=download.video_id)
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert video.local_status == LocalStatus.ABSENT
    assert video.file_path == ""
    # Nothing was promoted: only the transfer's temporary files, never a library file.
    assert all(path.startswith(".incomplete") for path in listing(media_root))
    assert not (media_root / MARKER_NAME).exists()
