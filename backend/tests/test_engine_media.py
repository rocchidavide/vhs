import json
from pathlib import Path

import pytest

from engine.media.compat import PlaybackAction, StreamOp, plan_playback
from engine.media.ffmpeg import EncodeOptions, build_command, parse_progress
from engine.media.probe import AudioStream, MediaProbe, VideoStream, parse_probe

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_probe(name: str) -> MediaProbe:
    return parse_probe(json.loads((FIXTURES / f"ffprobe_{name}.json").read_text()))


def media(video="h264", audio="aac", formats=("mov", "mp4"), pix_fmt="yuv420p") -> MediaProbe:
    return MediaProbe(
        format_names=formats,
        duration=10.0,
        video=VideoStream(codec=video, pix_fmt=pix_fmt, width=640, height=360) if video else None,
        audio=AudioStream(codec=audio) if audio else None,
    )


def test_parse_real_ffprobe_output():
    probe = fixture_probe("h264_aac_mp4")

    assert probe.format_names[:2] == ("mov", "mp4")
    assert probe.duration == 2.0
    assert probe.video.codec == "h264"
    assert probe.video.pix_fmt == "yuv420p"
    assert probe.resolution == "320x240"
    assert probe.audio.codec == "aac"
    assert probe.to_dict()["format_names"][:2] == ["mov", "mp4"]


def test_cover_art_is_not_the_video_stream():
    data = {
        "format": {"format_name": "mp3"},
        "streams": [
            {"codec_type": "audio", "codec_name": "mp3"},
            {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ],
    }

    assert parse_probe(data).video is None


@pytest.mark.parametrize(
    ("fixture", "action", "video_op", "audio_op"),
    [
        ("h264_aac_mp4", PlaybackAction.NATIVE, StreamOp.COPY, StreamOp.COPY),
        ("h264_aac_mkv", PlaybackAction.REMUX, StreamOp.COPY, StreamOp.COPY),
        ("vp9_opus_webm", PlaybackAction.TRANSCODE, StreamOp.ENCODE, StreamOp.ENCODE),
    ],
)
def test_plan_for_real_files(fixture, action, video_op, audio_op):
    plan = plan_playback(fixture_probe(fixture))

    assert (plan.action, plan.video_op, plan.audio_op) == (action, video_op, audio_op)


@pytest.mark.parametrize(
    ("probe", "action", "video_op", "audio_op"),
    [
        (media(audio="opus"), PlaybackAction.TRANSCODE, StreamOp.COPY, StreamOp.ENCODE),
        (media(video="hevc"), PlaybackAction.TRANSCODE, StreamOp.ENCODE, StreamOp.COPY),
        (media(video="av1", formats=("matroska", "webm")), PlaybackAction.TRANSCODE,
         StreamOp.ENCODE, StreamOp.COPY),
        (media(pix_fmt="yuv420p10le"), PlaybackAction.TRANSCODE, StreamOp.ENCODE, StreamOp.COPY),
        (media(audio=None), PlaybackAction.NATIVE, StreamOp.COPY, StreamOp.NONE),
        (media(audio="mp3"), PlaybackAction.NATIVE, StreamOp.COPY, StreamOp.COPY),
        (media(audio=None, formats=("matroska", "webm")), PlaybackAction.REMUX, StreamOp.COPY,
         StreamOp.NONE),
        (media(video=None), PlaybackAction.UNSUPPORTED, StreamOp.NONE, StreamOp.NONE),
    ],
)  # fmt: skip
def test_plan_matrix(probe, action, video_op, audio_op):
    plan = plan_playback(probe)

    assert (plan.action, plan.video_op, plan.audio_op) == (action, video_op, audio_op)


def test_plan_issues_have_stable_codes_and_parameters():
    assert plan_playback(media(video="vp9", audio="opus")).issues == (
        {"code": "video_codec", "codec": "VP9"},
        {"code": "audio_codec", "codec": "Opus"},
    )
    assert plan_playback(media(pix_fmt="yuv444p")).issues == (
        {"code": "pixel_format", "pix_fmt": "yuv444p"},
    )
    assert plan_playback(media(formats=("matroska", "webm"))).issues == (
        {"code": "container", "container": "matroska"},
    )
    assert plan_playback(media(video=None)).issues == ({"code": "no_video"},)
    assert plan_playback(media()).issues == ()


def test_plan_reasons_are_readable():
    assert "Opus" in plan_playback(media(audio="opus")).reason
    assert "matroska" in plan_playback(media(formats=("matroska", "webm"))).reason
    assert plan_playback(media()).reason == ""


def test_remux_command_copies_streams():
    plan = plan_playback(media(formats=("matroska",)))

    command = build_command(Path("in.mkv"), Path("out.mp4"), plan, EncodeOptions())

    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert "libx264" not in command
    assert command[-1] == "out.mp4"
    assert "+faststart" in command


def test_transcode_encodes_only_what_is_needed():
    plan = plan_playback(media(audio="opus"))
    options = EncodeOptions(preset="fast", crf=23, audio_bitrate="128k", threads=2)

    command = build_command(Path("in.mp4"), Path("out.mp4"), plan, options)

    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-b:a") + 1] == "128k"
    assert command[command.index("-threads") + 1] == "2"


def test_full_transcode_command():
    plan = plan_playback(fixture_probe("vp9_opus_webm"))

    command = build_command(Path("in.webm"), Path("out.mp4"), plan, EncodeOptions(crf=19))

    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-crf") + 1] == "19"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"


def test_no_command_for_native_files():
    with pytest.raises(ValueError):
        build_command(Path("a"), Path("b"), plan_playback(media()), EncodeOptions())


@pytest.mark.parametrize(
    ("line", "duration", "expected"),
    [
        ("out_time_us=5000000", 10.0, 50.0),
        ("out_time_ms=10000000", 10.0, 100.0),
        ("out_time_us=20000000", 10.0, 100.0),
        ("out_time_us=N/A", 10.0, None),
        ("frame=12", 10.0, None),
        ("out_time_us=5000000", None, None),
    ],
)
def test_parse_progress(line, duration, expected):
    assert parse_progress(line, duration) == expected
