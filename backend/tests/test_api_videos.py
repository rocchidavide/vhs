from pathlib import PurePosixPath
from unittest import mock
from urllib.parse import unquote

import pytest

from core.models import LocalStatus, Video
from services.media_service import MediaService
from tests.conftest import login

pytestmark = pytest.mark.django_db

MEDIA = PurePosixPath("youtube/Canale è/2024-03-15 - Titolo [con] spazi #1 [abc].mp4")


@pytest.fixture(autouse=True)
def patched_media_service(storage):
    with mock.patch("api.videos.MediaService", return_value=MediaService(storage=storage)):
        yield


@pytest.fixture
def archived_video(storage):
    path = storage.get_path(MEDIA)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"video")
    return Video.objects.create(
        platform="youtube",
        platform_id="abc",
        title="Titolo",
        source_url="https://www.youtube.com/watch?v=abc",
        file_path=str(MEDIA),
        local_status=LocalStatus.AVAILABLE,
    )


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


def stream(client, video):
    return client.get(f"/api/v1/videos/{video.pk}/stream")


def test_stream_hands_the_transfer_to_nginx(admin_client, archived_video):
    response = stream(admin_client, archived_video)

    assert response.status_code == 200
    assert response.content == b""
    assert response["Content-Type"] == "video/mp4"
    accel = response["X-Accel-Redirect"]
    assert accel.startswith("/media-internal/")
    assert " " not in accel and "[" not in accel and "#" not in accel
    assert unquote(accel) == f"/media-internal/{MEDIA}"


def test_stream_prefers_the_browser_copy(admin_client, archived_video, storage):
    derived = PurePosixPath("youtube/Canale è/derived [abc].mp4")
    storage.get_path(derived).write_bytes(b"h264")
    archived_video.playback_path = str(derived)
    archived_video.save()

    response = stream(admin_client, archived_video)

    assert unquote(response["X-Accel-Redirect"]) == f"/media-internal/{derived}"


def test_stream_requires_authentication(client, archived_video):
    response = stream(client, archived_video)

    assert response.status_code == 401
    assert "X-Accel-Redirect" not in response


def test_stream_requires_the_admin_account(client, regular_user, archived_video):
    client.force_login(regular_user)

    assert stream(client, archived_video).status_code == 401


def test_stream_of_a_video_not_archived(admin_client, archived_video):
    archived_video.local_status = LocalStatus.ABSENT
    archived_video.save()

    response = stream(admin_client, archived_video)

    assert response.status_code == 404
    assert "X-Accel-Redirect" not in response


def test_stream_of_a_missing_file(admin_client, archived_video, storage):
    storage.delete(MEDIA)

    assert stream(admin_client, archived_video).status_code == 404


@pytest.mark.parametrize(
    "file_path",
    ["../../etc/passwd", "/etc/passwd", ".incomplete/1/abc.mp4", "youtube/../../../x.mp4"],
)
def test_stream_rejects_paths_outside_the_library(admin_client, archived_video, file_path):
    archived_video.file_path = file_path
    archived_video.save()

    response = stream(admin_client, archived_video)

    assert response.status_code == 404
    assert "X-Accel-Redirect" not in response
    assert "etc" not in response.content.decode()


def test_stream_rejects_symlinks(admin_client, archived_video, storage, tmp_path):
    outside = tmp_path / "hosts"
    outside.write_text("127.0.0.1 localhost")
    storage.get_path("youtube/escape.mp4").symlink_to(outside)
    archived_video.file_path = "youtube/escape.mp4"
    archived_video.save()

    response = stream(admin_client, archived_video)

    assert response.status_code == 404
    assert "X-Accel-Redirect" not in response


def test_video_detail(admin_client, archived_video):
    body = admin_client.get(f"/api/v1/videos/{archived_video.pk}").json()

    assert body["title"] == "Titolo"
    assert body["local_status"] == "available"
    assert "file_path" not in body


def test_video_detail_shows_the_network_and_the_audio_track(admin_client, archived_video):
    body = admin_client.get(f"/api/v1/videos/{archived_video.pk}").json()
    assert (body["network"], body["audio_language"], body["audio_kind"]) == (None, "", "")

    archived_video.platform_metadata = {"network": "Rai 3"}
    archived_video.audio_language, archived_video.audio_kind = "it", "dubbed"
    archived_video.save()

    body = admin_client.get(f"/api/v1/videos/{archived_video.pk}").json()
    assert (body["network"], body["audio_language"], body["audio_kind"]) == (
        "Rai 3",
        "it",
        "dubbed",
    )


def test_video_detail_requires_authentication(client, archived_video):
    assert client.get(f"/api/v1/videos/{archived_video.pk}").status_code == 401


def test_stream_requires_nothing_but_a_session_cookie(csrf_client, admin_user, archived_video):
    # A <video src> GET carries no CSRF header: safe methods must not require one.
    login(csrf_client, "admin")

    assert stream(csrf_client, archived_video).status_code == 200


THUMBNAIL = MEDIA.with_suffix(".webp")


@pytest.fixture
def video_with_thumbnail(archived_video, storage):
    storage.get_path(THUMBNAIL).write_bytes(b"webp")
    archived_video.thumbnail_path = str(THUMBNAIL)
    archived_video.save()
    return archived_video


def test_thumbnail_is_served_from_the_local_copy(admin_client, video_with_thumbnail):
    response = admin_client.get(f"/api/v1/videos/{video_with_thumbnail.pk}/thumbnail")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/webp"
    assert response["Cache-Control"] == "private, max-age=3600"
    assert unquote(response["X-Accel-Redirect"]) == f"/media-internal/{THUMBNAIL}"


def test_thumbnail_requires_authentication(client, video_with_thumbnail):
    assert client.get(f"/api/v1/videos/{video_with_thumbnail.pk}/thumbnail").status_code == 401


def test_thumbnail_without_local_copy_is_not_proxied(admin_client, archived_video):
    archived_video.thumbnail_url = "https://i.ytimg.com/vi/abc/hq.jpg"
    archived_video.save()

    response = admin_client.get(f"/api/v1/videos/{archived_video.pk}/thumbnail")

    assert response.status_code == 404
    assert "X-Accel-Redirect" not in response


def test_thumbnail_symlink_is_rejected(admin_client, archived_video, storage, tmp_path):
    outside = tmp_path / "secret"
    outside.write_text("secret")
    storage.get_path("youtube/escape.webp").symlink_to(outside)
    archived_video.thumbnail_path = "youtube/escape.webp"
    archived_video.save()

    assert admin_client.get(f"/api/v1/videos/{archived_video.pk}/thumbnail").status_code == 404


def test_thumbnail_url_in_video_detail(admin_client, video_with_thumbnail, archived_video):
    body = admin_client.get(f"/api/v1/videos/{video_with_thumbnail.pk}").json()

    assert body["thumbnail"] == f"/api/v1/videos/{video_with_thumbnail.pk}/thumbnail"
    assert "thumbnail_path" not in body
