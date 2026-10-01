"""Building blocks shared by background jobs (downloads, playback preparations)."""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import Model
from django.utils import timezone

logger = logging.getLogger("vhs.jobs")


def enqueue_task(func: str, *args, task_name: str) -> None:
    from django_q.tasks import async_task

    async_task(func, *args, task_name=task_name)


def touch(model: type[Model], pk: int, statuses, **fields) -> int:
    """Update a running job's fields (heartbeat included) only while it is still running."""
    fields.setdefault("last_heartbeat_at", timezone.now())
    return model.objects.filter(pk=pk, status__in=statuses).update(**fields)


class Heartbeat:
    """Background liveness signal while a job runs, also inside long ffmpeg/yt-dlp steps."""

    def __init__(self, model: type[Model], pk: int, statuses, interval: float | None = None):
        self.model = model
        self.pk = pk
        self.statuses = statuses
        self.interval = interval or settings.VHS_HEARTBEAT_INTERVAL_SECONDS
        self._stop = threading.Event()
        name = f"heartbeat-{model.__name__.lower()}-{pk}"
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        self._thread.join(timeout=5)
        return False

    def _run(self) -> None:
        try:
            while not self._stop.wait(self.interval):
                close_old_connections()
                touch(self.model, self.pk, self.statuses)
        except Exception:
            logger.exception("heartbeat failed for %s %s", self.model.__name__, self.pk)
        finally:
            connection.close()
