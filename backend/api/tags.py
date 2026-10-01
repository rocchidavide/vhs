from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from ninja import Router, Status

from api.schemas.common import ErrorOut
from api.schemas.organization import TagIn, TagOut, TagPatch
from core.models import Tag
from services.organization_service import (
    DuplicateName,
    OrganizationError,
    create_tag,
    delete_tag,
    update_tag,
    with_counts,
)

router = Router()


def duplicate() -> dict:
    return {"detail": gettext("A personal tag with this name already exists."), "code": "duplicate"}


def _counted(pk: int) -> Tag:
    return with_counts(Tag.objects, "videos").get(pk=pk)


@router.get("/", response=list[TagOut])
def list_tags(request):
    return with_counts(Tag.objects, "videos").order_by("name")


@router.post("/", response={201: TagOut, 409: ErrorOut, 422: ErrorOut})
def create(request, payload: TagIn):
    try:
        tag = create_tag(payload.name, payload.color)
    except DuplicateName:
        return Status(409, duplicate())
    except OrganizationError as exc:
        return Status(422, {"detail": str(exc), "code": "invalid"})
    return Status(201, _counted(tag.pk))


@router.patch("/{tag_id}", response={200: TagOut, 409: ErrorOut, 422: ErrorOut})
def update(request, tag_id: int, payload: TagPatch):
    tag = get_object_or_404(Tag, pk=tag_id)
    try:
        update_tag(tag, name=payload.name, color=payload.color)
    except DuplicateName:
        return Status(409, duplicate())
    except OrganizationError as exc:
        return Status(422, {"detail": str(exc), "code": "invalid"})
    return _counted(tag.pk)


@router.delete("/{tag_id}", response={204: None})
def delete(request, tag_id: int):
    delete_tag(get_object_or_404(Tag, pk=tag_id))
    return Status(204, None)
