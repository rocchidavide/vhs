from engine.extractors.base import ChannelMetadata, MetadataExtractor, VideoMetadata
from engine.extractors.generic import GenericMetadataExtractor
from engine.extractors.youtube import YouTubeMetadataExtractor

_EXTRACTORS: dict[str, MetadataExtractor] = {"youtube": YouTubeMetadataExtractor()}


def get_extractor(extractor_key: str | None) -> MetadataExtractor:
    return _EXTRACTORS.get((extractor_key or "").lower(), GenericMetadataExtractor())


__all__ = ["ChannelMetadata", "MetadataExtractor", "VideoMetadata", "get_extractor"]
