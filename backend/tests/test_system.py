import io
import json
from unittest import mock

import pytest
from django.core.cache import cache

from services import system_service
from services.system_service import Release, update_available
from tests.conftest import login

pytestmark = pytest.mark.django_db

RELEASE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/rocchidavide/vhs/releases/tag/v0.2.0",
}


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def github_answers(payload):
    response = io.BytesIO(json.dumps(payload).encode())
    response.__enter__ = lambda self: self
    response.__exit__ = lambda self, *args: None
    return mock.patch("urllib.request.urlopen", return_value=response)


def test_versions_need_a_signed_in_user(client):
    assert client.get("/api/v1/system/info").status_code == 401


def test_health_does_not_reveal_versions(client):
    body = client.get("/api/v1/health").json()
    assert not any("version" in key for key in body)


def test_system_info_reports_the_versions(client, admin_user, settings):
    settings.VHS_UPDATE_CHECK = False
    login(client, "admin")

    body = client.get("/api/v1/system/info").json()

    assert body["vhs_version"] == system_service.vhs_version() != ""
    assert body["ytdlp_version"]  # the real yt-dlp of the image
    assert body["ytdlp_auto_update"] is False
    assert body["latest_version"] is None and body["update_available"] is False


@pytest.mark.parametrize(
    ("current", "latest", "expected"),
    [
        ("0.1.1", "0.2.0", True),
        ("0.1.1", "0.1.1", False),
        ("0.2.0", "0.1.9", False),
        ("0.1.9", "0.1.10", True),
        ("", "0.2.0", False),
        ("0.1.1", "nightly", False),
    ],
)
def test_update_available(current, latest, expected):
    assert update_available(current, Release(latest, "https://github.com/x")) is expected


def test_latest_release_is_asked_once_and_cached(settings):
    settings.VHS_UPDATE_CHECK = True
    with github_answers(RELEASE) as urlopen:
        first = system_service.latest_release()
        second = system_service.latest_release()

    assert first == second == Release("0.2.0", RELEASE["html_url"])
    assert urlopen.call_count == 1
    request = urlopen.call_args.args[0]
    assert request.full_url == system_service.UPDATE_CHECK_URL
    assert request.get_header("User-agent").startswith("VHS/")


def test_a_failed_check_is_not_retried_at_every_request(settings):
    settings.VHS_UPDATE_CHECK = True
    with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")) as urlopen:
        assert system_service.latest_release() is None
        assert system_service.latest_release() is None
    assert urlopen.call_count == 1


def test_unexpected_answers_are_ignored(settings):
    settings.VHS_UPDATE_CHECK = True
    with github_answers({"tag_name": "v0.2.0", "html_url": "https://evil.example/x"}):
        assert system_service.latest_release() is None


def test_no_request_when_the_check_is_off(settings):
    settings.VHS_UPDATE_CHECK = False
    with mock.patch("urllib.request.urlopen") as urlopen:
        assert system_service.latest_release() is None
    urlopen.assert_not_called()


def test_new_version_is_announced(client, admin_user, settings):
    settings.VHS_UPDATE_CHECK = True
    login(client, "admin")
    with (
        github_answers(RELEASE),
        mock.patch.object(system_service, "vhs_version", return_value="0.1.1"),
    ):
        body = client.get("/api/v1/system/info").json()

    assert body["update_available"] is True
    assert (body["latest_version"], body["latest_release_url"]) == ("0.2.0", RELEASE["html_url"])
