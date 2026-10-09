import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from engine.audio import AudioKind, AudioTrack
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
    assert ytdlp_extractors() == [r"youtube", r"raiplay"]


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


# RaiPlay ------------------------------------------------------------------------------------


def load_raiplay() -> dict:
    return json.loads((FIXTURES / "raiplay_video.json").read_text())


def test_lookups_find_raiplay():
    raiplay = get_platform("raiplay")

    assert platform_for_info({"extractor_key": "RaiPlay"}) is raiplay
    assert platform_for_host("raiplay.it") is raiplay
    # Live channels, programmes and RaiPlay Sound have other extractors: not allowed.
    assert platform_for_info({"extractor_key": "RaiPlayLive"}) is None
    assert platform_for_host("www.raiplaysound.it") is None


def test_maps_real_raiplay_info():
    info = load_raiplay()

    metadata = platform_for_info(info).map(info)

    assert metadata.platform == "raiplay"
    assert metadata.platform_id == "b1255a4a-8e72-4a2f-b9f3-fc1308e00736"
    assert metadata.title == "Blanca - S1E1 - Senza occhi"
    assert metadata.upload_date == date(2021, 11, 19)
    assert metadata.duration == 6493
    assert metadata.is_short is None
    # The series is the channel; the network it is listed under is information.
    assert (metadata.channel.platform_id, metadata.channel.name) == ("blanca", "Blanca")
    assert metadata.platform_metadata["network"] == "Rai Premium"
    assert metadata.platform_metadata["season_number"] == 1
    assert metadata.platform_metadata["episode"] == "Senza occhi"


def test_raiplay_channel_falls_back_to_the_network():
    raiplay = get_platform("raiplay")

    channel = raiplay.map_channel({"uploader": "Rai 3"})

    assert (channel.platform_id, channel.name) == ("rai-3", "Rai 3")
    assert raiplay.map_channel({}) is None


def test_raiplay_series_with_accents_has_a_stable_id():
    channel = get_platform("raiplay").map_channel({"series": "Che tempo che fa – Città"})

    assert channel.platform_id == "che-tempo-che-fa-citta"


@pytest.mark.parametrize(
    ("language", "track"),
    [
        ("ita", AudioTrack("it", AudioKind.DEFAULT)),
        ("vor", AudioTrack("", AudioKind.ORIGINAL)),
        ("des", AudioTrack("it", AudioKind.DESCRIPTION)),
        (None, AudioTrack()),
    ],
)
def test_raiplay_audio_tracks(language, track):
    assert get_platform("raiplay").audio_track({"language": language}) == track
