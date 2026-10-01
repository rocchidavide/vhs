from pathlib import PurePosixPath
from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from core.models import (
    LocalStatus,
    PlaybackAction,
    PlaybackPreparation,
    PreparationKind,
    PreparationStatus,
    Video,
)
from engine.errors import EngineError, ErrorCode
from engine.media.probe import AudioStream, MediaProbe, VideoStream
from services.media_service import MediaService, MediaUnavailable
from services.playback_service import (
    InvalidPlaybackState,
    PlaybackService,
    PlaybackStatus,
    derived_path,
)
from tests.conftest import RecordingEnqueue, ago

pytestmark = pytest.mark.django_db

H264 = VideoStream("h264", pix_fmt="yuv420p")
NATIVE = MediaProbe(("mov", "mp4"), 10.0, H264, AudioStream("aac"))
MKV = MediaProbe(("matroska", "webm"), 10.0, H264, AudioStream("aac"))
VP9 = MediaProbe(
    ("matroska", "webm"), 10.0, VideoStream("vp9", pix_fmt="yuv420p"), AudioStream("opus")
)


class FakeProber:
    """Returns the probe configured for the archived file; outputs probe as native."""

    def __init__(self, source: MediaProbe, output: MediaProbe = NATIVE):
        self.source = source
        self.output = output
        self.calls = []

    def __call__(self, path, timeout=None):
        self.calls.append(path)
        return self.output if path.name == "browser.mp4" else self.source


class FakeRunner:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.commands = []

    def __call__(self, command, duration, on_progress, on_activity, timeout):
        self.commands.append(command)
        on_progress(50.0)
        on_activity()
        if self.error:
            raise self.error
        with open(command[-1], "wb") as handle:
            handle.write(b"browser-copy")


