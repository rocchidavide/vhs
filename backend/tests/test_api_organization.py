import pytest

from core.models import Channel, Collection, LocalStatus, PlaybackAction, Tag, Video
from services import organization_service as org
from tests.conftest import ago, fetch_csrf_token, login

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client(csrf_client, admin_user):
    login(csrf_client, "admin")
    csrf_client.token = fetch_csrf_token(csrf_client)
    return csrf_client


def send(client, method, path, data=None):
    return getattr(client, method)(
        path, data, content_type="application/json", headers={"X-CSRFToken": client.token}
    )


def make_video(platform_id, title, **fields):
    defaults = {
        "platform": "youtube",
        "source_url": f"https://www.youtube.com/watch?v={platform_id}",
        "local_status": LocalStatus.AVAILABLE,
        "playback_action": PlaybackAction.NATIVE,
        "probed_at": ago(minutes=1),
    }
    return Video.objects.create(platform_id=platform_id, title=title, **(defaults | fields))


@pytest.fixture
def videos():
    channel = Channel.objects.create(name="RaiUno", platform="youtube", platform_id="UC1")
    return {
        "spot": make_video(
            "a", "Sequenza 1995", channel=channel, thumbnail_path="youtube/x/a.webp",
            platform_metadata={"tags": ["pubblicità", "caroselli"]},
        ),
        "tg": make_video("b", "TG1 serale", channel=channel),
        "film": make_video("c", "Film della sera"),
        "absent": make_video("d", "Non scaricato", local_status=LocalStatus.ABSENT),
    }  # fmt: skip


def titles(response):
    return [item["title"] for item in response.json()["items"]]


# Tags -----------------------------------------------------------------------------------


