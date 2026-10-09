from pathlib import PurePosixPath
from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from core.models import Download, DownloadStatus, LocalStatus, SourceStatus, Video
from engine.downloader.base import Progress
from engine.errors import EngineError, ErrorCode
from services.download_service import InvalidDownloadState, ProgressReporter
from storage import StorageError
from tests.conftest import ago, raiplay_info, youtube_info

URL = "https://youtu.be/jNQXAC9IVRw"
MEDIA = PurePosixPath("youtube/jawed/2005-04-24 - Me at the zoo [jNQXAC9IVRw].mp4")

pytestmark = pytest.mark.django_db


def request(service, django_capture_on_commit_callbacks, url=URL):
    with django_capture_on_commit_callbacks(execute=True):
        return service.request(url)


# Request --------------------------------------------------------------------------------


def test_request_creates_video_channel_and_queued_download(
    service, enqueue, fake_downloader, django_capture_on_commit_callbacks
):
    download, created = request(service, django_capture_on_commit_callbacks)

    assert created
    assert download.status == DownloadStatus.QUEUED
    assert fake_downloader.extract_calls == ["https://www.youtube.com/watch?v=jNQXAC9IVRw"]
    video = download.video
    assert (video.platform, video.platform_id) == ("youtube", "jNQXAC9IVRw")
    assert video.channel.name == "jawed"
    assert video.local_status == LocalStatus.ABSENT
    assert video.source_status == SourceStatus.AVAILABLE
    assert download.total_bytes == 433081 + 309288
    assert enqueue.calls == [download.pk]
    download.refresh_from_db()
    assert download.enqueued_at is not None


def test_enqueue_happens_only_after_commit(service, enqueue):
    with transaction.atomic():
        service.request(URL)
        assert enqueue.calls == []


def test_different_urls_of_the_same_video_are_deduplicated(
    service, enqueue, django_capture_on_commit_callbacks
):
    first, created_first = request(service, django_capture_on_commit_callbacks)
    second, created_second = request(
        service,
        django_capture_on_commit_callbacks,
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=10",
    )

    assert created_first and not created_second
    assert first.pk == second.pk
    assert Video.objects.count() == 1
    assert enqueue.calls == [first.pk]


def test_database_allows_a_single_active_download_per_video(service):
    download, _ = service.request(URL)

    with pytest.raises(IntegrityError), transaction.atomic():
        Download.objects.create(video=download.video)


def test_concurrent_creation_returns_the_existing_active_download(service):
    existing, _ = service.request(URL)

    # Simulate a racing request that did not see the active attempt yet.
    with mock.patch("django.db.models.query.QuerySet.first", return_value=None):
        download, created = service.request(URL)

    assert not created
    assert download.pk == existing.pk


def test_request_rejects_unsupported_urls_without_network(service, fake_downloader):
    with pytest.raises(EngineError) as excinfo:
        service.request("http://192.168.1.1/admin")

    assert excinfo.value.code == ErrorCode.UNSUPPORTED_URL
    assert fake_downloader.extract_calls == []


def test_request_propagates_source_errors(service, fake_downloader):
    fake_downloader.extract_error = EngineError(ErrorCode.SOURCE_UNAVAILABLE, "Private video")

    with pytest.raises(EngineError):
        service.request(URL)

    assert not Video.objects.exists()


def test_request_for_an_archived_video_returns_the_completed_download(
    service, enqueue, fake_downloader
):
    download, _ = service.request(URL)
    service.execute(download.pk)

    again, created = service.request(URL)

    assert not created
    assert again.pk == download.pk
    assert len(fake_downloader.download_calls) == 1


# Execute --------------------------------------------------------------------------------


def test_execute_archives_the_file(service, storage, fake_downloader):
    download, _ = service.request(URL)

    service.execute(download.pk)

    download.refresh_from_db()
    video = download.video
    assert download.status == DownloadStatus.COMPLETED
    assert download.progress == 100.0
    assert download.completed_at is not None
    assert download.last_progress_at is not None
    assert video.local_status == LocalStatus.AVAILABLE
    # Each attempt records the version of the download tool that ran it.
    assert download.ytdlp_version == fake_downloader.version
    # The size of the archived file, not the estimate made before downloading.
    assert video.file_size == len(fake_downloader.content)
    assert download.total_bytes == download.downloaded_bytes == video.file_size
    assert video.file_path == str(MEDIA)
    assert video.file_size == len(fake_downloader.content)
    assert video.checksum_sha256 == storage.checksum(storage.get_path(MEDIA))
    assert video.checksum_sha256 == download.checksum_sha256
    assert (video.container, video.video_codec, video.audio_codec) == (
        "mp4",
        "avc1.4d400c",
        "mp4a.40.2",
    )
    assert video.acquired_at is not None
    assert video.source_metadata_snapshot["id"] == "jNQXAC9IVRw"
    assert "formats" not in video.source_metadata_snapshot
    assert storage.exists(MEDIA.with_suffix(".info.json"))
    assert storage.exists(MEDIA.with_suffix(".webp"))
    assert video.thumbnail_path == str(MEDIA.with_suffix(".webp"))
    assert storage.work_dir_ids() == set()


