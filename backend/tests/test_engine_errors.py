import pytest

from engine.downloader.ytdlp import classify_error
from engine.errors import ErrorCode, sanitize_message
from engine.platforms import get_platform


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", ErrorCode.AUTHENTICATION),
        ("ERROR: [youtube] abc: Sign in to confirm your age", ErrorCode.AUTHENTICATION),
        ("ERROR: [youtube] abc: Private video", ErrorCode.SOURCE_UNAVAILABLE),
        ("ERROR: [youtube] abc: Video unavailable", ErrorCode.SOURCE_UNAVAILABLE),
        ("ERROR: Unable to download webpage: HTTP Error 503", ErrorCode.NETWORK),
        ("ERROR: The read operation timed out", ErrorCode.NETWORK),
        ("ERROR: Postprocessing: ffmpeg exited with code 1", ErrorCode.PROCESSING),
        ("ERROR: [Errno 28] No space left on device", ErrorCode.STORAGE),
        ("something odd", ErrorCode.UNKNOWN),
        ("ERROR: [RaiPlay] abc: This video is DRM protected", ErrorCode.DRM),
        (
            "ERROR: [RaiPlay] abc: This video is not available from your location due to geo "
            "restriction",
            ErrorCode.GEO_RESTRICTED,
        ),
        (
            "ERROR: [youtube] abc: The uploader has not made this video available in your country",
            ErrorCode.GEO_RESTRICTED,
        ),
    ],
)
def test_classify_error(message, code):
    assert classify_error(message) == code


EXPIRED = "ERROR: [RaiPlay] abc: Unable to download JSON metadata: HTTP Error 404: Not Found"


def test_a_platform_classifies_its_own_errors():
    # On RaiPlay a 404 means an expired or removed video; elsewhere it stays a network error.
    assert classify_error(EXPIRED, platform=get_platform("raiplay")) == ErrorCode.SOURCE_UNAVAILABLE
    assert classify_error(EXPIRED, platform=get_platform("youtube")) == ErrorCode.NETWORK
    assert classify_error(EXPIRED) == ErrorCode.NETWORK


def test_sanitize_removes_query_strings_and_secrets():
    message = (
        "\x1b[0;31mERROR:\x1b[0m HTTP Error 403 for "
        "https://rr1.googlevideo.com/videoplayback?expire=1&sig=SECRET&ip=1.2.3.4 "
        "Cookie: SID=abcdef; token=xyz"
    )

    clean = sanitize_message(message)

    assert "SECRET" not in clean
    assert "1.2.3.4" not in clean
    assert "abcdef" not in clean
    assert "xyz" not in clean
    assert "\x1b" not in clean
    assert "https://rr1.googlevideo.com/videoplayback" in clean


def test_sanitize_hides_work_directory_paths():
    clean = sanitize_message("cannot write /srv/video-library/.incomplete/12/abc.mp4.part")

    assert ".incomplete" not in clean
    assert "[work-dir]" in clean
