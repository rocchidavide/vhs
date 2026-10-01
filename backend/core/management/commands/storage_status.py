from django.core.management.base import BaseCommand
from django.utils.translation import gettext

from services.library_service import build_storage, library_state


class Command(BaseCommand):
    help = "Show the state of the library in VHS_MEDIA_ROOT (read-only)."

    def handle(self, *args, **options):
        storage = build_storage()
        info = library_state(storage)
        marker = gettext("present") if storage.marker_path.is_file() else gettext("absent")
        rows = [
            (gettext("Folder"), storage.root),
            (gettext("Marker"), marker),
            (gettext("State"), info.state),
        ]
        width = max(len(label) for label, _value in rows) + 2
        for label, value in rows:
            self.stdout.write(f"{label + ':':<{width}}{value}")
        if info.message:
            self.stdout.write(f"{'':<{width}}{info.message}")
