from django.core.management.base import BaseCommand

from core.models import LocalStatus, Video
from services.playback_service import PlaybackService


class Command(BaseCommand):
    help = "Probe archived videos with ffprobe and decide what browser playback needs."

    def add_arguments(self, parser):
        parser.add_argument("video_ids", nargs="*", type=int, help="Videos to analyze.")
        parser.add_argument(
            "--all", action="store_true", help="Re-analyze every archived video, not only new ones."
        )

    def handle(self, *args, video_ids, all, **options):
        videos = Video.objects.filter(local_status=LocalStatus.AVAILABLE).exclude(file_path="")
        if video_ids:
            videos = videos.filter(pk__in=video_ids)
        elif not all:
            videos = videos.filter(probed_at__isnull=True)
        service = PlaybackService()
        for video_id, title in videos.values_list("pk", "title"):
            video = service.analyze(video_id)
            outcome = video.playback_action if video else "analysis failed"
            self.stdout.write(f"{video_id}: {outcome} — {title}")
