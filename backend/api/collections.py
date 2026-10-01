from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from ninja import Router, Status

from api.schemas.common import ErrorOut
from api.schemas.organization import (
    CollectionDetailOut,
    CollectionIn,
    CollectionOrderIn,
    CollectionOut,
    CollectionPatch,
    CollectionVideoIn,
)
from api.schemas.thumbnails import local_thumbnail_url
from core.models import Collection, Video
from services.organization_service import (
    OrganizationError,
    add_video,
    collections_with_cover,
    cover_video_id,
    create_collection,
    delete_collection,
    remove_video,
    reorder,
    update_collection,
    with_counts,
)

router = Router()


def _queryset():
    return collections_with_cover(with_counts(Collection.objects, "videos"))


def _serialize(collection: Collection) -> dict:
    cover_id = cover_video_id(collection)
    return {
        "id": collection.pk,
        "name": collection.name,
        "description": collection.description,
        "cover_video_id": collection.cover_video_id,
        "cover": f"/api/v1/videos/{cover_id}/thumbnail" if cover_id else None,
        "video_count": collection.video_count,
        "archived_count": collection.archived_count,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


def _detail(pk: int) -> dict:
    collection = _queryset().get(pk=pk)
    items = collection.items.select_related("video", "video__channel").order_by("position")
    return {
        **_serialize(collection),
        "items": [
            {
                "video_id": item.video_id,
                "position": item.position,
                "title": item.video.title,
                "channel_name": item.video.channel.name if item.video.channel else None,
                "duration": item.video.duration,
                "local_status": item.video.local_status,
                "thumbnail": local_thumbnail_url(item.video),
            }
            for item in items
        ],
    }


def _invalid(exc: Exception):
    return Status(422, {"detail": str(exc), "code": "invalid"})


@router.get("/", response=list[CollectionOut])
def list_collections(request):
    return [_serialize(collection) for collection in _queryset().order_by("name")]


@router.post("/", response={201: CollectionDetailOut, 422: ErrorOut})
def create(request, payload: CollectionIn):
    try:
        collection = create_collection(payload.name, payload.description)
    except OrganizationError as exc:
        return _invalid(exc)
    return Status(201, _detail(collection.pk))


@router.get("/{collection_id}", response=CollectionDetailOut)
def detail(request, collection_id: int):
    get_object_or_404(Collection, pk=collection_id)
    return _detail(collection_id)


@router.patch("/{collection_id}", response={200: CollectionDetailOut, 422: ErrorOut})
def update(request, collection_id: int, payload: CollectionPatch):
    collection = get_object_or_404(Collection, pk=collection_id)
    try:
        update_collection(
            collection,
            name=payload.name,
            description=payload.description,
            cover_video_id=payload.cover_video_id,
            clear_cover=payload.clear_cover,
        )
    except OrganizationError as exc:
        return _invalid(exc)
    return _detail(collection_id)


@router.delete("/{collection_id}", response={204: None})
def delete(request, collection_id: int):
    delete_collection(get_object_or_404(Collection, pk=collection_id))
    return Status(204, None)


@router.post(
    "/{collection_id}/videos",
    response={200: CollectionDetailOut, 201: CollectionDetailOut, 404: ErrorOut},
)
def add(request, collection_id: int, payload: CollectionVideoIn):
    collection = get_object_or_404(Collection, pk=collection_id)
    video = Video.objects.filter(pk=payload.video_id).first()
    if video is None:
        return Status(404, {"detail": gettext("Video not found."), "code": "not_found"})
    _, created = add_video(collection, video)
    return Status(201 if created else 200, _detail(collection_id))


@router.delete("/{collection_id}/videos/{int:video_id}", response={200: CollectionDetailOut})
def remove(request, collection_id: int, video_id: int):
    collection = get_object_or_404(Collection, pk=collection_id)
    remove_video(collection, get_object_or_404(Video, pk=video_id))
    return _detail(collection_id)


@router.put("/{collection_id}/videos/order", response={200: CollectionDetailOut, 422: ErrorOut})
def order(request, collection_id: int, payload: CollectionOrderIn):
    collection = get_object_or_404(Collection, pk=collection_id)
    try:
        reorder(collection, payload.video_ids)
    except OrganizationError as exc:
        return _invalid(exc)
    return _detail(collection_id)
