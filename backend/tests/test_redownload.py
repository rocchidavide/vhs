"""A new download never orphans the main file (Phase 3, block 1)."""

import hashlib
from pathlib import PurePosixPath

import pytest

from core.models import Download, DownloadStatus, LocalStatus, Video
from engine.errors import ErrorCode
from services import library_service as lib
from services.download_service import AlreadyArchived
from tests.conftest import fetch_csrf_token, login

pytestmark = pytest.mark.django_db

URL = "https://youtu.be/jNQXAC9IVRw"
OLD_BASENAME = "youtube/jawed/2005-04-24 - Old title [jNQXAC9IVRw]"
NEW_TITLE_PATH = "youtube/jawed/2005-04-24 - Me at the zoo [jNQXAC9IVRw].mp4"


def registered_video(storage, suffix=".mp4", content=b"old-archived-copy", present=False, **fields):
    path = f"{OLD_BASENAME}{suffix}"
    if present:
        target = storage.get_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    defaults = {
        "platform": "youtube",
        "platform_id": "jNQXAC9IVRw",
        "title": "Old title",
        "source_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "file_path": path,
        "checksum_sha256": hashlib.sha256(content).hexdigest(),
        "local_status": LocalStatus.MISSING,
    }
    return Video.objects.create(**(defaults | fields))


def run(service, url=URL):
    download, _ = service.request(url)
    service.execute(download.pk)
    download.refresh_from_db()
    return download


# Guard on the state of the file ----------------------------------------------------------


def test_archived_video_without_completed_attempt_is_not_downloaded_again(service, storage):
    registered_video(storage, present=True, local_status=LocalStatus.AVAILABLE)

    with pytest.raises(AlreadyArchived):
        service.request(URL)
    assert Download.objects.count() == 0


def test_api_answers_409_already_archived(csrf_client, admin_user, service, storage):
    from unittest import mock

    video = registered_video(storage, present=True, local_status=LocalStatus.AVAILABLE)
    login(csrf_client, "admin")
    token = fetch_csrf_token(csrf_client)

    with mock.patch("api.downloads.DownloadService", return_value=service):
        response = csrf_client.post(
            "/api/v1/downloads/",
            {"url": URL},
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "already_archived"
    assert response.json()["video_id"] == video.pk


def test_retry_of_an_archived_video_is_refused(service, storage):
    video = registered_video(storage, present=True, local_status=LocalStatus.AVAILABLE)
    failed = Download.objects.create(video=video, status=DownloadStatus.FAILED)

    with pytest.raises(AlreadyArchived):
        service.retry(failed.pk)


# Same path on a new download --------------------------------------------------------------


def test_new_download_reuses_the_registered_path_despite_a_new_title(
    service, storage, fake_downloader
):
    video = registered_video(storage)

    download = run(service)

    video.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    assert video.title == "Me at the zoo"
    assert video.file_path == f"{OLD_BASENAME}.mp4"
    assert video.thumbnail_path == f"{OLD_BASENAME}.webp"
    assert storage.exists(f"{OLD_BASENAME}.info.json")
    assert not storage.get_path(NEW_TITLE_PATH).exists()
    assert video.superseded_files == []


def test_registered_file_back_before_the_download_is_recovered_without_transfer(
    service, storage, fake_downloader
):
    video = registered_video(storage, present=True)

    download = run(service)

    video.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    assert download.recovered_existing is True
    assert fake_downloader.download_calls == []
    assert video.local_status == LocalStatus.AVAILABLE
    assert storage.get_path(video.file_path).read_bytes() == b"old-archived-copy"


def test_a_different_file_at_the_registered_path_is_never_overwritten(
    service, storage, fake_downloader
):
    registered_video(storage, present=True, checksum_sha256="0" * 64)

    download = run(service)

    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert storage.get_path(f"{OLD_BASENAME}.mp4").read_bytes() == b"old-archived-copy"
    assert Video.objects.get().local_status == LocalStatus.MISSING


# Different extension: the old path is always recorded --------------------------------------


@pytest.mark.parametrize("present", [True, False], ids=["old-file-present", "old-file-absent"])
def test_extension_change_records_the_superseded_file(service, storage, present):
    video = registered_video(storage, suffix=".mkv", present=present, checksum_sha256="c" * 64)
    if present:
        # Present but not identical to the registered copy: no recovery, a real new download.
        storage.get_path(f"{OLD_BASENAME}.mkv").write_bytes(b"something else")

    download = run(service)

    video.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    assert video.file_path == f"{OLD_BASENAME}.mp4"
    assert [entry["path"] for entry in video.superseded_files] == [f"{OLD_BASENAME}.mkv"]
    assert video.superseded_files[0]["checksum_sha256"] == "c" * 64
    assert storage.get_path(f"{OLD_BASENAME}.mkv").exists() is present


def test_old_file_reappearing_after_the_new_path_is_registered_stays_tracked(service, storage):
    video = registered_video(storage, suffix=".mkv")
    run(service)

    # The storage comes back later with the old file.
    old = storage.get_path(f"{OLD_BASENAME}.mkv")
    old.write_bytes(b"old-archived-copy")

    video.refresh_from_db()
    assert video.file_path == f"{OLD_BASENAME}.mp4"
    assert old.read_bytes() == b"old-archived-copy"
    assert f"{OLD_BASENAME}.mkv" in lib.tracked_paths()
    assert str(PurePosixPath(video.file_path)) in lib.tracked_paths()


def test_missing_can_be_marked_only_with_the_library_available(storage, tmp_path):
    from storage import FilesystemStorage

    assert lib.can_mark_missing(storage) is True
    empty = tmp_path / "mnt"
    empty.mkdir()
    assert lib.can_mark_missing(FilesystemStorage(empty)) is False
