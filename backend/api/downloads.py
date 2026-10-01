from django.shortcuts import get_object_or_404
from ninja import Query, Router, Schema, Status
from ninja.pagination import LimitOffsetPagination, paginate

from api.schemas.common import ErrorOut
from api.schemas.downloads import DownloadIn, DownloadOut
from core.models import Download, DownloadStatus
from engine.errors import EngineError, ErrorCode
from services.download_service import AlreadyArchived, DownloadService, InvalidDownloadState

router = Router()

CLIENT_ERRORS = {ErrorCode.UNSUPPORTED_URL, ErrorCode.PLAYLIST}


class DownloadFilters(Schema):
    status: DownloadStatus | None = None


def _queryset():
    return Download.objects.select_related("video", "video__channel")


def _already_archived(exc: AlreadyArchived):
    return Status(409, {"detail": str(exc), "code": "already_archived", "video_id": exc.video.pk})


@router.post(
    "/",
    response={200: DownloadOut, 201: DownloadOut, 400: ErrorOut, 409: ErrorOut, 502: ErrorOut},
)
def create_download(request, payload: DownloadIn):
    try:
        download, created = DownloadService().request(payload.url)
    except AlreadyArchived as exc:
        return _already_archived(exc)
    except EngineError as exc:
        status = 400 if exc.code in CLIENT_ERRORS else 502
        return Status(status, {"detail": exc.message, "code": str(exc.code)})
    return Status(201 if created else 200, _queryset().get(pk=download.pk))


@router.get("/", response=list[DownloadOut])
@paginate(LimitOffsetPagination)
def list_downloads(request, filters: Query[DownloadFilters]):
    queryset = _queryset()
    if filters.status:
        queryset = queryset.filter(status=filters.status)
    return queryset


@router.get("/{download_id}", response=DownloadOut)
def get_download(request, download_id: int):
    return get_object_or_404(_queryset(), pk=download_id)


@router.post("/{download_id}/retry", response={200: DownloadOut, 201: DownloadOut, 409: ErrorOut})
def retry_download(request, download_id: int):
    get_object_or_404(Download, pk=download_id)
    try:
        download, created = DownloadService().retry(download_id)
    except AlreadyArchived as exc:
        return _already_archived(exc)
    except InvalidDownloadState as exc:
        return Status(409, {"detail": str(exc), "code": "invalid_state"})
    return Status(201 if created else 200, _queryset().get(pk=download.pk))
