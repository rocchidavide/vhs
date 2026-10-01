from engine.extractors.base import MetadataExtractor


class YouTubeMetadataExtractor(MetadataExtractor):
    platform = "youtube"

    def is_short(self, info: dict) -> bool | None:
        url = info.get("webpage_url") or info.get("original_url") or ""
        if "/shorts/" in url:
            return True
        width, height, duration = info.get("width"), info.get("height"), info.get("duration")
        if width is None or height is None or duration is None:
            return None
        return height > width and duration <= 180
