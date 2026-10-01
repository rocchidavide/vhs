"""Cookie security is configured per installation, independently of DEBUG."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import override_settings

from core.checks import insecure_cookies_check
from tests.conftest import PASSWORD

BACKEND_DIR = Path(__file__).resolve().parent.parent


def cookie_settings(**env) -> dict:
    """Import the settings in a fresh interpreter with only the given variables."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "VHS_"))}
    clean |= {"VHS_ENV_FILE": "/nonexistent/.env", "DJANGO_SECRET_KEY": "x" * 50} | env
    code = (
        "import json, config.settings as s; "
        "print(json.dumps([s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.DEBUG]))"
    )
    output = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=clean,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    session, csrf, debug = json.loads(output)
    return {"session": session, "csrf": csrf, "debug": debug}


@pytest.mark.parametrize("debug", ["true", "false"])
def test_cookies_are_secure_by_default_whatever_debug_is(debug):
    result = cookie_settings(DJANGO_DEBUG=debug)

    assert result["session"] is True
    assert result["csrf"] is True


@pytest.mark.parametrize("debug", ["true", "false"])
def test_plain_http_install_opts_out_explicitly(debug):
    result = cookie_settings(DJANGO_DEBUG=debug, DJANGO_SECURE_COOKIES="false")

    assert result["session"] is False
    assert result["csrf"] is False


def test_explicit_true_keeps_cookies_secure():
    result = cookie_settings(DJANGO_DEBUG="false", DJANGO_SECURE_COOKIES="true")

    assert result["session"] is True
    assert result["csrf"] is True


@pytest.mark.parametrize(
    ("secure", "expected"),
    [(True, True), (False, "")],
    ids=["https", "lan-http"],
)
def test_login_and_authenticated_requests(csrf_client, admin_user, secure, expected):
    origin = f"{'https' if secure else 'http'}://testserver"
    # Browsers send Origin on POST fetch requests; Django requires it (or Referer) on HTTPS.
    browser = {"secure": secure, "headers": {"Origin": origin}}

    with override_settings(SESSION_COOKIE_SECURE=secure, CSRF_COOKIE_SECURE=secure):
        csrf_response = csrf_client.get("/api/v1/auth/csrf", secure=secure)
        token = csrf_response.cookies["csrftoken"].value
        response = csrf_client.post(
            "/api/v1/auth/login",
            {"username": "admin", "password": PASSWORD},
            content_type="application/json",
            secure=secure,
            headers={"Origin": origin, "X-CSRFToken": token},
        )
        me = csrf_client.get("/api/v1/auth/me", **browser)
        token = csrf_client.cookies["csrftoken"].value
        logout = csrf_client.post(
            "/api/v1/auth/logout", secure=secure, headers={"Origin": origin, "X-CSRFToken": token}
        )
        after_logout = csrf_client.get("/api/v1/auth/me", **browser)

    assert csrf_response.cookies["csrftoken"]["secure"] == expected
    assert response.status_code == 200
    assert response.cookies["sessionid"]["secure"] == expected
    assert response.cookies["sessionid"]["httponly"] is True
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert logout.status_code == 204
    assert after_logout.status_code == 401


def test_https_rejects_cross_origin_posts(csrf_client, admin_user):
    with override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
        token = csrf_client.get("/api/v1/auth/csrf", secure=True).cookies["csrftoken"].value
        response = csrf_client.post(
            "/api/v1/auth/login",
            {"username": "admin", "password": PASSWORD},
            content_type="application/json",
            secure=True,
            headers={"Origin": "https://evil.example", "X-CSRFToken": token},
        )

    assert response.status_code == 403


@override_settings(DEBUG=False, VHS_SECURE_COOKIES=False)
def test_insecure_install_is_reported():
    assert [warning.id for warning in insecure_cookies_check(None)] == ["vhs.W001"]


@pytest.mark.parametrize(
    ("debug", "secure"), [(False, True), (True, False)], ids=["https", "development"]
)
def test_no_warning_for_https_or_development(debug, secure):
    with override_settings(DEBUG=debug, VHS_SECURE_COOKIES=secure):
        assert insecure_cookies_check(None) == []
