from django.core.management.base import BaseCommand

from services.download_service import DownloadService
from services.playback_service import PlaybackService


class Command(BaseCommand):
    help = (
        "Recover lost enqueues, interrupted downloads and preparations, videos never "
        "analyzed and leftover work directories."
    )

    def handle(self, *args, **options):
        for name, stats in (
            ("downloads", DownloadService().reconcile()),
            ("playback", PlaybackService().reconcile()),
        ):
            self.stdout.write(f"{name}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
