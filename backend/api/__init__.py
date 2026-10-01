"""VHS public API (/api/v1/). HTTP contract independent of the Vue SPA."""

from django.contrib.admin.views.decorators import staff_member_required
from ninja import NinjaAPI
from ninja.security import SessionAuthIsStaff

from api.auth import router as auth_router
from api.channels import router as channels_router
from api.collections import router as collections_router
from api.downloads import router as downloads_router
from api.health import router as health_router
from api.tags import router as tags_router
from api.videos import router as videos_router

# Admin account session with CSRF checks; auth=None only where explicit.
api = NinjaAPI(
    title="VHS API",
    version="1",
    urls_namespace="api-v1",
    auth=SessionAuthIsStaff(),
    docs_decorator=staff_member_required,
)

api.add_router("/health", health_router, tags=["health"])
api.add_router("/auth", auth_router, tags=["auth"])
api.add_router("/downloads", downloads_router, tags=["downloads"])
api.add_router("/videos", videos_router, tags=["videos"])
api.add_router("/channels", channels_router, tags=["channels"])
api.add_router("/tags", tags_router, tags=["tags"])
api.add_router("/collections", collections_router, tags=["collections"])
