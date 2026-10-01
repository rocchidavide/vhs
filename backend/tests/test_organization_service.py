import threading
import time

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from core.models import Collection, CollectionVideo, LocalStatus, Tag, Video
from services import organization_service as org
from tests.conftest import youtube_info

pytestmark = pytest.mark.django_db


def make_video(platform_id, **fields):
    defaults = {
        "platform": "youtube",
        "title": f"Video {platform_id}",
        "source_url": f"https://www.youtube.com/watch?v={platform_id}",
        "local_status": LocalStatus.AVAILABLE,
    }
    return Video.objects.create(platform_id=platform_id, **(defaults | fields))


# Tags -----------------------------------------------------------------------------------


def test_tag_names_are_unique_ignoring_case():
    org.create_tag("Spot", "#ff0000")

    with pytest.raises(org.DuplicateName):
        org.create_tag("  spot ", "#00ff00")


def test_slugs_get_a_suffix_on_collision():
    first = org.create_tag("Anni '90", "#ff0000")
    second = org.create_tag("Anni 90", "#00ff00")

    assert first.slug == "anni-90"
    assert second.slug == "anni-90-2"


@pytest.mark.parametrize(
    ("name", "color"), [("", "#ff0000"), ("   ", "#ff0000"), ("Ok", "red"), ("Ok", "#ff00")]
)
def test_invalid_tag_input(name, color):
    with pytest.raises(org.OrganizationError):
        org.create_tag(name, color)


def test_rename_keeps_uniqueness():
    org.create_tag("Spot", "#ff0000")
    other = org.create_tag("Promo", "#00ff00")

    with pytest.raises(org.DuplicateName):
        org.update_tag(other, name="SPOT")
    org.update_tag(other, name="Promo RAI", color="#0000FF")

    other.refresh_from_db()
    assert (other.name, other.slug, other.color) == ("Promo RAI", "promo-rai", "#0000ff")


def test_set_video_tags_replaces_the_set():
    video = make_video("a")
    spot, promo = org.create_tag("Spot", "#ff0000"), org.create_tag("Promo", "#00ff00")

    org.set_video_tags(video, [spot.pk, promo.pk])
    org.set_video_tags(video, [promo.pk])

    assert list(video.tags.all()) == [promo]


def test_set_video_tags_rejects_unknown_ids():
    video = make_video("a")

    with pytest.raises(org.OrganizationError):
        org.set_video_tags(video, [999])


def test_deleting_a_tag_keeps_the_videos():
    video = make_video("a")
    tag = org.create_tag("Spot", "#ff0000")
    org.set_video_tags(video, [tag.pk])

    org.delete_tag(tag)

    assert Video.objects.filter(pk=video.pk).exists()
    assert video.tags.count() == 0


def test_platform_tags_are_never_imported(service):
    download, _ = service.request("https://youtu.be/jNQXAC9IVRw")

    assert youtube_info()["tags"]
    assert Tag.objects.count() == 0
    assert download.video.platform_metadata["tags"] == youtube_info()["tags"]


# Collections ----------------------------------------------------------------------------


@pytest.fixture
def collection():
    return org.create_collection("Cronosequenze 1995")


def positions(collection):
    return list(collection.items.order_by("position").values_list("video__platform_id", flat=True))


def test_add_video_appends_and_is_idempotent(collection):
    a, b = make_video("a"), make_video("b")

    org.add_video(collection, a)
    _, created = org.add_video(collection, b)
    _, again = org.add_video(collection, a)

    assert created and not again
    assert positions(collection) == ["a", "b"]


def test_add_after_remove_uses_the_next_position(collection):
    a, b, c = make_video("a"), make_video("b"), make_video("c")
    for video in (a, b):
        org.add_video(collection, video)
    org.remove_video(collection, a)

    item, _ = org.add_video(collection, c)

    assert item.position == 2
    assert positions(collection) == ["b", "c"]


