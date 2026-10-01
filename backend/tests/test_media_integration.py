"""Real ffmpeg/ffprobe runs on tiny generated files (skipped when the tools are missing)."""

import shutil
import subprocess

import pytest

from engine.errors import EngineError
from engine.media import ffmpeg
from engine.media.compat import PlaybackAction, plan_playback
from engine.media.probe import probe

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed"
)

SOURCE = ["-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10", "-f", "lavfi", "-i", "sine"]


def generate(path, *codec_args):
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", *SOURCE, "-t", "1", *codec_args, str(path)],
        check=True,
    )
    return path


def convert(src, dst):
    media = probe(src)
    plan = plan_playback(media)
    progress = []
    ffmpeg.run(
        ffmpeg.build_command(src, dst, plan, ffmpeg.EncodeOptions()),
        media.duration,
        progress.append,
        lambda: None,
        timeout=120,
    )
    return plan, progress


def test_remux_mkv_to_a_playable_mp4(tmp_path):
    src = generate(tmp_path / "in.mkv", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")
    original = src.read_bytes()

    plan, _ = convert(src, tmp_path / "out.mp4")

    assert plan.action == PlaybackAction.REMUX
    assert plan_playback(probe(tmp_path / "out.mp4")).action == PlaybackAction.NATIVE
    assert src.read_bytes() == original


def test_transcode_vp9_opus_to_h264_aac(tmp_path):
    src = generate(tmp_path / "in.webm", "-c:v", "libvpx-vp9", "-b:v", "100k", "-c:a", "libopus")

    plan, progress = convert(src, tmp_path / "out.mp4")

    assert plan.action == PlaybackAction.TRANSCODE
    result = probe(tmp_path / "out.mp4")
    assert (result.video.codec, result.audio.codec) == ("h264", "aac")
    assert progress and max(progress) > 50


def test_ffmpeg_failure_is_reported(tmp_path):
    src = generate(tmp_path / "in.mkv", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")
    media = probe(src)
    command = ffmpeg.build_command(
        src,
        tmp_path / "out.mp4",
        plan_playback(media),
        ffmpeg.EncodeOptions(),
    )
    command[command.index("-f") + 1] = "no-such-format"

    with pytest.raises(EngineError, match="ffmpeg"):
        ffmpeg.run(command, media.duration, lambda p: None, lambda: None, timeout=60)


def test_probe_of_a_non_media_file(tmp_path):
    bogus = tmp_path / "bogus.mp4"
    bogus.write_text("not a video")

    with pytest.raises(EngineError):
        probe(bogus)
