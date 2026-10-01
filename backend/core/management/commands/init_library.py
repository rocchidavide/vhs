from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext

from core.models import Video
from services.library_service import (
    LibraryInitError,
    build_storage,
    initialize_library,
    library_state,
)


class Command(BaseCommand):
    help = (
        "Explicitly mark VHS_MEDIA_ROOT as the VHS library (creates .vhs-library). "
        "Refuses when the library looks missing (registered files not found)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-empty",
            action="store_true",
            help="Initialize an empty folder (a brand-new library).",
        )

    def handle(self, *args, allow_empty, **options):
        storage = build_storage()
        root = storage.root
        rows = [(gettext("Folder"), root)]
        if root.is_dir():
            rows.append((gettext("Entries"), sum(1 for _ in root.iterdir())))
        rows.append((gettext("Archived videos"), Video.objects.exclude(file_path="").count()))
        rows.append((gettext("Current state"), library_state(storage).state))
        width = max(len(label) for label, _value in rows) + 2
        for label, value in rows:
            self.stdout.write(f"{label + ':':<{width}}{value}")
        try:
            summary = initialize_library(allow_empty=allow_empty, storage=storage)
        except LibraryInitError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(summary))
