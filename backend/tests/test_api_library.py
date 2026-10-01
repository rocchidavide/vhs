from datetime import date
from unittest import mock

import pytest

from core.models import (
    Channel,
    LocalStatus,
    PlaybackAction,
    PlaybackPreparation,
    PlaybackProgress,
    PreparationKind,
    Video,
)
from services.playback_service import PlaybackService
from tests.conftest import RecordingEnqueue, ago, fetch_csrf_token, login

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client(csrf_client, admin_user):
    login(csrf_client, "admin")
    csrf_client.token = fetch_csrf_token(csrf_client)
    return csrf_client


@pytest.fixture(autouse=True)
def playback_service(storage):
    service = PlaybackService(
        storage=storage,
        enqueue_preparation=RecordingEnqueue(),
        enqueue_analysis=RecordingEnqueue(),
    )
    with (
        mock.patch("api.videos.PlaybackService", return_value=service),
        mock.patch("api.schemas.videos.PlaybackService", return_value=service),
    ):
        yield service


def make_video(platform_id, title, channel=None, **fields):
    defaults = {
        "platform": "youtube",
        "source_url": f"https://www.youtube.com/watch?v={platform_id}",
        "local_status": LocalStatus.AVAILABLE,
        "file_path": f"youtube/x/{platform_id}.mp4",
        "playback_action": PlaybackAction.NATIVE,
        "probed_at": ago(minutes=1),
    }
    return Video.objects.create(
        platform_id=platform_id, title=title, channel=channel, **(defaults | fields)
    )


@pytest.fixture
def library():
    rai = Channel.objects.create(name="RaiUno", platform="youtube", platform_id="UC1")
    other = Channel.objects.create(name="Altro", platform="youtube", platform_id="UC2")
    return {
        "spot": make_video(
            "a", "Sequenza spot 1995", rai, upload_date=date(2018, 5, 8), duration=300
        ),
        "tg": make_video(
            "b", "TG1 edizione serale", rai, upload_date=date(2020, 1, 1), duration=60
        ),
        "zoo": make_video(
            "c", "Me at the zoo", other, duration=19, playback_action=PlaybackAction.TRANSCODE
        ),
        "absent": make_video(
            "d", "Non scaricato", other, local_status=LocalStatus.ABSENT, file_path=""
        ),
    }


def titles(response):
    return [item["title"] for item in response.json()["items"]]


def test_library_lists_archived_videos_by_default(api_client, library):
    response = api_client.get("/api/v1/videos/")

    assert response.status_code == 200
    assert set(titles(response)) == {"Sequenza spot 1995", "TG1 edizione serale", "Me at the zoo"}


def test_search_matches_title_description_and_channel(api_client, library):
    assert titles(api_client.get("/api/v1/videos/?q=spot")) == ["Sequenza spot 1995"]
    assert set(titles(api_client.get("/api/v1/videos/?q=raiuno"))) == {
        "Sequenza spot 1995",
        "TG1 edizione serale",
    }


def test_filter_by_channel_and_status(api_client, library):
    channel_id = library["zoo"].channel_id

    assert titles(api_client.get(f"/api/v1/videos/?channel={channel_id}")) == ["Me at the zoo"]
    assert titles(api_client.get("/api/v1/videos/?local_status=absent")) == ["Non scaricato"]
    assert len(titles(api_client.get("/api/v1/videos/?local_status=all"))) == 4


def test_filter_by_playback_status(api_client, library):
    assert titles(api_client.get("/api/v1/videos/?playback=unavailable")) == ["Me at the zoo"]
    assert "Me at the zoo" not in titles(api_client.get("/api/v1/videos/?playback=ready"))


def test_ordering(api_client, library):
    assert titles(api_client.get("/api/v1/videos/?ordering=-upload_date"))[:2] == [
        "TG1 edizione serale",
        "Sequenza spot 1995",
    ]
    assert titles(api_client.get("/api/v1/videos/?ordering=duration"))[0] == "Me at the zoo"
    assert titles(api_client.get("/api/v1/videos/?ordering=title"))[0] == "Me at the zoo"


def test_list_items_carry_playback_status_and_progress(api_client, library, admin_user):
    PlaybackProgress.objects.create(
        user=admin_user, video=library["spot"], position_seconds=120, duration=300
    )
    PlaybackPreparation.objects.create(video=library["tg"], kind=PreparationKind.REMUX)
    library["tg"].playback_action = PlaybackAction.REMUX
    library["tg"].save()

    items = {i["title"]: i for i in api_client.get("/api/v1/videos/").json()["items"]}

    assert items["Sequenza spot 1995"]["progress_position"] == 120
    assert items["Sequenza spot 1995"]["playback_status"] == "ready"
    assert items["TG1 edizione serale"]["playback_status"] == "preparing"
    assert items["Me at the zoo"]["playback_status"] == "unavailable"
    assert items["Me at the zoo"]["progress_position"] is None


