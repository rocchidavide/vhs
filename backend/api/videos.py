from django.db.models import Exists, F, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from ninja import Query, Router, Schema, Status
from ninja.pagination import LimitOffsetPagination, paginate

from api.media import accel_redirect
from api.schemas.common import ErrorOut
from api.schemas.organization import TagRef, VideoTagsIn
from api.schemas.videos import (
    PreparationOut,
    ProgressIn,
    ProgressOut,
    VideoListItemOut,
    VideoOut,
)
from core.models import CollectionVideo, LocalStatus, PlaybackProgress, Tag, Video
from services.media_service import MediaService, MediaUnavailable
from services.organization_service import OrganizationError, set_video_tags
from services.playback_service import (
    InvalidPlaybackState,
    PlaybackService,
    filter_by_playback_status,
    with_active_preparation,
)
from services.progress_service import get_progress, save_progress

router = Router()

ORDERINGS = {
    "-created_at": (F("created_at").desc(), "-id"),
    "title": ("title", "id"),
    "-upload_date": (F("upload_date").desc(nulls_last=True), "-id"),
    "duration": (F("duration").asc(nulls_last=True), "id"),
    "position": ("collection_position", "id"),
}


class VideoFilters(Schema):
    q: str | None = None
    channel: int | None = None
    tag: list[int] | None = None
    collection: int | None = None
    local_status: str | None = LocalStatus.AVAILABLE
    playback: str | None = None
    ordering: str | None = None


def _queryset():
    return Video.objects.select_related("channel").prefetch_related(
        Prefetch("tags", queryset=Tag.objects.order_by("name"))
    )


@router.get("/", response=list[VideoListItemOut])
@paginate(LimitOffsetPagination)
def list_videos(request, filters: Query[VideoFilters]):
    progress = PlaybackProgress.objects.filter(user=request.auth, video=OuterRef("pk"))
    queryset = with_active_preparation(_queryset()).annotate(
        progress_position=Subquery(progress.values("position_seconds")[:1]),
        progress_duration=Subquery(progress.values("duration")[:1]),
    )
    if filters.q and filters.q.strip():
        term = filters.q.strip()
        # Personal tags only: platform tags and collection names are deliberately excluded.
        tagged = Video.tags.through.objects.filter(
            video_id=OuterRef("pk"), tag__name__icontains=term
        )
        queryset = queryset.filter(
            Q(title__icontains=term)
            | Q(description__icontains=term)
            | Q(channel__name__icontains=term)
            | Exists(tagged)
        )
    if filters.channel:
        queryset = queryset.filter(channel_id=filters.channel)
    for tag_id in set(filters.tag or []):
        queryset = queryset.filter(tags__id=tag_id)
    ordering = filters.ordering or ("position" if filters.collection else "-created_at")
    if filters.collection:
        position = CollectionVideo.objects.filter(
            collection_id=filters.collection, video_id=OuterRef("pk")
        ).values("position")[:1]
        queryset = queryset.filter(collection_items__collection_id=filters.collection).annotate(
            collection_position=Subquery(position)
        )
    elif ordering == "position":
        ordering = "-created_at"
    if filters.local_status and filters.local_status != "all":
        queryset = queryset.filter(local_status=filters.local_status)
    if filters.playback:
        queryset = filter_by_playback_status(queryset, filters.playback)
    return queryset.order_by(*ORDERINGS.get(ordering, ORDERINGS["-created_at"]))


@router.get("/{video_id}", response=VideoOut)
def get_video(request, video_id: int):
    return get_object_or_404(_queryset().prefetch_related("collections"), pk=video_id)


@router.put("/{video_id}/tags", response={200: list[TagRef], 422: ErrorOut})
def put_video_tags(request, video_id: int, payload: VideoTagsIn):
    video = get_object_or_404(Video, pk=video_id)
    try:
        return set_video_tags(video, payload.tag_ids)
    except OrganizationError as exc:
        return Status(422, {"detail": str(exc), "code": "invalid"})


@router.post(
    "/{video_id}/playback/prepare",
    response={202: PreparationOut, 404: ErrorOut, 409: ErrorOut},
)
def prepare_playback(request, video_id: int):
    video = get_object_or_404(Video, pk=video_id)
    if video.local_status != LocalStatus.AVAILABLE:
        return Status(
            404, {"detail": gettext("The video is not archived."), "code": "media_unavailable"}
        )
    try:
        preparation, _ = PlaybackService().request_transcode(video.pk)
    except InvalidPlaybackState as exc:
        return Status(409, {"detail": str(exc), "code": "invalid_state"})
    return Status(202, preparation)


@router.get("/{video_id}/progress", response=ProgressOut)
def read_progress(request, video_id: int):
    video = get_object_or_404(Video, pk=video_id)
    progress = get_progress(request.auth, video)
    if progress is None:
        return {"position_seconds": 0, "duration": None, "updated_at": None}
    return progress


@router.put("/{video_id}/progress", response=ProgressOut)
def write_progress(request, video_id: int, payload: ProgressIn):
    video = get_object_or_404(Video, pk=video_id)
    return save_progress(request.auth, video, payload.position_seconds, payload.duration)


def _media_error(exc: MediaUnavailable):
    # 503 when the whole library is unavailable (e.g. folder moved), 404 otherwise.
    status = 503 if exc.code == "storage_unavailable" else 404
    return Status(status, {"detail": str(exc), "code": exc.code})


@router.get("/{video_id}/thumbnail", response={404: ErrorOut, 503: ErrorOut})
def video_thumbnail(request, video_id: int):
    video = get_object_or_404(Video, pk=video_id)
    try:
        path = MediaService().thumbnail_path(video)
    except MediaUnavailable as exc:
        return _media_error(exc)
    return accel_redirect(path, cache_control="private, max-age=3600")


@router.get("/{video_id}/stream", response={404: ErrorOut, 503: ErrorOut})
def stream_video(request, video_id: int):
    video = get_object_or_404(Video, pk=video_id)
    try:
        path = MediaService().stream_path(video)
    except MediaUnavailable as exc:
        return _media_error(exc)
    return accel_redirect(path)
