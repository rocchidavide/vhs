from datetime import date, datetime

from ninja import Field, Schema

from api.schemas.organization import CollectionRef, TagRef
from api.schemas.thumbnails import local_thumbnail_url
from services.playback_service import PlaybackService, PlaybackStatus


class PreparationOut(Schema):
    id: int
    kind: str
    status: str
    progress: float | None
    error_code: str
    error_message: str
    created_at: datetime
    completed_at: datetime | None


class PlaybackOut(Schema):
    status: str
    source: str | None
    action: str
    # Why direct playback is not possible: {"code": ..., parameters}, e.g.
    # {"code": "video_codec", "codec": "VP9"}. The UI translates them by code.
    issues: list[dict[str, str]]
    reason: str
    can_prepare: bool
    preparation: PreparationOut | None


class ProgressOut(Schema):
    position_seconds: float
    duration: float | None
    updated_at: datetime | None


class ProgressIn(Schema):
    position_seconds: float = Field(..., ge=0)
    duration: float | None = Field(None, gt=0)


class VideoOut(Schema):
    id: int
    title: str
    description: str
    platform: str
    platform_id: str
    source_url: str
    channel_name: str | None = Field(None, alias="channel.name")
    duration: int | None
    upload_date: date | None
    local_status: str
    thumbnail: str | None = None
    source_status: str
    container: str
    video_codec: str
    audio_codec: str
    resolution: str
    file_size: int | None
    playback: PlaybackOut
    tags: list[TagRef]
    collections: list[CollectionRef]
    source_tags: list[str] = []

    @staticmethod
    def resolve_thumbnail(obj) -> str | None:
        return local_thumbnail_url(obj)

    @staticmethod
    def resolve_tags(obj) -> list:
        return list(obj.tags.all())

    @staticmethod
    def resolve_collections(obj) -> list:
        return sorted(obj.collections.all(), key=lambda collection: collection.name.lower())

    @staticmethod
    def resolve_source_tags(obj) -> list[str]:
        # Platform metadata, read-only: never converted into personal tags.
        tags = (obj.platform_metadata or {}).get("tags") or []
        return [str(tag) for tag in tags if isinstance(tag, str | int)]

    @staticmethod
    def resolve_playback(obj) -> PlaybackOut:
        state = PlaybackService().state(obj)
        return {
            "status": state.status,
            "source": state.source,
            "action": state.action,
            "issues": state.issues,
            "reason": state.reason,
            "can_prepare": state.can_prepare,
            "preparation": state.preparation,
        }


class VideoListItemOut(Schema):
    id: int
    title: str
    channel_id: int | None
    channel_name: str | None = Field(None, alias="channel.name")
    duration: int | None
    upload_date: date | None
    created_at: datetime
    local_status: str
    thumbnail: str | None = None
    playback_status: str = ""
    progress_position: float | None = None
    progress_duration: float | None = None
    tags: list[TagRef]

    @staticmethod
    def resolve_thumbnail(obj) -> str | None:
        return local_thumbnail_url(obj)

    @staticmethod
    def resolve_tags(obj) -> list:
        return list(obj.tags.all())

    @staticmethod
    def resolve_playback_status(obj) -> str:
        # Mirrors PlaybackService.state, using the annotation added by the list query.
        if obj.local_status != "available":
            return PlaybackStatus.UNAVAILABLE
        if obj.playback_path or obj.playback_action == "native":
            return PlaybackStatus.READY
        if obj.has_active_preparation or (not obj.playback_action and obj.probed_at is None):
            return PlaybackStatus.PREPARING
        return PlaybackStatus.UNAVAILABLE


class ChannelOut(Schema):
    id: int
    name: str
    platform: str
    video_count: int
