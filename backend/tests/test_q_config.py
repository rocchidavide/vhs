from django.conf import settings
from django.test import override_settings

from core.checks import q_cluster_retry_check


def test_configured_retry_exceeds_timeout():
    assert settings.Q_CLUSTER["retry"] > settings.Q_CLUSTER["timeout"]
    assert q_cluster_retry_check(None) == []


def test_check_rejects_retry_not_greater_than_timeout():
    with override_settings(Q_CLUSTER={**settings.Q_CLUSTER, "timeout": 600, "retry": 600}):
        errors = q_cluster_retry_check(None)

    assert [error.id for error in errors] == ["vhs.E001"]


def test_check_rejects_missing_timeout():
    conf = {key: value for key, value in settings.Q_CLUSTER.items() if key != "timeout"}
    with override_settings(Q_CLUSTER=conf):
        errors = q_cluster_retry_check(None)

    assert [error.id for error in errors] == ["vhs.E001"]


def test_broker_is_postgresql_orm():
    assert settings.Q_CLUSTER["orm"] == "default"


def test_relative_media_root_is_resolved_against_the_project(monkeypatch):
    from config.settings import PROJECT_DIR, env_path

    monkeypatch.setenv("VHS_TEST_PATH", "./video-library")

    assert env_path("VHS_TEST_PATH", PROJECT_DIR) == PROJECT_DIR / "video-library"
