import pytest

from engine.errors import EngineError, ErrorCode
from engine.urls import normalize_url

CANONICAL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://youtube.com/watch?v=dQw4w9WgXcQ&t=42",
        "https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
        "  https://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ  ",
    ],
)
def test_youtube_variants_share_the_canonical_url(url):
    assert normalize_url(url) == CANONICAL


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("", ErrorCode.UNSUPPORTED_URL),
        ("ftp://youtube.com/watch?v=dQw4w9WgXcQ", ErrorCode.UNSUPPORTED_URL),
        ("file:///etc/passwd", ErrorCode.UNSUPPORTED_URL),
        ("http://127.0.0.1/watch?v=dQw4w9WgXcQ", ErrorCode.UNSUPPORTED_URL),
        ("http://169.254.169.254/latest/meta-data", ErrorCode.UNSUPPORTED_URL),
        ("https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ", ErrorCode.UNSUPPORTED_URL),
        ("https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ", ErrorCode.UNSUPPORTED_URL),
        ("https://youtube.com:8443/watch?v=dQw4w9WgXcQ", ErrorCode.UNSUPPORTED_URL),
        ("https://www.youtube.com/watch?v=short", ErrorCode.UNSUPPORTED_URL),
        ("https://www.youtube.com/", ErrorCode.UNSUPPORTED_URL),
        ("https://www.youtube.com/playlist?list=PL123", ErrorCode.PLAYLIST),
        ("https://www.youtube.com/@somechannel", ErrorCode.PLAYLIST),
    ],
)
def test_rejected_urls(url, code):
    with pytest.raises(EngineError) as excinfo:
        normalize_url(url)
    assert excinfo.value.code == code


RAIPLAY = "https://www.raiplay.it/video/2021/11/Blanca-S1E1-Senza-occhi-b1255a4a-8e72-4a2f-b9f3-fc1308e00736.html"


@pytest.mark.parametrize(
    "url",
    [
        RAIPLAY,
        RAIPLAY.replace("www.raiplay.it", "raiplay.it"),
        RAIPLAY.replace("https://", "http://"),
        RAIPLAY + "?wt_mc=social",
        RAIPLAY + "#player",
    ],
)
def test_raiplay_variants_share_the_canonical_url(url):
    assert normalize_url(url) == RAIPLAY


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://www.raiplay.it/programmi/blanca", ErrorCode.PLAYLIST),
        ("https://www.raiplay.it/programmi/blanca/episodi/stagione-1", ErrorCode.PLAYLIST),
        ("https://www.raiplay.it/dirette/rai1", ErrorCode.UNSUPPORTED_URL),
        ("https://www.raiplay.it/", ErrorCode.UNSUPPORTED_URL),
        ("https://www.raiplay.it/video/2021/11/Blanca.html", ErrorCode.UNSUPPORTED_URL),
        (
            "https://www.raiplaysound.it/audio/2021/12/x-1ebae2a7-7cdb-42bb-842e-fe0d193e9707.html",
            ErrorCode.UNSUPPORTED_URL,
        ),
    ],
)
def test_rejected_raiplay_urls(url, code):
    with pytest.raises(EngineError) as excinfo:
        normalize_url(url)
    assert excinfo.value.code == code
