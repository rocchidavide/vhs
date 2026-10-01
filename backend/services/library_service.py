"""Library availability and initialization (docs/storage-decisions.md)."""

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db.models import QuerySet
from django.utils.translation import gettext, gettext_lazy

from core.models import LocalStatus, Video
from storage import FilesystemStorage, Storage

logger = logging.getLogger("vhs.library")

SAMPLE_SIZE = 20


class LibraryState:
    OK = "ok"
    NEW = "new"  # brand-new library, initialized automatically on the first write
    NOT_INITIALIZED = "not_initialized"
    MISSING = "missing"


USABLE_STATES = {LibraryState.OK, LibraryState.NEW}

# Lazy: translated in the language active when the state is read.
MESSAGES = {
    LibraryState.NOT_INITIALIZED: gettext_lazy(
        'Library not initialized: run "manage.py init_library" once.'
    ),
    LibraryState.MISSING: gettext_lazy(
        "Library not found: the registered files are not in the configured folder. "
        "Check the video library folder (VHS_HOST_LIBRARY with Docker)."
    ),
}


class LibraryInitError(Exception):
    """Explicit initialization refused; the message explains why."""


def build_storage() -> FilesystemStorage:
    return FilesystemStorage(settings.VHS_MEDIA_ROOT)


# State ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class StateInfo:
    state: str
    message: str = ""

    @property
    def usable(self) -> bool:
        return self.state in USABLE_STATES


def _archived() -> QuerySet:
    return Video.objects.exclude(file_path="")


def _registered_files_present(storage: Storage) -> bool:
    """True if at least one of the most recent registered files exists in the root."""
    sample = (
        _archived()
        .filter(local_status=LocalStatus.AVAILABLE)
        .order_by("-downloaded_at", "-id")
        .values_list("file_path", flat=True)[:SAMPLE_SIZE]
    )
    for relative in sample:
        try:
            if storage.get_path(relative).is_file():
                return True
        except Exception:  # noqa: BLE001 - an invalid stored path simply does not count
            continue
    return False


def _root_is_empty(root: Path) -> bool:
    try:
        return not any(root.iterdir())
    except OSError:
        return False


def library_state(storage: Storage | None = None) -> StateInfo:
    storage = storage or build_storage()
    if storage.is_available():
        return StateInfo(LibraryState.OK)

    root = Path(storage.root)
    has_archive = _archived().exists()
    if not root.exists() or (root.is_dir() and _root_is_empty(root)):
        if has_archive:
            return StateInfo(LibraryState.MISSING, str(MESSAGES[LibraryState.MISSING]))
        return StateInfo(LibraryState.NEW)
    if has_archive and not _registered_files_present(storage):
        return StateInfo(LibraryState.MISSING, str(MESSAGES[LibraryState.MISSING]))
    return StateInfo(LibraryState.NOT_INITIALIZED, str(MESSAGES[LibraryState.NOT_INITIALIZED]))


def prepare_for_write(storage: Storage | None = None) -> StateInfo:
    """Before writing: set up a brand-new library, otherwise just report the state.

    Never initializes a non-empty folder or a library whose videos are already registered
    in the database (a populated library that disappeared stays blocked).
    """
    storage = storage or build_storage()
    info = library_state(storage)
    if info.state == LibraryState.NEW:
        storage.create_marker(create_root=True)
        logger.info("new library initialized at %s", storage.root)
        return StateInfo(LibraryState.OK)
    return info


def initialize_library(allow_empty: bool = False, storage: Storage | None = None) -> str:
    """Explicit initialization (manage.py init_library). Returns a summary or raises."""
    storage = storage or build_storage()
    root = Path(storage.root)
    if storage.is_available():
        return gettext("The library in {root} is already initialized.").format(root=root)
    if not root.is_dir():
        raise LibraryInitError(gettext("The folder {root} does not exist.").format(root=root))
    if _archived().exists() and not _registered_files_present(storage):
        raise LibraryInitError(
            gettext(
                "The database has archived videos, but none of their files is in {root}: "
                "the folder is probably wrong or the files were moved. "
                "No option overrides this check."
            ).format(root=root)
        )
    if _root_is_empty(root) and not allow_empty:
        raise LibraryInitError(
            gettext("The folder {root} is empty. Use --allow-empty to initialize it.").format(
                root=root
            )
        )
    storage.create_marker()
    return gettext("Library initialized in {root}.").format(root=root)


def can_mark_missing(storage: Storage | None = None) -> bool:
    """A video may be marked missing only when the library itself is available."""
    return (storage or build_storage()).is_available()


def tracked_paths() -> set[str]:
    """Every library path known to the database, superseded originals included."""
    paths: set[str] = set()
    rows = Video.objects.values_list(
        "file_path", "playback_path", "thumbnail_path", "superseded_files"
    )
    for file_path, playback_path, thumbnail_path, superseded in rows:
        for value in (file_path, playback_path, thumbnail_path):
            if value:
                paths.add(value)
        if file_path:
            paths.add(str(PurePosixPath(file_path).with_suffix(".info.json")))
        for entry in superseded or []:
            if entry.get("path"):
                paths.add(entry["path"])
    return paths
