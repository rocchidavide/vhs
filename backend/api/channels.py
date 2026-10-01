from django.db.models import Count, Q
from ninja import Router

from api.schemas.videos import ChannelOut
from core.models import Channel, LocalStatus

router = Router()


@router.get("/", response=list[ChannelOut])
def list_channels(request):
    """Read-only list for library filters; channel management arrives in phase 4."""
    archived = Count("videos", filter=Q(videos__local_status=LocalStatus.AVAILABLE))
    return Channel.objects.annotate(video_count=archived).filter(video_count__gt=0).order_by("name")
