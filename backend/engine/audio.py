"""The audio track of a download: which one VHS asks for, and what it records about it (§18).

VHS downloads one audio track: the one the platform plays by default, never an audio
description. What the downloaded track is (language, original or dubbed) is recorded, so
that later work (choosing the language, adding other tracks) needs no new download.
"""

from dataclasses import dataclass
from enum import StrEnum


class AudioKind(StrEnum):
    ORIGINAL = "original"
    # The platform's main track, when it does not say whether it is the original.
    DEFAULT = "default"
    DUBBED = "dubbed"
    DESCRIPTION = "description"
    UNKNOWN = ""


@dataclass(frozen=True)
class AudioTrack:
    language: str = ""  # e.g. "it", "en-US"; "" when unknown
    kind: AudioKind = AudioKind.UNKNOWN


# yt-dlp's language_preference for YouTube's tracks.
ORIGINAL_PREFERENCE = 10
DEFAULT_PREFERENCE = 5

# ISO 639-2 codes some platforms use, as the ISO 639-1 codes used everywhere else.
_ISO_639_2 = {
    "ara": "ar",
    "chi": "zh",
    "deu": "de",
    "dut": "nl",
    "eng": "en",
    "fra": "fr",
    "fre": "fr",
    "ger": "de",
    "hin": "hi",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "nld": "nl",
    "pol": "pl",
    "por": "pt",
    "rus": "ru",
    "spa": "es",
    "tur": "tr",
    "zho": "zh",
}


def normalize_language(code: str | None) -> str:
    """A language as a BCP 47 tag ("ita" -> "it", "en-US" stays), "" when unknown."""
    code = (code or "").strip()
    if code.lower() in {"", "und", "none"}:
        return ""
    return _ISO_639_2.get(code.lower(), code)


def track_from_format(fmt: dict) -> AudioTrack:
    """What yt-dlp says about an audio format, in the terms of YouTube's extractor."""
    language = fmt.get("language") or ""
    if language.endswith("-desc"):
        return AudioTrack(normalize_language(language.removesuffix("-desc")), AudioKind.DESCRIPTION)
    preference = fmt.get("language_preference")
    if preference == ORIGINAL_PREFERENCE:
        kind = AudioKind.ORIGINAL
    elif preference == DEFAULT_PREFERENCE:
        kind = AudioKind.DEFAULT
    elif language and preference is not None and preference < 0:
        kind = AudioKind.DUBBED
    else:
        kind = AudioKind.UNKNOWN
    return AudioTrack(normalize_language(language), kind)


def downloaded_audio_format(info: dict) -> dict:
    """The format that brought the audio of a download: its audio-only part, or the file."""
    for fmt in info.get("requested_formats") or []:
        if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none"):
            return fmt
    return info
