import logging

from django.db import connection
from django.db.utils import DatabaseError
from ninja import Router, Status

from api.schemas.health import HealthOut
from services.library_service import library_state

logger = logging.getLogger("vhs.api")

router = Router()


@router.get("", auth=None, response={200: HealthOut, 503: HealthOut})
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("health check: database unreachable")
        return Status(503, {"status": "error", "database": "unavailable"})
    # Read-only: reporting the library state never creates or initializes anything.
    info = library_state()
    # A missing library degrades the service but is not a reason to restart the backend.
    status = "ok" if info.usable else "degraded"
    return Status(
        200,
        {
            "status": status,
            "database": "ok",
            "storage": info.state,
            "storage_message": info.message,
        },
    )