def test_execute_is_idempotent(service, fake_downloader):
    download, _ = service.request(URL)

    service.execute(download.pk)
    service.execute(download.pk)

    assert len(fake_downloader.download_calls) == 1


def test_execute_skips_a_download_that_is_already_running(service, fake_downloader):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(status=DownloadStatus.DOWNLOADING)

    service.execute(download.pk)

    assert fake_downloader.download_calls == []
    download.refresh_from_db()
    assert download.status == DownloadStatus.DOWNLOADING


def test_insufficient_space_fails_before_downloading(service, storage, fake_downloader):
    download, _ = service.request(URL)

    with mock.patch.object(storage, "available_space", return_value=1024):
        service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert download.error_code == ErrorCode.STORAGE
    assert "Not enough space" in download.error_message
    assert fake_downloader.download_calls == []


def test_source_error_marks_the_source_unavailable(service, fake_downloader):
    download, _ = service.request(URL)
    fake_downloader.download_error = EngineError(
        ErrorCode.SOURCE_UNAVAILABLE, "Private video https://x.example/v?sig=SECRET"
    )

    service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.SOURCE_UNAVAILABLE
    assert "SECRET" not in download.error_message
    assert download.video.source_status == SourceStatus.UNAVAILABLE
    assert download.video.local_status == LocalStatus.ABSENT


def test_network_error_does_not_change_the_source_status(service, fake_downloader, storage):
    download, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "HTTP Error 503")

    service.execute(download.pk)

    download.refresh_from_db()
    assert download.error_code == ErrorCode.NETWORK
    assert download.video.source_status == SourceStatus.AVAILABLE
    assert storage.work_dir_ids() == set()


def test_storage_failure_during_finalize(service, storage):
    download, _ = service.request(URL)

    with mock.patch.object(storage, "finalize", side_effect=StorageError("disk gone")):
        service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.STORAGE
    assert download.video.local_status == LocalStatus.ABSENT
    assert storage.work_dir_ids() == set()


def test_unexpected_errors_are_categorized_as_unknown(service, fake_downloader):
    download, _ = service.request(URL)
    fake_downloader.download_error = RuntimeError("boom")

    service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.FAILED
    assert download.error_code == ErrorCode.UNKNOWN


# Retry ----------------------------------------------------------------------------------


def test_retry_creates_a_new_attempt_and_keeps_history(
    service, fake_downloader, enqueue, django_capture_on_commit_callbacks
):
    failed, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")
    service.execute(failed.pk)
    fake_downloader.download_error = None

    with django_capture_on_commit_callbacks(execute=True):
        retry, created = service.retry(failed.pk)
    service.execute(retry.pk)

    assert created and retry.pk != failed.pk
    assert enqueue.calls[-1] == retry.pk
    failed.refresh_from_db()
    retry.refresh_from_db()
    assert failed.status == DownloadStatus.FAILED
    assert retry.status == DownloadStatus.COMPLETED
    assert failed.video.downloads.count() == 2


def failed_attempt(service, fake_downloader):
    failed, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")
    service.execute(failed.pk)
    fake_downloader.download_error = None
    return failed


def test_retry_estimates_the_size_from_the_current_formats(
    service, fake_downloader, django_capture_on_commit_callbacks
):
    failed = failed_attempt(service, fake_downloader)
    # The source now offers other formats: the old size does not apply.
    current = youtube_info(requested_formats=[{"filesize": 7_000_000}, {"filesize": 3_000_000}])

    with mock.patch.object(fake_downloader, "extract_info", return_value=current):
        retry, _ = service.retry(failed.pk)

    assert retry.total_bytes == 10_000_000


def test_retry_falls_back_to_the_previous_size_when_the_source_cannot_be_asked(
    service, fake_downloader
):
    failed = failed_attempt(service, fake_downloader)
    failed.refresh_from_db()
    fake_downloader.extract_error = EngineError(ErrorCode.NETWORK, "timed out")

    retry, created = service.retry(failed.pk)

    assert created
    assert retry.total_bytes == failed.total_bytes == 433081 + 309288


