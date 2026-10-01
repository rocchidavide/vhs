from unittest import mock

import pytest

from core.models import Download, DownloadStatus
from engine.errors import EngineError, ErrorCode
from tests.conftest import ago, fetch_csrf_token, login

URL = "https://youtu.be/jNQXAC9IVRw"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def patched_service(service):
    """Every DownloadService built by the API uses the test doubles."""
    with mock.patch("api.downloads.DownloadService", return_value=service):
        yield service


@pytest.fixture
def api_client(csrf_client, admin_user):
    login(csrf_client, "admin")
    csrf_client.token = fetch_csrf_token(csrf_client)
    return csrf_client


def post(client, path, data=None):
    return client.post(
        path,
        data or {},
        content_type="application/json",
        headers={"X-CSRFToken": client.token},
    )


def test_create_download(api_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = post(api_client, "/api/v1/downloads/", {"url": URL})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["video"]["platform_id"] == "jNQXAC9IVRw"
    assert body["video"]["channel_name"] == "jawed"
    assert body["is_stalled"] is False
    assert body["video"]["thumbnail"] is None


def test_duplicate_request_returns_the_active_download(api_client):
    first = post(api_client, "/api/v1/downloads/", {"url": URL}).json()

    response = post(
        api_client, "/api/v1/downloads/", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == first["id"]


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://127.0.0.1:8000/admin", "unsupported_url"),
        ("https://www.youtube.com/playlist?list=PL1", "playlist"),
    ],
)
def test_invalid_urls_are_client_errors(api_client, url, code):
    response = post(api_client, "/api/v1/downloads/", {"url": url})

    assert response.status_code == 400
    assert response.json()["code"] == code


def test_source_failures_are_reported_with_a_category(api_client, fake_downloader):
    fake_downloader.extract_error = EngineError(
        ErrorCode.AUTHENTICATION, "Sign in to confirm you're not a bot. Cookie: SID=topsecret"
    )

    response = post(api_client, "/api/v1/downloads/", {"url": URL})

    assert response.status_code == 502
    assert response.json()["code"] == "authentication"
    assert "topsecret" not in response.content.decode()


def test_create_requires_authentication(csrf_client, db):
    token = fetch_csrf_token(csrf_client)

    response = csrf_client.post(
        "/api/v1/downloads/",
        {"url": URL},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )

    assert response.status_code == 401


def test_create_requires_csrf(csrf_client, admin_user):
    csrf_client.force_login(admin_user)

    response = csrf_client.post("/api/v1/downloads/", {"url": URL}, content_type="application/json")

    assert response.status_code == 403


def test_list_and_detail(api_client, service):
    download, _ = service.request(URL)
    service.execute(download.pk)

    listing = api_client.get("/api/v1/downloads/?status=completed").json()
    detail = api_client.get(f"/api/v1/downloads/{download.pk}").json()

    assert listing["count"] == 1
    assert listing["items"][0]["id"] == download.pk
    assert detail["status"] == "completed"
    assert detail["video"]["local_status"] == "available"
    assert detail["video"]["thumbnail"] == f"/api/v1/videos/{detail['video']['id']}/thumbnail"
    body = str(detail)
    assert "file_path" not in body
    assert "video-library" not in body
    assert "checksum" not in body


def test_detail_not_found(api_client):
    assert api_client.get("/api/v1/downloads/999").status_code == 404


def test_stalled_downloads_are_flagged(api_client, service):
    download, _ = service.request(URL)
    Download.objects.filter(pk=download.pk).update(
        status=DownloadStatus.DOWNLOADING,
        started_at=ago(minutes=20),
        last_progress_at=ago(minutes=10),
        last_heartbeat_at=ago(seconds=5),
    )

    assert api_client.get(f"/api/v1/downloads/{download.pk}").json()["is_stalled"] is True


def test_retry(api_client, service, fake_downloader):
    download, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")
    service.execute(download.pk)

    response = post(api_client, f"/api/v1/downloads/{download.pk}/retry")

    assert response.status_code == 201
    assert response.json()["id"] != download.pk
    assert response.json()["status"] == "queued"


def test_retry_of_an_active_download_is_a_conflict(api_client, service):
    download, _ = service.request(URL)

    response = post(api_client, f"/api/v1/downloads/{download.pk}/retry")

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


def test_failed_download_keeps_showing_its_thumbnail(api_client, service, fake_downloader):
    download, _ = service.request(URL)
    fake_downloader.download_error = EngineError(ErrorCode.NETWORK, "timed out")
    service.execute(download.pk)

    body = api_client.get(f"/api/v1/downloads/{download.pk}").json()

    assert body["status"] == "failed"
    assert body["video"]["thumbnail"] == f"/api/v1/videos/{body['video']['id']}/thumbnail"