def test_reorder_applies_a_permutation(collection):
    videos = [make_video(x) for x in "abc"]
    for video in videos:
        org.add_video(collection, video)

    org.reorder(collection, [videos[2].pk, videos[0].pk, videos[1].pk])

    assert positions(collection) == ["c", "a", "b"]
    assert list(collection.items.order_by("position").values_list("position", flat=True)) == [
        0,
        1,
        2,
    ]


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate"])
def test_reorder_requires_exactly_the_current_videos(collection, case):
    videos = [make_video(x) for x in "abc"]
    for video in videos:
        org.add_video(collection, video)
    ids = [video.pk for video in videos]
    stranger = make_video("z")
    order = {
        "missing": ids[:2],
        "extra": [*ids, stranger.pk],
        "duplicate": [ids[0], ids[0], ids[1]],
    }[case]

    with pytest.raises(org.OrganizationError):
        org.reorder(collection, order)
    assert positions(collection) == ["a", "b", "c"]


def test_removing_the_cover_clears_it(collection):
    video = make_video("a", thumbnail_path="youtube/x/a.webp")
    org.add_video(collection, video)
    org.update_collection(collection, cover_video_id=video.pk)

    org.remove_video(collection, video)

    collection.refresh_from_db()
    assert collection.cover_video is None


def test_cover_must_belong_to_the_collection(collection):
    stranger = make_video("z")

    with pytest.raises(org.OrganizationError):
        org.update_collection(collection, cover_video_id=stranger.pk)


def test_deleting_a_collection_keeps_the_videos(collection):
    video = make_video("a")
    org.add_video(collection, video)

    org.delete_collection(collection)

    assert Video.objects.filter(pk=video.pk).exists()
    assert CollectionVideo.objects.count() == 0


def test_a_video_appears_once_per_collection(collection):
    video = make_video("a")
    org.add_video(collection, video)

    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionVideo.objects.create(collection=collection, video=video, position=5)


def test_deferred_constraint_rejects_duplicate_positions_at_commit(collection):
    a, b = make_video("a"), make_video("b")

    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionVideo.objects.create(collection=collection, video=a, position=0)
        CollectionVideo.objects.create(collection=collection, video=b, position=0)
        # Deferred: checked when the transaction commits (forced here).
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_counts_and_cover(collection):
    archived = make_video("a", thumbnail_path="youtube/x/a.webp")
    absent = make_video("b", local_status=LocalStatus.ABSENT, thumbnail_path="youtube/x/b.webp")
    bare = make_video("c")
    for video in (bare, absent, archived):
        org.add_video(collection, video)

    def annotated():
        queryset = org.with_counts(Collection.objects, "videos")
        return org.collections_with_cover(queryset).get(pk=collection.pk)

    result = annotated()
    assert (result.video_count, result.archived_count) == (3, 2)
    # First video in order with a thumbnail, even when not archived.
    assert org.cover_video_id(result) == absent.pk

    org.update_collection(collection, cover_video_id=archived.pk)
    assert org.cover_video_id(annotated()) == archived.pk

    org.update_collection(collection, cover_video_id=bare.pk)
    assert org.cover_video_id(annotated()) == absent.pk


def test_cover_is_none_without_thumbnails(collection):
    org.add_video(collection, make_video("a"))

    result = org.collections_with_cover(Collection.objects).get(pk=collection.pk)

    assert org.cover_video_id(result) is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_additions_are_serialized():
    collection = org.create_collection("Concorrenza")
    first, second = make_video("a"), make_video("b")
    results = {}
    locked = threading.Event()

    def slow_add():
        # Holds the collection lock for a while before appending.
        with transaction.atomic():
            Collection.objects.select_for_update().get(pk=collection.pk)
            locked.set()
            time.sleep(0.5)
            results["first"] = org.add_video(collection, first)[0].position
        close_old_connections()
        connection.close()

    thread = threading.Thread(target=slow_add)
    thread.start()
    locked.wait(timeout=5)
    started = time.monotonic()
    results["second"] = org.add_video(collection, second)[0].position
    waited = time.monotonic() - started
    thread.join(timeout=5)

    assert waited >= 0.3
    assert sorted([results["first"], results["second"]]) == [0, 1]
    assert results["second"] == 1