def test_retry_is_refused_for_completed_downloads(service):
    download, _ = service.request(URL)
    service.execute(download.pk)

    with pytest.raises(InvalidDownloadState):
        service.retry(download.pk)


def test_retry_returns_the_attempt_already_active(service, fake_downloader):
    failed, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")
    service.execute(failed.pk)
    active, _ = service.retry(failed.pk)

    again, created = service.retry(failed.pk)

    assert not created
    assert again.pk == active.pk


# Progress -------------------------------------------------------------------------------


def running(service, estimated_total=None):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(status=DownloadStatus.DOWNLOADING)
    return download, ProgressReporter(download.pk, estimated_total=estimated_total)


def test_progress_is_recorded(service):
    download, reporter = running(service, estimated_total=100)

    reporter.progress(Progress(downloaded_bytes=25, total_bytes=100, speed=5.0, stream_eta=3))

    download.refresh_from_db()
    assert download.progress == 25.0
    assert (download.speed, download.total_bytes) == (5.0, 100)
    # From the whole estimated size and the speed, not the ETA of the current stream.
    assert download.eta == 15
    assert download.last_progress_at is not None

    first_progress_at = download.last_progress_at
    reporter.progress(Progress(downloaded_bytes=25, total_bytes=100))
    download.refresh_from_db()
    assert download.last_progress_at == first_progress_at
    assert download.last_heartbeat_at > first_progress_at


def test_video_then_audio_progress_moves_forward_only(service):
    from engine.downloader.ytdlp import StreamProgress
    from tests.test_engine_ytdlp import two_streams

    estimate = 433080 + 309287  # filesize_approx of the two formats: one byte short each
    download, reporter = running(service, estimated_total=estimate)
    streams = StreamProgress()

    recorded = []
    for data in two_streams():
        if data["status"] == "downloading":
            reporter.progress(streams.update(data))
            download.refresh_from_db()
            recorded.append((download.progress, download.total_bytes, download.eta))
        else:
            streams.update(data)

    percents = [percent for percent, _, _ in recorded]
    assert percents == sorted(percents), "the bar never goes back at the audio stream"
    assert percents[1] < 60, "the end of the video stream is not the end of the download"
    assert max(percents) == 99.0, "100% only once the file is archived"
    assert {total for _, total, _ in recorded} <= {estimate, 433081 + 309288}
    # The overall ETA: at the end of the video stream the audio is still to come.
    assert recorded[1][2] > 0


def test_eta_is_unknown_without_an_estimate_of_the_whole_download(service):
    download, reporter = running(service, estimated_total=None)

    reporter.progress(Progress(downloaded_bytes=50, total_bytes=100, speed=10.0, stream_eta=5))

    download.refresh_from_db()
    assert download.eta is None
    assert download.progress == 50.0


def test_the_audio_stream_is_progress_not_a_stall(service, settings):
    settings.VHS_DOWNLOAD_STALL_SECONDS = 60
    download, reporter = running(service, estimated_total=1000)
    reporter.progress(Progress(downloaded_bytes=600, total_bytes=600))
    Download.objects.filter(pk=download.pk).update(last_progress_at=ago(minutes=5))

    # The audio starts: its own bytes start from zero, the whole download goes on.
    reporter.progress(Progress(downloaded_bytes=610, total_bytes=1000))

    download.refresh_from_db()
    assert not download.is_stalled


def test_merging_is_processing_not_a_stall(service, fake_downloader, settings):
    settings.VHS_DOWNLOAD_STALL_SECONDS = 60
    download, _ = service.request(URL)
    during_merge = {}
    original = fake_downloader.download

    def download_and_merge(url, work_dir, on_progress, on_activity, **callbacks):
        result = original(url, work_dir, on_progress, on_activity, **callbacks)
        callbacks["on_processing"]()
        # A long merge: no new bytes for longer than the stall threshold.
        Download.objects.filter(pk=download.pk).update(last_progress_at=ago(minutes=5))
        during_merge["download"] = Download.objects.get(pk=download.pk)
        return result

    with mock.patch.object(fake_downloader, "download", side_effect=download_and_merge):
        service.execute(download.pk)

    merged = during_merge["download"]
    assert merged.status == DownloadStatus.PROCESSING
    assert merged.progress < 100
    assert not merged.is_stalled
    download.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    assert download.progress == 100.0


def test_video_metadata_is_refreshed_on_new_requests(service):
    service.request(URL)

    with mock.patch.object(
        service.downloader, "extract_info", return_value=youtube_info(title="Nuovo titolo")
    ):
        service.request(URL)

    assert Video.objects.get().title == "Nuovo titolo"


# Early thumbnail ------------------------------------------------------------------------