@pytest.fixture
def original(storage):
    path = PurePosixPath("youtube/Canale/2024-01-01 - Video [abc].mkv")
    target = storage.get_path(path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original-archived-bytes")
    return path


@pytest.fixture
def video(original):
    return Video.objects.create(
        platform="youtube",
        platform_id="abc",
        title="Video",
        source_url="https://www.youtube.com/watch?v=abc",
        file_path=str(original),
        local_status=LocalStatus.AVAILABLE,
    )


@pytest.fixture
def queues():
    return {"preparation": RecordingEnqueue(), "analysis": RecordingEnqueue()}


def make_service(storage, queues, prober, runner=None):
    return PlaybackService(
        storage=storage,
        prober=prober,
        runner=runner or FakeRunner(),
        enqueue_preparation=queues["preparation"],
        enqueue_analysis=queues["analysis"],
    )


def analyze(service, video, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        return service.analyze(video.pk)


# Analysis -------------------------------------------------------------------------------


def test_native_video_is_ready_with_the_original(
    storage, queues, video, django_capture_on_commit_callbacks
):
    service = make_service(storage, queues, FakeProber(NATIVE))

    analyze(service, video, django_capture_on_commit_callbacks)

    video.refresh_from_db()
    assert video.playback_action == PlaybackAction.NATIVE
    assert (video.video_codec, video.audio_codec) == ("h264", "aac")
    assert video.media_probe["format_names"] == ["mov", "mp4"]
    assert not video.preparations.exists()
    state = service.state(video)
    assert (state.status, state.source) == (PlaybackStatus.READY, "original")


def test_container_change_starts_an_automatic_remux(
    storage, queues, video, django_capture_on_commit_callbacks
):
    service = make_service(storage, queues, FakeProber(MKV))

    analyze(service, video, django_capture_on_commit_callbacks)

    preparation = video.preparations.get()
    assert preparation.kind == PreparationKind.REMUX
    assert queues["preparation"].calls == [preparation.pk]
    assert service.state(Video.objects.get(pk=video.pk)).status == PlaybackStatus.PREPARING


def test_reencoding_waits_for_a_request(storage, queues, video, django_capture_on_commit_callbacks):
    service = make_service(storage, queues, FakeProber(VP9))

    analyze(service, video, django_capture_on_commit_callbacks)

    video.refresh_from_db()
    assert video.playback_action == PlaybackAction.TRANSCODE
    assert video.playback_issues == [
        {"code": "video_codec", "codec": "VP9"},
        {"code": "audio_codec", "codec": "Opus"},
    ]
    assert "VP9" in video.playback_reason and "Opus" in video.playback_reason
    assert not video.preparations.exists()
    assert queues["preparation"].calls == []
    state = service.state(video)
    assert state.status == PlaybackStatus.UNAVAILABLE
    assert state.can_prepare is True


def test_a_new_analysis_replaces_the_issues(
    storage, queues, video, django_capture_on_commit_callbacks
):
    analyze(
        make_service(storage, queues, FakeProber(VP9)), video, django_capture_on_commit_callbacks
    )
    video.refresh_from_db()
    assert len(video.playback_issues) == 2

    # The same video analyzed again (e.g. the file was replaced): nothing from before lingers.
    analyze(
        make_service(storage, queues, FakeProber(MKV)), video, django_capture_on_commit_callbacks
    )
    video.refresh_from_db()
    assert video.playback_issues == [{"code": "container", "container": "matroska"}]

    analyze(
        make_service(storage, queues, FakeProber(NATIVE)), video, django_capture_on_commit_callbacks
    )
    video.refresh_from_db()
    assert video.playback_issues == []
    assert video.playback_reason == ""


def test_failed_analysis_keeps_the_video_archived(storage, queues, video):
    error = EngineError(ErrorCode.PROCESSING, "ffprobe: moov atom not found")
    prober = mock.Mock(side_effect=error)
    service = make_service(storage, queues, prober)

    assert service.analyze(video.pk) is None

    video.refresh_from_db()
    assert video.local_status == LocalStatus.AVAILABLE
    assert video.probed_at is not None
    assert video.playback_issues == [{"code": "analysis_failed"}]
    assert "File analysis failed" in video.playback_reason
    state = service.state(video)
    assert state.status == PlaybackStatus.UNAVAILABLE
    assert state.issues == [{"code": "analysis_failed"}]


def test_not_analyzed_video_is_preparing(storage, queues, video):
    state = make_service(storage, queues, FakeProber(NATIVE)).state(video)

    assert state.status == PlaybackStatus.PREPARING


# Preparation ----------------------------------------------------------------------------


def test_remux_builds_the_browser_copy_and_keeps_the_original(
    storage, queues, video, original, django_capture_on_commit_callbacks
):
    runner = FakeRunner()
    service = make_service(storage, queues, FakeProber(MKV), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation = video.preparations.get()
    original_bytes = storage.get_path(original).read_bytes()

    service.execute(preparation.pk)

    preparation.refresh_from_db()
    video.refresh_from_db()
    assert preparation.status == PreparationStatus.COMPLETED
    assert preparation.progress == 100
    assert video.playback_path == str(derived_path(str(original)))
    assert video.playback_path == ".browser/youtube/Canale/2024-01-01 - Video [abc].mp4"
    # The channel folder keeps a single video file: the original.
    folder = storage.get_path(original).parent
    assert sorted(p.name for p in folder.iterdir()) == ["2024-01-01 - Video [abc].mkv"]
    assert storage.get_path(video.playback_path).read_bytes() == b"browser-copy"
    assert storage.get_path(original).read_bytes() == original_bytes
    assert "libx264" not in runner.commands[0]
    assert storage.work_dir_names() == set()
    state = service.state(video)
    assert (state.status, state.source) == (PlaybackStatus.READY, "derived")


def test_transcode_only_on_request(storage, queues, video, django_capture_on_commit_callbacks):
    runner = FakeRunner()
    service = make_service(storage, queues, FakeProber(VP9), runner)
    analyze(service, video, django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=True):
        preparation, created = service.request_transcode(video.pk)
    service.execute(preparation.pk)

    assert created
    assert queues["preparation"].calls == [preparation.pk]
    preparation.refresh_from_db()
    assert preparation.kind == PreparationKind.TRANSCODE
    assert preparation.status == PreparationStatus.COMPLETED
    assert "libx264" in runner.commands[0]


def test_transcode_request_is_refused_when_not_needed(
    storage, queues, video, django_capture_on_commit_callbacks
):
    service = make_service(storage, queues, FakeProber(NATIVE))
    analyze(service, video, django_capture_on_commit_callbacks)

    with pytest.raises(InvalidPlaybackState):
        service.request_transcode(video.pk)


def test_transcode_request_returns_the_active_preparation(
    storage, queues, video, django_capture_on_commit_callbacks
):
    service = make_service(storage, queues, FakeProber(VP9))
    analyze(service, video, django_capture_on_commit_callbacks)
    first, _ = service.request_transcode(video.pk)

    again, created = service.request_transcode(video.pk)

    assert not created
    assert again.pk == first.pk


def test_database_allows_one_active_preparation(video):
    PlaybackPreparation.objects.create(video=video, kind=PreparationKind.REMUX)

    with pytest.raises(IntegrityError), transaction.atomic():
        PlaybackPreparation.objects.create(video=video, kind=PreparationKind.TRANSCODE)


def test_ffmpeg_failure_never_invalidates_the_archived_video(
    storage, queues, video, original, django_capture_on_commit_callbacks
):
    runner = FakeRunner(error=EngineError(ErrorCode.PROCESSING, "ffmpeg: Invalid data found"))
    service = make_service(storage, queues, FakeProber(VP9), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation, _ = service.request_transcode(video.pk)

    service.execute(preparation.pk)

    preparation.refresh_from_db()
    video.refresh_from_db()
    assert preparation.status == PreparationStatus.FAILED
    assert preparation.error_code == ErrorCode.PROCESSING
    assert "Invalid data" in preparation.error_message
    assert video.local_status == LocalStatus.AVAILABLE
    assert video.playback_path == ""
    assert storage.exists(original)
    assert storage.work_dir_names() == set()
    state = service.state(video)
    assert state.status == PlaybackStatus.UNAVAILABLE
    assert state.can_prepare is True
    assert state.preparation.error_message


def test_retry_after_a_failed_transcode(storage, queues, video, django_capture_on_commit_callbacks):
    runner = FakeRunner(error=EngineError(ErrorCode.PROCESSING, "boom"))
    service = make_service(storage, queues, FakeProber(VP9), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    failed, _ = service.request_transcode(video.pk)
    service.execute(failed.pk)

    retry, created = service.request_transcode(video.pk)

    assert created and retry.pk != failed.pk
    assert video.preparations.count() == 2


def test_unplayable_output_fails_the_preparation(
    storage, queues, video, django_capture_on_commit_callbacks
):
    service = make_service(storage, queues, FakeProber(VP9, output=VP9))
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation, _ = service.request_transcode(video.pk)

    service.execute(preparation.pk)

    preparation.refresh_from_db()
    assert preparation.status == PreparationStatus.FAILED
    assert "cannot be played in the browser" in preparation.error_message
    assert not storage.exists(derived_path(video.file_path))


def test_insufficient_space_fails_before_ffmpeg(
    storage, queues, video, django_capture_on_commit_callbacks
):
    runner = FakeRunner()
    service = make_service(storage, queues, FakeProber(VP9), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation, _ = service.request_transcode(video.pk)

    with mock.patch.object(storage, "available_space", return_value=10):
        service.execute(preparation.pk)

    preparation.refresh_from_db()
    assert preparation.error_code == ErrorCode.STORAGE
    assert runner.commands == []


def test_execute_is_idempotent(storage, queues, video, django_capture_on_commit_callbacks):
    runner = FakeRunner()
    service = make_service(storage, queues, FakeProber(MKV), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation = video.preparations.get()

    service.execute(preparation.pk)
    service.execute(preparation.pk)

    assert len(runner.commands) == 1


# Streaming ------------------------------------------------------------------------------


def test_stream_uses_the_derived_copy(storage, video, original):
    derived = derived_path(str(original))
    storage.get_path(derived).parent.mkdir(parents=True)
    storage.get_path(derived).write_bytes(b"copy")
    video.playback_action = PlaybackAction.REMUX
    video.playback_path = str(derived)
    video.save()

    assert MediaService(storage=storage).stream_path(video) == derived


def test_stream_refuses_an_original_that_needs_conversion(storage, video):
    video.playback_action = PlaybackAction.TRANSCODE
    video.probed_at = ago(minutes=1)
    video.save()

    with pytest.raises(MediaUnavailable) as excinfo:
        MediaService(storage=storage).stream_path(video)
    assert excinfo.value.code == "not_playable"


def test_stream_serves_a_video_not_analyzed_yet(storage, video, original):
    assert MediaService(storage=storage).stream_path(video) == original


# Reconcile ------------------------------------------------------------------------------


def test_reconcile_marks_stale_preparations_interrupted(storage, queues, video):
    preparation = PlaybackPreparation.objects.create(
        video=video,
        kind=PreparationKind.TRANSCODE,
        status=PreparationStatus.RUNNING,
        last_heartbeat_at=ago(minutes=30),
    )
    storage.work_dir(f"prep-{preparation.pk}")

    stats = make_service(storage, queues, FakeProber(NATIVE)).reconcile()

    preparation.refresh_from_db()
    assert stats["interrupted"] == 1
    assert preparation.status == PreparationStatus.FAILED
    assert preparation.error_code == ErrorCode.INTERRUPTED
    assert storage.work_dir_names() == set()


def test_reconcile_requeues_lost_preparations(storage, queues, video):
    preparation = PlaybackPreparation.objects.create(video=video, kind=PreparationKind.REMUX)
    PlaybackPreparation.objects.filter(pk=preparation.pk).update(created_at=ago(minutes=5))

    stats = make_service(storage, queues, FakeProber(NATIVE)).reconcile()

    assert stats["requeued"] == 1
    assert queues["preparation"].calls == [preparation.pk]


def test_reconcile_queues_analysis_of_videos_never_analyzed(storage, queues, video):
    stats = make_service(storage, queues, FakeProber(NATIVE)).reconcile()

    assert stats["analysis_queued"] == 1
    assert queues["analysis"].calls == [video.pk]


def test_reconcile_keeps_download_work_dirs(storage, queues, video):
    storage.work_dir(42)
    storage.work_dir("prep-999")

    make_service(storage, queues, FakeProber(NATIVE)).reconcile()

    assert storage.work_dir_names() == {"42"}


# Download hook --------------------------------------------------------------------------


def test_completed_download_queues_the_analysis(
    service, analysis_queue, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        download, _ = service.request("https://youtu.be/jNQXAC9IVRw")
    with django_capture_on_commit_callbacks(execute=True):
        service.execute(download.pk)

    assert analysis_queue.calls == [download.video_id]


def test_failure_messages_do_not_expose_filesystem_paths(
    storage, queues, video, django_capture_on_commit_callbacks
):
    source = storage.get_path(video.file_path)
    runner = FakeRunner(error=EngineError(ErrorCode.PROCESSING, f"ffmpeg: {source}: denied"))
    service = make_service(storage, queues, FakeProber(VP9), runner)
    analyze(service, video, django_capture_on_commit_callbacks)
    preparation, _ = service.request_transcode(video.pk)

    service.execute(preparation.pk)

    preparation.refresh_from_db()
    assert str(storage.root) not in preparation.error_message
    assert preparation.error_message.startswith("ffmpeg: youtube/Canale/")


def test_derived_path_mirrors_the_original_under_a_separate_tree():
    assert str(derived_path("youtube/Canale/Titolo v2.0 [abc].webm")) == (
        ".browser/youtube/Canale/Titolo v2.0 [abc].mp4"
    )
    # An original that is already an MP4 (but not playable) gets a distinct path.
    assert str(derived_path("youtube/Canale/x [abc].mp4")) == ".browser/youtube/Canale/x [abc].mp4"
