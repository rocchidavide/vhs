"""Single-user admin authentication through the Django session."""

from django.contrib.auth import authenticate, login, logout
from django.utils.translation import gettext
from django.views.decorators.csrf import ensure_csrf_cookie
from ninja import Router, Status
from ninja.decorators import decorate_view
from ninja.utils import check_csrf

from api.schemas.auth import LoginIn, UserOut
from api.schemas.common import ErrorOut

router = Router()


@router.get("/csrf", auth=None, response={204: None})
@decorate_view(ensure_csrf_cookie)
def csrf(request):
    """Set the `csrftoken` cookie the SPA uses for state-changing requests."""
    return Status(204, None)


@router.post("/login", auth=None, response={200: UserOut, 401: ErrorOut, 403: ErrorOut})
def login_view(request, payload: LoginIn):
    # The endpoint is unauthenticated, so the CSRF check must be done explicitly.
    if check_csrf(request) is not None:
        return Status(
            403, {"detail": gettext("Missing or invalid CSRF token."), "code": "csrf_failed"}
        )

    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None or not user.is_staff:
        return Status(
            401, {"detail": gettext("Invalid credentials."), "code": "invalid_credentials"}
        )

    login(request, user)
    return Status(200, user)


@router.post("/logout", response={204: None})
def logout_view(request):
    logout(request)
    return Status(204, None)


@router.get("/me", response=UserOut)
def me(request):
    return request.user
