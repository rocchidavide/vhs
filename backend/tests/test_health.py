from unittest import mock

import pytest
from django.db.utils import OperationalError

from core.models import LocalStatus, Video
from storage.filesystem import MARKER_NAME

pytestmark = pytest.mark.django_db


def test_health_ok_with_an_initialized_library(client, storage):
    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["storage"] == "ok"


def test_new_local_library_is_healthy_and_not_created_by_health(client, media_root):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["storage"] == "new"
    assert response.json()["status"] == "ok"
    assert not media_root.exists()


def test_missing_library_degrades_without_failing(client, media_root):
    media_root.mkdir()
    Video.objects.create(
        platform="youtube",
        platform_id="a",
        title="A",
        source_url="https://www.youtube.com/watch?v=a",
        file_path="youtube/x/a.mp4",
        local_status=LocalStatus.AVAILABLE,
    )

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["storage"] == "missing"
    assert list(media_root.iterdir()) == []
    assert not (media_root / MARKER_NAME).exists()


def test_health_reports_database_unavailable(client, db):
    with mock.patch("api.health.connection.cursor", side_effect=OperationalError):
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["database"] == "unavailable"