def test_thumbnail_is_published_while_the_media_downloads(service, storage, fake_downloader):
    download, _ = service.request(URL)

    def snapshot():
        video = Video.objects.get(pk=download.video_id)
        current = Download.objects.get(pk=download.pk)
        return current.status, video.thumbnail_path, storage.exists(video.thumbnail_path)

    fake_downloader.on_thumbnail_probe = snapshot

    service.execute(download.pk)

    status, thumbnail_path, exists = fake_downloader.thumbnail_seen_during_download
    assert status == DownloadStatus.DOWNLOADING
    assert thumbnail_path == str(MEDIA.with_suffix(".webp"))
    assert exists
    assert Video.objects.get(pk=download.video_id).thumbnail_path == thumbnail_path


def test_thumbnail_stays_when_the_download_fails(service, storage, fake_downloader):
    download, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")

    service.execute(download.pk)

    video = Video.objects.get(pk=download.video_id)
    assert video.local_status == LocalStatus.ABSENT
    assert video.thumbnail_path == str(MEDIA.with_suffix(".webp"))
    assert storage.exists(video.thumbnail_path)
    assert storage.work_dir_ids() == set()


def test_early_thumbnail_failure_never_fails_the_download(service, storage):
    download, _ = service.request(URL)

    with mock.patch("services.download_service.shutil.copyfile", side_effect=OSError("disk")):
        service.execute(download.pk)

    download.refresh_from_db()
    assert download.status == DownloadStatus.COMPLETED
    # The sidecar promoted at the end still provides the thumbnail.
    assert download.video.thumbnail_path == str(MEDIA.with_suffix(".webp"))


# History correction (migration 0008) ----------------------------------------------------


def test_history_correction_touches_only_attempts_tied_to_the_current_file(service):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("core.migrations.0008_downloads_real_size")
    download, _ = service.request(URL)
    service.execute(download.pk)
    video = Video.objects.get(pk=download.video_id)
    # The bug: only the last stream was recorded.
    Download.objects.filter(pk=download.pk).update(total_bytes=3, downloaded_bytes=3)
    other = {"video": video, "status": DownloadStatus.COMPLETED, "total_bytes": 3}
    recovered = Download.objects.create(
        **other, recovered_existing=True, checksum_sha256=video.checksum_sha256,
        target_path=video.file_path,
    )  # fmt: skip
    replaced = Download.objects.create(
        **other, checksum_sha256="0" * 64, target_path=video.file_path
    )
    moved = Download.objects.create(
        **other, checksum_sha256=video.checksum_sha256, target_path="youtube/old.mp4"
    )

    migration.correct_sizes(apps, None)

    download.refresh_from_db()
    assert download.total_bytes == download.downloaded_bytes == video.file_size
    for ambiguous in (recovered, replaced, moved):
        ambiguous.refresh_from_db()
        assert ambiguous.total_bytes == 3


# Platforms and audio tracks -------------------------------------------------------------------

RAIPLAY_URL = "https://www.raiplay.it/video/2021/11/Blanca-S1E1-Senza-occhi-b1255a4a-8e72-4a2f-b9f3-fc1308e00736.html"


def test_a_raiplay_video_is_archived_under_its_series(service, storage, fake_downloader):
    fake_downloader.info_for = lambda url: raiplay_info()

    download, _ = service.request(RAIPLAY_URL)
    service.execute(download.pk)

    video = Video.objects.get()
    assert (video.platform, video.platform_id) == (
        "raiplay",
        "b1255a4a-8e72-4a2f-b9f3-fc1308e00736",
    )
    assert (video.channel.platform, video.channel.name) == ("raiplay", "Blanca")
    assert video.platform_metadata["network"] == "Rai Premium"
    assert video.file_path.startswith("raiplay/Blanca/2021-11-19 - Blanca - S1E1 - Senza occhi [")
    # The Italian track of the fixture's requested formats.
    assert (video.audio_language, video.audio_kind) == ("it", "default")


def test_the_downloaded_audio_track_is_recorded(service, storage, fake_downloader):
    requested = [
        {"format_id": "137", "vcodec": "avc1", "acodec": "none"},
        {
            "format_id": "140",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "language": "en",
            "language_preference": 10,
        },
    ]
    fake_downloader.info_for = lambda url: youtube_info(requested_formats=requested)

    download, _ = service.request(URL)
    service.execute(download.pk)

    video = Video.objects.get()
    assert (video.audio_language, video.audio_kind) == ("en", "original")


def test_an_unknown_audio_track_is_recorded_as_unknown(service, storage, fake_downloader):
    download, _ = service.request(URL)
    service.execute(download.pk)

    video = Video.objects.get()
    assert (video.audio_language, video.audio_kind) == ("", "")
