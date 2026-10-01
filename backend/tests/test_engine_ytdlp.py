from unittest import mock

import pytest
from yt_dlp.utils import DownloadError

from engine.downloader.base import Progress
from engine.downloader.ytdlp import StreamProgress, YTDLPDownloader
from engine.errors import EngineError, ErrorCode


class FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL: records options and replays a scripted run."""

    instances: list["FakeYoutubeDL"] = []
    script = None

    def __init__(self, options):
        self.options = options
        FakeYoutubeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def sanitize_info(self, info):
        return info

    def extract_info(self, url, download):
        return FakeYoutubeDL.script(self, url, download)


@pytest.fixture
def fake_ydl():
    FakeYoutubeDL.instances = []
    with mock.patch("engine.downloader.ytdlp.yt_dlp.YoutubeDL", FakeYoutubeDL):
        yield FakeYoutubeDL


def test_extract_info_restricts_extractors_and_playlists(fake_ydl):
    fake_ydl.script = lambda ydl, url, download: {"id": "abc", "_type": "video"}

    YTDLPDownloader().extract_info("https://www.youtube.com/watch?v=abc")

    options = fake_ydl.instances[0].options
    assert options["allowed_extractors"] == [r"youtube"]
    assert options["noplaylist"] is True


def test_extract_info_rejects_playlists(fake_ydl):
    fake_ydl.script = lambda ydl, url, download: {"id": "PL1", "_type": "playlist"}

    with pytest.raises(EngineError) as excinfo:
        YTDLPDownloader().extract_info("https://www.youtube.com/watch?v=abc")
    assert excinfo.value.code == ErrorCode.PLAYLIST


def test_extract_info_maps_errors(fake_ydl):
    def script(ydl, url, download):
        raise DownloadError("ERROR: [youtube] abc: Private video")

    fake_ydl.script = script

    with pytest.raises(EngineError) as excinfo:
        YTDLPDownloader().extract_info("https://www.youtube.com/watch?v=abc")
    assert excinfo.value.code == ErrorCode.SOURCE_UNAVAILABLE


def test_download_writes_into_work_dir_and_reports_progress(fake_ydl, tmp_path):
    def script(ydl, url, download):
        assert download is True
        assert ydl.options["paths"] == {"home": str(tmp_path), "temp": str(tmp_path)}
        hook = ydl.options["progress_hooks"][0]
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 10.0})
        hook({"status": "finished"})
        ydl.options["postprocessor_hooks"][0]({"status": "started"})
        media = tmp_path / "abc.mp4"
        media.write_bytes(b"video")
        (tmp_path / "abc.info.json").write_text("{}")
        (tmp_path / "abc.webp").write_bytes(b"img")
        return {
            "id": "abc",
            "vcodec": "avc1.64001F",
            "acodec": "mp4a.40.2",
            "requested_downloads": [{"filepath": str(media)}],
        }

    fake_ydl.script = script
    progress, activity = [], []

    result = YTDLPDownloader().download(
        "https://www.youtube.com/watch?v=abc", tmp_path, progress.append, lambda: activity.append(1)
    )

    assert result.media == tmp_path / "abc.mp4"
    assert result.info_json == tmp_path / "abc.info.json"
    assert result.thumbnail == tmp_path / "abc.webp"
    assert result.info["vcodec"] == "avc1.64001F"
    assert progress == [Progress(downloaded_bytes=50, total_bytes=100, speed=10.0)]
    assert len(activity) == 2


VIDEO = "/work/abc.f133.mp4"
AUDIO = "/work/abc.f140.m4a"


def two_streams():
    """What yt-dlp reports for separate video and audio formats (seen on a real download):
    each stream on its own, starting again from zero."""
    return [
        {"status": "downloading", "filename": VIDEO, "downloaded_bytes": 1024,
         "total_bytes": 433081, "speed": 1000.0, "eta": 400},
        {"status": "downloading", "filename": VIDEO, "downloaded_bytes": 433081,
         "total_bytes": 433081, "speed": 1000.0, "eta": 0},
        {"status": "finished", "filename": VIDEO, "downloaded_bytes": 433081,
         "total_bytes": 433081},
        {"status": "downloading", "filename": AUDIO, "downloaded_bytes": 1024,
         "total_bytes": 309288, "speed": 1000.0, "eta": 300},
        {"status": "downloading", "filename": AUDIO, "downloaded_bytes": 309288,
         "total_bytes": 309288, "speed": 1000.0, "eta": 0},
        {"status": "finished", "filename": AUDIO, "downloaded_bytes": 309288,
         "total_bytes": 309288},
    ]  # fmt: skip


def test_stream_progress_sums_video_and_audio():
    streams = StreamProgress()

    reported = [streams.update(data) for data in two_streams()]

    downloaded = [progress.downloaded_bytes for progress in reported]
    assert downloaded == sorted(downloaded), "the bytes never go back at the audio stream"
    assert downloaded[3] == 433081 + 1024
    assert reported[-1].downloaded_bytes == 433081 + 309288
    # The total covers only the streams started so far: the audio is not known yet.
    assert reported[1].total_bytes == 433081
    assert reported[3].total_bytes == 433081 + 309288
    # The ETA stays the current stream's: it is never presented as the overall one.
    assert reported[3].stream_eta == 300


def test_stream_progress_total_is_unknown_while_a_stream_total_is():
    streams = StreamProgress()
    streams.update({"status": "finished", "filename": VIDEO, "total_bytes": 100})

    progress = streams.update({"status": "downloading", "filename": AUDIO, "downloaded_bytes": 5})

    assert progress.downloaded_bytes == 105
    assert progress.total_bytes is None


def test_processing_is_signalled_once_when_merging_starts(fake_ydl, tmp_path):
    events = []

    def script(ydl, url, download):
        progress_hook = ydl.options["progress_hooks"][0]
        pp_hook = ydl.options["postprocessor_hooks"][0]
        # The thumbnail conversion runs before the transfer: not processing yet.
        pp_hook({"postprocessor": "ThumbnailsConvertor", "status": "started", "info_dict": {}})
        for data in two_streams():
            progress_hook(data)
            events.append(data["status"])
        pp_hook({"postprocessor": "Merger", "status": "started"})
        pp_hook({"postprocessor": "Merger", "status": "finished"})
        pp_hook({"postprocessor": "MoveFiles", "status": "started"})
        media = tmp_path / "abc.mp4"
        media.write_bytes(b"video")
        return {"id": "abc", "requested_downloads": [{"filepath": str(media)}]}

    fake_ydl.script = script

    YTDLPDownloader().download(
        "u",
        tmp_path,
        lambda progress: None,
        lambda: None,
        on_processing=lambda: events.append("processing"),
    )

    assert events.count("processing") == 1
    assert events.index("processing") == len(two_streams())


def test_download_without_output_file_is_a_processing_error(fake_ydl, tmp_path):
    fake_ydl.script = lambda ydl, url, download: {"id": "abc", "requested_downloads": [{}]}

    with pytest.raises(EngineError) as excinfo:
        YTDLPDownloader().download("u", tmp_path, lambda p: None, lambda: None)
    assert excinfo.value.code == ErrorCode.PROCESSING


def test_thumbnail_is_reported_before_the_media_transfer(fake_ydl, tmp_path):
    events = []

    def script(ydl, url, download):
        (tmp_path / "abc.webp").write_bytes(b"img")
        pp_hook = ydl.options["postprocessor_hooks"][0]
        info = {"id": "abc"}
        pp_hook({"postprocessor": "ThumbnailsConvertor", "status": "started", "info_dict": info})
        pp_hook({"postprocessor": "ThumbnailsConvertor", "status": "finished", "info_dict": info})
        pp_hook({"postprocessor": "ThumbnailsConvertor", "status": "finished", "info_dict": info})
        ydl.options["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 1})
        media = tmp_path / "abc.mp4"
        media.write_bytes(b"video")
        return {"id": "abc", "requested_downloads": [{"filepath": str(media)}]}

    fake_ydl.script = script

    YTDLPDownloader().download(
        "u",
        tmp_path,
        lambda progress: events.append("progress"),
        lambda: None,
        on_thumbnail=lambda path: events.append(("thumbnail", path.name)),
    )

    assert events == [("thumbnail", "abc.webp"), "progress"]
