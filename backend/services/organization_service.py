"""Personal tags and collections (§11, §12): local data, managed by hand."""

import re

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, OuterRef, Q, QuerySet, Subquery
from django.utils.text import slugify
from django.utils.translation import gettext

from core.models import Collection, CollectionVideo, LocalStatus, Tag, Video

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SLUG_ATTEMPTS = 100


class DuplicateName(Exception):
    """A personal tag with the same name (case-insensitive) already exists."""


class OrganizationError(ValueError):
    """Invalid input for a tag or collection operation."""


def _clean_name(name: str, max_length: int) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise OrganizationError(gettext("The name cannot be empty."))
    if len(cleaned) > max_length:
        raise OrganizationError(
            gettext("The name can have at most {max_length} characters.").format(
                max_length=max_length
            )
        )
    return cleaned


def _clean_color(color: str) -> str:
    if not COLOR_PATTERN.match(color or ""):
        raise OrganizationError(gettext("The color must be in the #RRGGBB format."))
    return color.lower()


def with_counts(queryset: QuerySet, relation: str) -> QuerySet:
    """video_count = every associated video; archived_count = those with a local copy."""
    archived = Q(**{f"{relation}__local_status": LocalStatus.AVAILABLE})
    return queryset.annotate(
        video_count=Count(relation, distinct=True),
        archived_count=Count(relation, filter=archived, distinct=True),
    )


# Tags -----------------------------------------------------------------------------------


def _unique_slug(name: str, exclude_pk: int | None = None) -> str:
    base = slugify(name)[:70] or "tag"
    others = Tag.objects.exclude(pk=exclude_pk) if exclude_pk else Tag.objects.all()
    for attempt in range(MAX_SLUG_ATTEMPTS):
        slug = base if attempt == 0 else f"{base}-{attempt + 1}"
        if not others.filter(slug=slug).exists():
            return slug
    raise OrganizationError(gettext("Cannot generate a unique slug."))


def _name_taken(name: str, exclude_pk: int | None = None) -> bool:
    others = Tag.objects.exclude(pk=exclude_pk) if exclude_pk else Tag.objects.all()
    return others.filter(name__iexact=name).exists()


def create_tag(name: str, color: str) -> Tag:
    name = _clean_name(name, 60)
    color = _clean_color(color)
    if _name_taken(name):
        raise DuplicateName(name)
    try:
        with transaction.atomic():
            return Tag.objects.create(name=name, slug=_unique_slug(name), color=color)
    except IntegrityError as exc:
        raise DuplicateName(name) from exc


def update_tag(tag: Tag, name: str | None = None, color: str | None = None) -> Tag:
    if name is not None:
        name = _clean_name(name, 60)
        if _name_taken(name, exclude_pk=tag.pk):
            raise DuplicateName(name)
        if name != tag.name:
            tag.name = name
            tag.slug = _unique_slug(name, exclude_pk=tag.pk)
    if color is not None:
        tag.color = _clean_color(color)
    try:
        with transaction.atomic():
            tag.save()
    except IntegrityError as exc:
        raise DuplicateName(tag.name) from exc
    return tag


def delete_tag(tag: Tag) -> None:
    """Removes the tag and its associations; the videos are untouched."""
    tag.delete()


def set_video_tags(video: Video, tag_ids: list[int]) -> list[Tag]:
    wanted = set(tag_ids)
    tags = list(Tag.objects.filter(pk__in=wanted))
    if len(tags) != len(wanted):
        raise OrganizationError(gettext("One or more personal tags do not exist."))
    video.tags.set(tags)
    return sorted(tags, key=lambda tag: tag.name.lower())


# Collections ----------------------------------------------------------------------------


def create_collection(name: str, description: str = "") -> Collection:
    return Collection.objects.create(name=_clean_name(name, 120), description=description or "")


def update_collection(
    collection: Collection,
    name: str | None = None,
    description: str | None = None,
    cover_video_id: int | None = None,
    clear_cover: bool = False,
) -> Collection:
    with transaction.atomic():
        collection = Collection.objects.select_for_update().get(pk=collection.pk)
        if name is not None:
            collection.name = _clean_name(name, 120)
        if description is not None:
            collection.description = description
        if clear_cover:
            collection.cover_video = None
        elif cover_video_id is not None:
            if not collection.items.filter(video_id=cover_video_id).exists():
                raise OrganizationError(gettext("The cover must be a video of the collection."))
            collection.cover_video_id = cover_video_id
        collection.save()
    return collection


def delete_collection(collection: Collection) -> None:
    """Removes the collection; its videos stay in the library."""
    collection.delete()


def _lock(collection: Collection) -> Collection:
    # Serializes every change to the positions of one collection.
    return Collection.objects.select_for_update().get(pk=collection.pk)


def add_video(collection: Collection, video: Video) -> tuple[CollectionVideo, bool]:
    """Append at the end. Returns (item, created); adding twice is a no-op."""
    with transaction.atomic():
        collection = _lock(collection)
        existing = collection.items.filter(video=video).first()
        if existing:
            return existing, False
        last = collection.items.aggregate(last=Max("position"))["last"]
        item = CollectionVideo.objects.create(
            collection=collection, video=video, position=0 if last is None else last + 1
        )
        return item, True


def remove_video(collection: Collection, video: Video) -> bool:
    with transaction.atomic():
        collection = _lock(collection)
        deleted, _ = collection.items.filter(video=video).delete()
        if collection.cover_video_id == video.pk:
            collection.cover_video = None
            collection.save(update_fields=["cover_video", "updated_at"])
        return bool(deleted)


def reorder(collection: Collection, video_ids: list[int]) -> list[CollectionVideo]:
    """Apply a new order; video_ids must be exactly the current videos, each once."""
    with transaction.atomic():
        collection = _lock(collection)
        items = {item.video_id: item for item in collection.items.all()}
        if len(video_ids) != len(set(video_ids)) or set(video_ids) != set(items):
            raise OrganizationError(
                gettext("The order must list exactly the videos of the collection, each once.")
            )
        for position, video_id in enumerate(video_ids):
            items[video_id].position = position
        CollectionVideo.objects.bulk_update(items.values(), ["position"])
        return sorted(items.values(), key=lambda item: item.position)


def collections_with_cover(queryset: QuerySet) -> QuerySet:
    """Annotate the video whose local thumbnail represents each collection.

    The chosen cover when it has a thumbnail, otherwise the first video in order that has
    one (archived or not: thumbnails are published during the download).
    """
    first_with_thumbnail = (
        CollectionVideo.objects.filter(collection=OuterRef("pk"))
        .exclude(video__thumbnail_path="")
        .order_by("position")
        .values("video_id")[:1]
    )
    return queryset.select_related("cover_video").annotate(
        first_thumbnail_video_id=Subquery(first_with_thumbnail)
    )


def cover_video_id(collection: Collection) -> int | None:
    cover = collection.cover_video
    if cover is not None and cover.thumbnail_path:
        return cover.pk
    return getattr(collection, "first_thumbnail_video_id", None)