def test_tag_crud(api_client, videos):
    created = send(api_client, "post", "/api/v1/tags/", {"name": "Spot", "color": "#E5A50A"})
    assert created.status_code == 201
    tag = created.json()
    assert (tag["slug"], tag["color"], tag["video_count"]) == ("spot", "#e5a50a", 0)

    duplicate = send(api_client, "post", "/api/v1/tags/", {"name": "SPOT", "color": "#000000"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate"

    invalid = send(api_client, "post", "/api/v1/tags/", {"name": "X", "color": "blu"})
    assert invalid.status_code == 422

    renamed = send(api_client, "patch", f"/api/v1/tags/{tag['id']}", {"name": "Spot TV"})
    assert renamed.json()["slug"] == "spot-tv"

    assert send(api_client, "delete", f"/api/v1/tags/{tag['id']}").status_code == 204
    assert api_client.get("/api/v1/tags/").json() == []


def test_video_tags_and_counts(api_client, videos):
    spot = org.create_tag("Spot", "#ff0000")
    anni = org.create_tag("Anni 90", "#00ff00")

    response = send(
        api_client,
        "put",
        f"/api/v1/videos/{videos['spot'].pk}/tags",
        {"tag_ids": [spot.pk, anni.pk]},
    )
    send(api_client, "put", f"/api/v1/videos/{videos['absent'].pk}/tags", {"tag_ids": [spot.pk]})

    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["Anni 90", "Spot"]
    counts = {
        t["name"]: (t["video_count"], t["archived_count"])
        for t in api_client.get("/api/v1/tags/").json()
    }
    assert counts == {"Anni 90": (1, 1), "Spot": (2, 1)}
    unknown = send(api_client, "put", f"/api/v1/videos/{videos['tg'].pk}/tags", {"tag_ids": [999]})
    assert unknown.status_code == 422


def test_video_detail_separates_personal_and_source_tags(api_client, videos):
    tag = org.create_tag("Spot", "#ff0000")
    org.set_video_tags(videos["spot"], [tag.pk])
    collection = org.create_collection("Cronosequenze")
    org.add_video(collection, videos["spot"])

    body = api_client.get(f"/api/v1/videos/{videos['spot'].pk}").json()

    assert [t["name"] for t in body["tags"]] == ["Spot"]
    assert body["source_tags"] == ["pubblicità", "caroselli"]
    assert body["collections"] == [{"id": collection.pk, "name": "Cronosequenze"}]
    assert Tag.objects.count() == 1


# Search and filters ---------------------------------------------------------------------


def test_search_includes_personal_tag_names(api_client, videos):
    carosello = org.create_tag("Carosello", "#ff0000")
    caro = org.create_tag("Carosello RAI", "#00ff00")
    org.set_video_tags(videos["tg"], [carosello.pk, caro.pk])

    assert titles(api_client.get("/api/v1/videos/?q=carosel")) == ["TG1 serale"]


def test_search_ignores_platform_tags_and_collection_names(api_client, videos):
    collection = org.create_collection("Serata speciale")
    org.add_video(collection, videos["film"])

    assert titles(api_client.get("/api/v1/videos/?q=caroselli")) == []
    assert titles(api_client.get("/api/v1/videos/?q=speciale")) == []


def test_filter_by_tags_in_and(api_client, videos):
    spot, anni = org.create_tag("Spot", "#ff0000"), org.create_tag("Anni 90", "#00ff00")
    org.set_video_tags(videos["spot"], [spot.pk, anni.pk])
    org.set_video_tags(videos["tg"], [spot.pk])

    one = titles(api_client.get(f"/api/v1/videos/?tag={spot.pk}"))
    both = titles(api_client.get(f"/api/v1/videos/?tag={spot.pk}&tag={anni.pk}"))

    assert set(one) == {"Sequenza 1995", "TG1 serale"}
    assert both == ["Sequenza 1995"]


def test_filter_by_collection_uses_its_order(api_client, videos):
    collection = org.create_collection("Serata")
    for key in ("film", "absent", "spot", "tg"):
        org.add_video(collection, videos[key])

    default = titles(api_client.get(f"/api/v1/videos/?collection={collection.pk}"))
    everything = titles(
        api_client.get(f"/api/v1/videos/?collection={collection.pk}&local_status=all")
    )
    by_title = titles(api_client.get(f"/api/v1/videos/?collection={collection.pk}&ordering=title"))

    assert default == ["Film della sera", "Sequenza 1995", "TG1 serale"]
    assert everything == ["Film della sera", "Non scaricato", "Sequenza 1995", "TG1 serale"]
    assert by_title == ["Film della sera", "Sequenza 1995", "TG1 serale"]


def test_position_ordering_without_collection_falls_back(api_client, videos):
    response = api_client.get("/api/v1/videos/?ordering=position")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 3


def test_list_query_count_does_not_grow_with_videos(
    api_client, videos, django_assert_max_num_queries
):
    tag = org.create_tag("Spot", "#ff0000")
    for index in range(15):
        video = make_video(f"x{index}", f"Extra {index}")
        org.set_video_tags(video, [tag.pk])

    with django_assert_max_num_queries(8):
        response = api_client.get("/api/v1/videos/?limit=50")

    assert len(response.json()["items"]) == 18
    assert all(
        item["tags"] for item in response.json()["items"] if item["title"].startswith("Extra")
    )


# Collections ----------------------------------------------------------------------------


def test_collection_lifecycle(api_client, videos):
    created = send(api_client, "post", "/api/v1/collections/", {"name": "Serata RaiUno"})
    assert created.status_code == 201
    cid = created.json()["id"]

    for key in ("tg", "spot", "absent"):
        added = send(
            api_client, "post", f"/api/v1/collections/{cid}/videos", {"video_id": videos[key].pk}
        )
        assert added.status_code == 201  # fmt: skip
    again = send(api_client, "post", f"/api/v1/collections/{cid}/videos",
                 {"video_id": videos["tg"].pk})  # fmt: skip
    assert again.status_code == 200

    detail = api_client.get(f"/api/v1/collections/{cid}").json()
    assert [i["title"] for i in detail["items"]] == ["TG1 serale", "Sequenza 1995", "Non scaricato"]
    assert [i["local_status"] for i in detail["items"]] == ["available", "available", "absent"]
    assert (detail["video_count"], detail["archived_count"]) == (3, 2)
    assert detail["cover"] == f"/api/v1/videos/{videos['spot'].pk}/thumbnail"

    order = [videos["absent"].pk, videos["spot"].pk, videos["tg"].pk]
    reordered = send(api_client, "put", f"/api/v1/collections/{cid}/videos/order",
                     {"video_ids": order})  # fmt: skip
    assert [i["video_id"] for i in reordered.json()["items"]] == order

    bad = send(api_client, "put", f"/api/v1/collections/{cid}/videos/order",
               {"video_ids": order[:2]})  # fmt: skip
    assert bad.status_code == 422

    removed = send(api_client, "delete", f"/api/v1/collections/{cid}/videos/{videos['tg'].pk}")
    assert [i["video_id"] for i in removed.json()["items"]] == order[:2]

    patched = send(api_client, "patch", f"/api/v1/collections/{cid}",
                   {"name": "Serata 1995", "cover_video_id": videos["spot"].pk})  # fmt: skip
    assert patched.json()["name"] == "Serata 1995"
    assert patched.json()["cover_video_id"] == videos["spot"].pk

    stranger = send(api_client, "patch", f"/api/v1/collections/{cid}",
                    {"cover_video_id": videos["film"].pk})  # fmt: skip
    assert stranger.status_code == 422

    listing = api_client.get("/api/v1/collections/").json()
    assert [c["name"] for c in listing] == ["Serata 1995"]

    assert send(api_client, "delete", f"/api/v1/collections/{cid}").status_code == 204
    assert Video.objects.filter(pk=videos["spot"].pk).exists()
    assert not Collection.objects.exists()


def test_add_unknown_video_to_collection(api_client, videos):
    collection = org.create_collection("Serata")

    response = send(api_client, "post", f"/api/v1/collections/{collection.pk}/videos",
                    {"video_id": 999})  # fmt: skip

    assert response.status_code == 404


def test_collection_without_thumbnails_has_no_cover(api_client, videos):
    collection = org.create_collection("Senza copertina")
    org.add_video(collection, videos["tg"])

    assert api_client.get("/api/v1/collections/").json()[0]["cover"] is None


def test_organization_requires_authentication_and_csrf(csrf_client, admin_user, videos):
    assert csrf_client.get("/api/v1/tags/").status_code == 401
    assert csrf_client.get("/api/v1/collections/").status_code == 401

    csrf_client.force_login(admin_user)
    response = csrf_client.post(
        "/api/v1/tags/", {"name": "Spot", "color": "#ff0000"}, content_type="application/json"
    )
    assert response.status_code == 403
