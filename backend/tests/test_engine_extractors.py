import json
from datetime import date
from pathlib import Path

from engine.extractors import get_extractor
from engine.extractors.base import SNAPSHOT_EXCLUDED_KEYS
from engine.extractors.generic import GenericMetadataExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def load_info() -> dict:
    return json.loads((FIXTURES / "youtube_video.json").read_text())


def test_maps_real_youtube_info():
    metadata = get_extractor("Youtube").map(load_info())

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

    snapshot = get_extractor("youtube").map(info).snapshot

    assert not SNAPSHOT_EXCLUDED_KEYS & snapshot.keys()
    assert snapshot["id"] == "jNQXAC9IVRw"


def test_missing_metadata_is_not_guessed():
    info = {"id": "abc", "extractor_key": "Youtube"}

    metadata = get_extractor("youtube").map(info)

    assert metadata.title == "abc"
    assert metadata.upload_date is None
    assert metadata.channel is None
    assert metadata.estimated_size is None
    assert metadata.is_short is None


def test_invalid_upload_date_is_ignored():
    metadata = get_extractor("youtube").map({"id": "abc", "upload_date": "2024-13-99"})

    assert metadata.upload_date is None


def test_shorts_url_is_a_short():
    info = {"id": "abc", "webpage_url": "https://www.youtube.com/shorts/abc"}

    assert get_extractor("youtube").map(info).is_short is True


def test_unknown_extractor_falls_back_to_generic():
    assert isinstance(get_extractor("Vimeo"), GenericMetadataExtractor)
