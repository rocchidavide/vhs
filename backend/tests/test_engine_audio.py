import pytest
import yt_dlp

from engine.audio import (
    AudioKind,
    AudioTrack,
    downloaded_audio_format,
    normalize_language,
    track_from_format,
)
from engine.downloader.ytdlp import DEFAULT_FORMAT, format_selector


def select(selector: str, formats: list[dict]) -> list[str]:
    """The formats yt-dlp picks with a selector, offline, after sorting them as it does."""
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        ydl.sort_formats({"formats": formats})
        chosen = ydl.build_format_selector(selector)(
            {"formats": formats, "has_merged_format": False, "incomplete_formats": False}
        )
        return [fmt["format_id"] for fmt in chosen]


def video(format_id: str, height: int) -> dict:
    return {
        "format_id": format_id,
        "url": "x",
        "ext": "mp4",
        "protocol": "https",
        "vcodec": "avc1.64001f",
        "acodec": "none",
        "height": height,
    }


def audio(format_id: str, language: str | None, *, ext: str = "m4a", preference=None) -> dict:
    return {
        "format_id": format_id,
        "url": "x",
        "ext": ext,
        "protocol": "https",
        "vcodec": "none",
        "acodec": "mp4a.40.2",
        "language": language,
        "language_preference": preference,
    }


# Which track is asked for --------------------------------------------------------------------


def test_youtube_gets_the_original_track_not_a_dub_or_a_description():
    formats = [
        audio("it-desc", "it-desc", preference=-10),
        audio("en", "en-US", preference=10),
        audio("it", "it", preference=-1),
        audio("de", "de", preference=-1),
        video("720", 720),
        video("1080", 1080),
    ]

    assert select(DEFAULT_FORMAT, formats) == ["1080+en"]


@pytest.mark.parametrize("order", ["italian-first", "italian-last"])
def test_raiplay_gets_the_italian_track_whatever_the_order(order):
    tracks = [
        audio("aud-des", "des", ext="mp4"),
        audio("aud-vor", "vor", ext="mp4"),
        audio("aud-ita", "ita", ext="mp4"),
    ]
    if order == "italian-first":
        tracks.reverse()

    assert select(format_selector("it"), [*tracks, video("1080", 1080)]) == ["1080+aud-ita"]


def test_without_the_language_the_best_track_that_is_not_a_description():
    formats = [audio("aud-des", "des", ext="mp4"), audio("aud-vor", "vor", ext="mp4")]

    assert select(format_selector("it"), [*formats, video("1080", 1080)]) == ["1080+aud-vor"]


def test_a_single_file_with_its_own_audio_is_kept():
    # Older RaiPlay videos: one MP4 with video and audio, no separate audio track.
    single = video("https-1800", 576) | {"acodec": "mp4a.40.2"}

    assert select(format_selector("it"), [video("https-800", 394), single]) == ["https-1800"]


# What is recorded ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "language"),
    [("ita", "it"), ("ENG", "en"), ("en-US", "en-US"), ("it", "it"), ("und", ""), (None, "")],
)
def test_normalize_language(code, language):
    assert normalize_language(code) == language


@pytest.mark.parametrize(
    ("fmt", "track"),
    [
        ({"language": "en-US", "language_preference": 10}, AudioTrack("en-US", AudioKind.ORIGINAL)),
        ({"language": "it", "language_preference": 5}, AudioTrack("it", AudioKind.DEFAULT)),
        ({"language": "it", "language_preference": -1}, AudioTrack("it", AudioKind.DUBBED)),
        (
            {"language": "it-desc", "language_preference": -10},
            AudioTrack("it", AudioKind.DESCRIPTION),
        ),
        ({"language": None, "language_preference": -1}, AudioTrack()),
        ({}, AudioTrack()),
    ],
)
def test_track_from_a_youtube_format(fmt, track):
    assert track_from_format(fmt) == track


def test_the_downloaded_audio_is_the_audio_only_part():
    info = {
        "language": None,
        "requested_formats": [video("1080", 1080), audio("en", "en-US", preference=10)],
    }

    assert downloaded_audio_format(info)["format_id"] == "en"


def test_a_single_file_brings_its_own_audio():
    info = {"format_id": "18", "language": "it", "requested_formats": None}

    assert downloaded_audio_format(info) is info
