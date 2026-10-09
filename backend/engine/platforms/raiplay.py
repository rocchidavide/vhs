import re
import unicodedata
from urllib.parse import SplitResult

from engine.audio import AudioKind, AudioTrack, normalize_language
from engine.errors import EngineError, ErrorCode
from engine.metadata import ChannelMetadata
from engine.platforms.base import Platform

# A video page: /video/<year>/<month>/<slug>-<uuid>.html
_VIDEO_PATH = re.compile(
    r"^/video/\d{4}/\d{2}/[^/]+-[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}\.html$"
)
_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

# RaiPlay's own codes for its audio tracks (the Italian one is "ita").
_ORIGINAL_VERSION = "vor"
_AUDIO_DESCRIPTION = "des"


class RaiPlay(Platform):
    key = "raiplay"
    name = "RaiPlay"
    hosts = frozenset({"raiplay.it", "www.raiplay.it"})
    extractor_keys = frozenset({"raiplay"})
    # Single videos only: not RaiPlayLive, RaiPlayPlaylist or RaiPlaySound.
    ytdlp_extractors = (r"raiplay",)
    # RaiPlay marks no track as the default: it plays the Italian one.
    default_audio_language = "it"

    def canonical_url(self, parts: SplitResult) -> str:
        if _VIDEO_PATH.match(parts.path):
            return f"https://www.raiplay.it{parts.path}"
        first = next((segment for segment in parts.path.split("/") if segment), "")
        if first in {"programmi", "playlist"}:
            raise EngineError(ErrorCode.PLAYLIST, "Programmes and playlists are not supported yet.")
        if first == "dirette":
            raise EngineError(ErrorCode.UNSUPPORTED_URL, "Live channels cannot be downloaded.")
        raise EngineError(ErrorCode.UNSUPPORTED_URL, "The URL does not identify a video.")

    def map_channel(self, info: dict) -> ChannelMetadata | None:
        """The series is the channel: the network a video is listed under can change."""
        name = info.get("series") or info.get("uploader")
        if not name:
            return None
        return ChannelMetadata(platform=self.key, platform_id=_slug(name), name=name)

    def platform_metadata(self, info: dict) -> dict:
        metadata = super().platform_metadata(info)
        keys = ("series", "season", "season_number", "episode", "episode_number")
        metadata.update({key: info[key] for key in keys if info.get(key) is not None})
        if info.get("uploader"):
            metadata["network"] = info["uploader"]
        return metadata

    def audio_track(self, fmt: dict) -> AudioTrack:
        language = (fmt.get("language") or "").lower()
        if language == _AUDIO_DESCRIPTION:
            return AudioTrack(self.default_audio_language, AudioKind.DESCRIPTION)
        if language == _ORIGINAL_VERSION:
            return AudioTrack("", AudioKind.ORIGINAL)
        if language:
            return AudioTrack(normalize_language(language), AudioKind.DEFAULT)
        return AudioTrack()

    def classify_error(self, message: str) -> ErrorCode | None:
        # An expired or removed video: its JSON description is gone.
        if "http error 404" in message.lower():
            return ErrorCode.SOURCE_UNAVAILABLE
        return None


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _NOT_ALPHANUMERIC.sub("-", ascii_name.lower()).strip("-") or name
