"""Versions and update status, for signed-in users only: unlike /health, versions are not
shown to anyone who can reach the server."""

from ninja import Router

from api.schemas.system import SystemInfoOut
from services.system_service import system_info

router = Router()


@router.get("/info", response=SystemInfoOut)
def info(request):
    return system_info()