def test_progress_is_per_user(api_client, library, regular_user):
    PlaybackProgress.objects.create(user=regular_user, video=library["spot"], position_seconds=99)

    items = {i["title"]: i for i in api_client.get("/api/v1/videos/").json()["items"]}

    assert items["Sequenza spot 1995"]["progress_position"] is None


def test_pagination(api_client, library):
    body = api_client.get("/api/v1/videos/?limit=2").json()

    assert body["count"] == 3
    assert len(body["items"]) == 2


def test_channels_for_filters(api_client, library):
    channels = api_client.get("/api/v1/channels/").json()

    assert [(c["name"], c["video_count"]) for c in channels] == [("Altro", 1), ("RaiUno", 2)]


def test_library_requires_authentication(client, library):
    assert client.get("/api/v1/videos/").status_code == 401
    assert client.get("/api/v1/channels/").status_code == 401


# Video detail and preparation -----------------------------------------------------------


def post(client, path, **kwargs):
    return client.post(path, headers={"X-CSRFToken": client.token}, **kwargs)


def test_detail_exposes_the_playback_state(api_client, library):
    body = api_client.get(f"/api/v1/videos/{library['zoo'].pk}").json()

    assert body["playback"]["status"] == "unavailable"
    assert body["playback"]["can_prepare"] is True
    assert body["playback"]["action"] == "transcode"
    assert body["playback"]["preparation"] is None
    # Stable codes with their parameters: the UI translates them, "reason" is a detail.
    assert body["playback"]["issues"] == library["zoo"].playback_issues


def test_playback_issues_keep_their_parameters(api_client, library):
    video = library["zoo"]
    video.playback_issues = [{"code": "video_codec", "codec": "VP9"}]
    video.save(update_fields=["playback_issues"])

    body = api_client.get(f"/api/v1/videos/{video.pk}").json()

    assert body["playback"]["issues"] == [{"code": "video_codec", "codec": "VP9"}]


def test_prepare_starts_a_conversion(api_client, library):
    response = post(api_client, f"/api/v1/videos/{library['zoo'].pk}/playback/prepare")

    assert response.status_code == 202
    assert response.json()["kind"] == "transcode"
    detail = api_client.get(f"/api/v1/videos/{library['zoo'].pk}").json()
    assert detail["playback"]["status"] == "preparing"


def test_prepare_is_refused_when_not_needed(api_client, library):
    response = post(api_client, f"/api/v1/videos/{library['spot'].pk}/playback/prepare")

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


def test_prepare_of_a_video_not_archived(api_client, library):
    response = post(api_client, f"/api/v1/videos/{library['absent'].pk}/playback/prepare")

    assert response.status_code == 404


def test_prepare_requires_csrf(csrf_client, admin_user, library):
    csrf_client.force_login(admin_user)

    response = csrf_client.post(f"/api/v1/videos/{library['zoo'].pk}/playback/prepare")

    assert response.status_code == 403


# Playback progress ----------------------------------------------------------------------


def put_progress(client, video, **payload):
    return client.put(
        f"/api/v1/videos/{video.pk}/progress",
        payload,
        content_type="application/json",
        headers={"X-CSRFToken": client.token},
    )


def test_progress_defaults_to_the_beginning(api_client, library):
    body = api_client.get(f"/api/v1/videos/{library['spot'].pk}/progress").json()

    assert body == {"position_seconds": 0, "duration": None, "updated_at": None}


def test_progress_is_saved_and_updated(api_client, library, admin_user):
    first = put_progress(api_client, library["spot"], position_seconds=61.5, duration=300)
    put_progress(api_client, library["spot"], position_seconds=90, duration=300)

    body = api_client.get(f"/api/v1/videos/{library['spot'].pk}/progress").json()
    assert first.status_code == 200
    assert body["position_seconds"] == 90
    assert body["duration"] == 300
    assert PlaybackProgress.objects.filter(user=admin_user).count() == 1


def test_progress_is_clamped_to_the_duration(api_client, library):
    body = put_progress(api_client, library["spot"], position_seconds=999, duration=300).json()

    assert body["position_seconds"] == 300


@pytest.mark.parametrize("payload", [{"position_seconds": -1}, {"position_seconds": "abc"}, {}])
def test_invalid_progress_is_rejected(api_client, library, payload):
    assert put_progress(api_client, library["spot"], **payload).status_code == 422


def test_progress_requires_authentication_and_csrf(csrf_client, admin_user, library):
    video = library["spot"]
    assert csrf_client.get(f"/api/v1/videos/{video.pk}/progress").status_code == 401

    csrf_client.force_login(admin_user)
    response = csrf_client.put(
        f"/api/v1/videos/{video.pk}/progress",
        {"position_seconds": 10},
        content_type="application/json",
    )
    assert response.status_code == 403
