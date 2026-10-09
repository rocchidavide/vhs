from datetime import date

import pytest

from engine.metadata import ChannelMetadata, VideoMetadata
from engine.naming import MAX_TITLE_LENGTH, NamingTemplate, build_basename, with_suffix


def metadata(**overrides) -> VideoMetadata:
    values = {
        "platform": "youtube",
        "platform_id": "dQw4w9WgXcQ",
        "title": "Titolo del video",
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "upload_date": date(2024, 3, 15),
        "channel": ChannelMetadata("youtube", "UC1", "Nome Canale"),
    }
    return VideoMetadata(**(values | overrides))


def test_standard_template():
    path = with_suffix(build_basename(NamingTemplate.STANDARD, metadata()), ".mp4")

    assert str(path) == "youtube/Nome Canale/2024-03-15 - Titolo del video [dQw4w9WgXcQ].mp4"


def test_tv_show_template():
    path = with_suffix(build_basename(NamingTemplate.TV_SHOW, metadata()), ".info.json")

    assert str(path) == (
        "youtube/Nome Canale/Season 2024/s2024.e0315 - Titolo del video [dQw4w9WgXcQ].info.json"
    )


@pytest.mark.parametrize("template", list(NamingTemplate))
def test_missing_date_and_channel(template):
    path = build_basename(template, metadata(upload_date=None, channel=None))

    assert path.parts[1] == "Unknown channel"
    assert path.name == "unknown-date - Titolo del video [dQw4w9WgXcQ]"


def test_invalid_characters_are_sanitized():
    unsafe = metadata(
        title='../../etc/passwd: a "b" <c>|d?*\x00',
        channel=ChannelMetadata("youtube", "UC1", ".. / Canale\\strano ."),
    )

    path = build_basename(NamingTemplate.STANDARD, unsafe)

    assert ".." not in path.parts
    assert len(path.parts) == 3
    assert not set('\\:*?"<>|\x00') & set(str(path))
    assert path.name.endswith("[dQw4w9WgXcQ]")


def test_long_titles_are_truncated_but_keep_the_id():
    path = build_basename(NamingTemplate.STANDARD, metadata(title="x" * 500))

    assert len(path.name) <= len("2024-03-15 - ") + MAX_TITLE_LENGTH + len(" [dQw4w9WgXcQ]")
    assert path.name.endswith("[dQw4w9WgXcQ]")


def test_with_suffix_keeps_dots_in_titles():
    path = build_basename(NamingTemplate.STANDARD, metadata(title="Vol. 2"))

    assert with_suffix(path, ".mp4").name == "2024-03-15 - Vol. 2 [dQw4w9WgXcQ].mp4"
