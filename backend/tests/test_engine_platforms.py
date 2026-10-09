import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from engine.metadata import SNAPSHOT_EXCLUDED_KEYS
from engine.platforms import (
    PLATFORMS,
    Platform,
    get_platform,
    platform_for_host,
    platform_for_info,
    ytdlp_extractors,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_info() -> dict:
    return json.loads((FIXTURES / "youtube_video.json").read_text())


def test_maps_real_youtube_info():
    metadata = platform_for_info(load_info()).map(load_info())

    assert metadata.platform == "youtube"
    assert metadata.platform_id == "jNQXAC9IVRw"
    assert metadata.title == "Me at the zoo"
    assert metadata.upload_date == date(2005, 4, 24)
    assert metadata.duration == 19
    assert metadata.channel.platform_id == "UC4QobU6STFB0P71PMvOGN5A"
    assert metadata.channel.name == "jawed"
    assert metadata.estimated_size == 433081 + 309288
    assert metadata.is_short is False
    assert metadata.source_url == "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def test_snapshot_drops_bulky_and_sensitive_keys():
    info = load_info() | {"http_headers": {"Cookie": "SID=secret"}, "formats": [{}]}

    snapshot = get_platform("youtube").map(info).snapshot

    assert not SNAPSHOT_EXCLUDED_KEYS & snapshot.keys()
    assert snapshot["id"] == "jNQXAC9IVRw"


def test_missing_metadata_is_not_guessed():
    info = {"id": "abc", "extractor_key": "Youtube"}

    metadata = get_platform("youtube").map(info)

    assert metadata.title == "abc"
    assert metadata.upload_date is None
    assert metadata.channel is None
    assert metadata.estimated_size is None
    assert metadata.is_short is None


def test_invalid_upload_date_is_ignored():
    metadata = get_platform("youtube").map({"id": "abc", "upload_date": "2024-13-99"})

    assert metadata.upload_date is None


def test_shorts_url_is_a_short():
    info = {"id": "abc", "webpage_url": "https://www.youtube.com/shorts/abc"}

    assert get_platform("youtube").map(info).is_short is True


# The registry --------------------------------------------------------------------------------


def test_unsupported_platforms_are_not_found():
    assert platform_for_info({"extractor_key": "Vimeo"}) is None
    assert platform_for_info({}) is None
    assert platform_for_host("vimeo.com") is None
    assert get_platform("vimeo") is None


def test_lookups_find_youtube():
    youtube = get_platform("youtube")

    assert platform_for_info({"extractor_key": "Youtube"}) is youtube
    assert platform_for_host("WWW.YouTube.com.") is youtube
    assert platform_for_host("youtu.be") is youtube
    assert ytdlp_extractors() == [r"youtube"]


@pytest.mark.parametrize("platform", PLATFORMS, ids=lambda platform: platform.key)
def test_every_platform_is_complete(platform):
    assert platform.key and platform.key == platform.key.lower()
    assert platform.name
    assert platform.hosts and all(host == host.lower() for host in platform.hosts)
    assert platform.extractor_keys and platform.ytdlp_extractors
    assert type(platform).canonical_url is not Platform.canonical_url


def test_keys_hosts_and_extractors_are_not_shared():
    for attribute in ("hosts", "extractor_keys"):
        values = [value for platform in PLATFORMS for value in getattr(platform, attribute)]
        assert len(values) == len(set(values)), attribute
    assert len({platform.key for platform in PLATFORMS}) == len(PLATFORMS)


def test_canonical_url_of_the_platform_of_the_host():
    parts = urlsplit("https://youtu.be/jNQXAC9IVRw")

    assert platform_for_host(parts.hostname).canonical_url(parts) == (
        "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    )
