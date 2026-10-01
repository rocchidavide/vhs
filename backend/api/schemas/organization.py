from datetime import datetime

from ninja import Field, Schema


class TagRef(Schema):
    id: int
    name: str
    slug: str
    color: str


class TagOut(TagRef):
    video_count: int = 0
    archived_count: int = 0


class TagIn(Schema):
    name: str = Field(..., max_length=200)
    color: str = Field(..., max_length=7)


class TagPatch(Schema):
    name: str | None = Field(None, max_length=200)
    color: str | None = Field(None, max_length=7)


class VideoTagsIn(Schema):
    tag_ids: list[int]


class CollectionRef(Schema):
    id: int
    name: str


class CollectionOut(Schema):
    id: int
    name: str
    description: str
    cover_video_id: int | None
    cover: str | None = None
    video_count: int = 0
    archived_count: int = 0
    created_at: datetime
    updated_at: datetime


class CollectionItemOut(Schema):
    video_id: int
    position: int
    title: str
    channel_name: str | None
    duration: int | None
    local_status: str
    thumbnail: str | None


class CollectionDetailOut(CollectionOut):
    items: list[CollectionItemOut]


class CollectionIn(Schema):
    name: str = Field(..., max_length=500)
    description: str = ""


class CollectionPatch(Schema):
    name: str | None = Field(None, max_length=500)
    description: str | None = None
    cover_video_id: int | None = None
    clear_cover: bool = False


class CollectionVideoIn(Schema):
    video_id: int


class CollectionOrderIn(Schema):
    video_ids: list[int]
