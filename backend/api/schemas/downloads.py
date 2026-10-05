from datetime import date, datetime

from ninja import Field, Schema

from api.schemas.thumbnails import local_thumbnail_url


class DownloadIn(Schema):
    url: str = Field(..., max_length=2048)


class VideoSummaryOut(Schema):
    id: int
    title: str
    platform: str
    platform_id: str
    channel_name: str | None = Field(None, alias="channel.name")
    thumbnail_url: str
    duration: int | None
    upload_date: date | None
    local_status: str
    thumbnail: str | None = None
    source_status: str

    @staticmethod
    def resolve_thumbnail(obj) -> str | None:
        return local_thumbnail_url(obj)


class DownloadOut(Schema):
    id: int
    status: str
    progress: float | None
    downloaded_bytes: int | None
    total_bytes: int | None
    speed: float | None
    eta: int | None
    error_code: str
    error_message: str
    ytdlp_version: str
    is_stalled: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_progress_at: datetime | None
    last_heartbeat_at: datetime | None
    video: VideoSummaryOut
