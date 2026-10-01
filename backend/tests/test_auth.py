from tests.conftest import fetch_csrf_token, login


def test_login_as_admin(csrf_client, admin_user):
    response = login(csrf_client, "admin")

    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert csrf_client.get("/api/v1/auth/me").json()["username"] == "admin"


def test_login_rejects_wrong_password(csrf_client, admin_user):
    response = login(csrf_client, "admin", password="wrong")

    assert response.status_code == 401


def test_login_rejects_non_staff_user(csrf_client, regular_user):
    response = login(csrf_client, "guest")

    assert response.status_code == 401


def test_login_requires_csrf_token(csrf_client, admin_user):
    response = csrf_client.post(
        "/api/v1/auth/login",
        {"username": "admin", "password": "correct-horse-battery"},
        content_type="application/json",
    )

    assert response.status_code == 403


def test_me_requires_authentication(csrf_client, db):
    assert csrf_client.get("/api/v1/auth/me").status_code == 401


def test_non_staff_session_is_not_authorized(csrf_client, regular_user):
    csrf_client.force_login(regular_user)

    assert csrf_client.get("/api/v1/auth/me").status_code == 401


def test_logout_requires_csrf_token(csrf_client, admin_user):
    csrf_client.force_login(admin_user)

    assert csrf_client.post("/api/v1/auth/logout").status_code == 403
    assert csrf_client.get("/api/v1/auth/me").status_code == 200


def test_logout(csrf_client, admin_user):
    login(csrf_client, "admin")
    token = fetch_csrf_token(csrf_client)

    response = csrf_client.post("/api/v1/auth/logout", headers={"X-CSRFToken": token})

    assert response.status_code == 204
    assert csrf_client.get("/api/v1/auth/me").status_code == 401


def test_openapi_docs_require_admin(client, admin_user):
    assert client.get("/api/v1/docs").status_code == 302

    client.force_login(admin_user)
    assert client.get("/api/v1/docs").status_code == 200


def test_errors_have_codes_and_follow_the_available_languages(csrf_client, admin_user):
    token = fetch_csrf_token(csrf_client)
    response = csrf_client.post(
        "/api/v1/auth/login",
        {"username": "admin", "password": "wrong"},
        content_type="application/json",
        headers={"X-CSRFToken": token, "Accept-Language": "it-IT,it;q=0.9"},
    )

    assert response.status_code == 401
    # English is the only language for now: an Italian browser still gets English texts.
    body = response.json()
    assert (body["detail"], body["code"]) == ("Invalid credentials.", "invalid_credentials")
    assert response["Content-Language"] == "en"
