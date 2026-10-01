import json
from pathlib import PurePosixPath

import pytest

from core.models import Download, DownloadStatus, LocalStatus
from engine.errors import ErrorCode
from tests.conftest import ago, youtube_info

URL = "https://youtu.be/jNQXAC9IVRw"

pytestmark = pytest.mark.django_db


def test_queued_downloads_that_were_never_enqueued_are_requeued(service, enqueue):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(created_at=ago(minutes=5), enqueued_at=None)

    stats = service.reconcile()

    assert stats["requeued"] == 1
    assert enqueue.calls == [download.pk]


def test_recent_queued_downloads_are_left_alone(service, enqueue):
    service.request(URL)

    assert service.reconcile()["requeued"] == 0
    assert enqueue.calls == []


def test_stale_running_downloads_are_marked_interrupted(service, storage):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.DOWNLOADING, last_heartbeat_at=ago(minutes=30)
    )
    (storage.work_dir(download.pk) / "x.part").write_bytes(b"partial")

    stats = service.reconcile()

    download.refresh_from_db()
    assert stats["interrupted"] == 1
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.INTERRUPTED
    assert storage.work_dir_ids() == set()


def test_running_downloads_with_a_fresh_heartbeat_are_kept(service, storage):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.DOWNLOADING, last_heartbeat_at=ago(seconds=10)
    )
    storage.work_dir(download.pk)

    service.reconcile()

    download.refresh_from_db()
    assert download.status == DownloadStatus.DOWNLOADING
    assert storage.work_dir_ids() == {download.pk}


def test_crash_after_promotion_is_recovered(service, storage):
    download, _ = service.request(URL)
    media = PurePosixPath("youtube/jawed/2005-04-24 - Me at the zoo [jNQXAC9IVRw].mp4")
    work_dir = storage.work_dir(download.pk)
    (work_dir / "m.mp4").write_bytes(b"complete-copy")
    (work_dir / "m.info.json").write_text(json.dumps(youtube_info()))
    checksum = storage.checksum(work_dir / "m.mp4")
    storage.finalize(work_dir / "m.info.json", media.with_suffix(".info.json"))
    storage.finalize(work_dir / "m.mp4", media)
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.PROCESSING,
        last_heartbeat_at=ago(minutes=30),
        target_path=str(media),
        checksum_sha256=checksum,
    )

    stats = service.reconcile()

    download.refresh_from_db()
    video = download.video
    assert stats["recovered"] == 1
    assert download.status == DownloadStatus.COMPLETED
    assert video.local_status == LocalStatus.AVAILABLE
    assert video.file_path == str(media)
    assert video.checksum_sha256 == checksum
    assert video.video_codec == "avc1.4d400c"
    assert video.thumbnail_path == ""
    assert video.source_metadata_snapshot["id"] == "jNQXAC9IVRw"


def test_promoted_file_with_wrong_checksum_is_not_registered(service, storage):
    download, _ = service.request(URL)
    media = PurePosixPath("youtube/jawed/x [jNQXAC9IVRw].mp4")
    src = storage.work_dir(download.pk) / "m.mp4"
    src.write_bytes(b"truncated")
    storage.finalize(src, media)
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.PROCESSING,
        last_heartbeat_at=ago(minutes=30),
        target_path=str(media),
        checksum_sha256="0" * 64,
    )

    service.reconcile()

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.video.local_status == LocalStatus.ABSENT


def test_orphan_work_directories_are_removed(service, storage):
    download, _ = service.request(URL)
    storage.work_dir(download.pk)
    storage.work_dir(9999)

    stats = service.reconcile()

    assert stats["cleaned"] == 1
    assert storage.work_dir_ids() == {download.pk}
