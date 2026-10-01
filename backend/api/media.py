"""Protected media delivery: Django authorizes, Nginx transfers the bytes (§21, §22)."""

import mimetypes
from pathlib import PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse


def accel_redirect(
    relative_path: PurePosixPath, cache_control: str = "private, no-transform"
) -> HttpResponse:
    """Hand the transfer to Nginx's internal media location, Range requests included.

    The URI is built only from a fixed prefix and a library-relative path that the
    services have already validated: no filesystem path ever leaves Django.
    """
    content_type = mimetypes.guess_type(relative_path.name)[0] or "application/octet-stream"
    response = HttpResponse(content_type=content_type)
    response["X-Accel-Redirect"] = settings.VHS_MEDIA_ACCEL_PREFIX + quote(
        str(relative_path), safe="/"
    )
    response["Cache-Control"] = cache_control
    return response
