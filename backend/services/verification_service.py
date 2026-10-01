"""Read-only comparison between the database and the library folder (Phase 3, §39).

Never writes: no model is saved and no file is created, changed or removed. Symbolic links
are reported, never followed. When the library is unavailable or the scan hits read errors,
the report is marked incomplete and must not be read as "everything is fine".
"""

import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from django.utils.translation import gettext, ngettext

from core.models import (
    ACTIVE_PREPARATION_STATUSES,
    ACTIVE_STATUSES,
    Download,
    LocalStatus,
    PlaybackPreparation,
    Video,
)
from services.library_service import build_storage, library_state, tracked_paths
from services.playback_service import WORK_DIR_PREFIX
from storage import FilesystemStorage, StorageError
from storage.filesystem import INCOMPLETE_DIR, MARKER_NAME

# Files that operating systems drop into any folder: not worth reporting.
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SIDECARS = (".info.json", ".webp")


class Kind:
    MAIN_MISSING = "main_missing"
    SIZE_MISMATCH = "size_mismatch"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    UNREFERENCED = "unreferenced"
    INCOMPLETE_ABANDONED = "incomplete_abandoned"
    SYMLINK = "symlink"
    # Not a problem: a download or a preparation still running.
    INCOMPLETE_ACTIVE = "incomplete_active"


@dataclass
class Finding:
    kind: str
    path: str
    video_id: int | None = None
    detail: str = ""
    # Observed value (size in bytes or checksum): lets reports be compared without relying
    # on the wording of "detail", which follows the active language.
    found: str = ""


@dataclass
class Report:
    root: str
    checksums: bool
    complete: bool = True
    incomplete_reason: str = ""
    problems: list[Finding] = field(default_factory=list)
    active: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    videos_checked: int = 0
    files_scanned: int = 0

    @property
    def ok(self) -> bool:
        return self.complete and not self.problems

    def incomplete(self, reason: str) -> None:
        if self.complete:
            self.complete = False
            self.incomplete_reason = reason

    def as_dict(self) -> dict:
        return asdict(self) | {"ok": self.ok}


def _relative(root: Path, path: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


class LibraryVerifier:
    def __init__(self, storage: FilesystemStorage | None = None, checksums: bool = False):
        self.storage = storage or build_storage()
        self.root = Path(self.storage.root)
        self.report = Report(root=str(self.root), checksums=checksums)

    def run(self) -> Report:
        info = library_state(self.storage)
        if not self.storage.is_available():
            self.report.incomplete(
                gettext("library not available ({state}): {message}").format(
                    state=info.state, message=info.message or gettext("nothing checked")
                )
            )
            return self.report
        self._check_registered()
        self._scan_library()
        # The library may have disappeared meanwhile: absences would then mean nothing.
        if not self.storage.is_available():
            self.report.incomplete(gettext("the library became unavailable during the check"))
        if self.report.errors:
            count = len(self.report.errors)
            self.report.incomplete(
                ngettext("{count} read error", "{count} read errors", count).format(count=count)
            )
        return self.report

    # Database -> disk ---------------------------------------------------------------------

    def _check_registered(self) -> None:
        videos = (
            Video.objects.filter(local_status=LocalStatus.AVAILABLE)
            .exclude(file_path="")
            .values_list("pk", "file_path", "file_size", "checksum_sha256")
            .order_by("pk")
        )
        for video_id, file_path, file_size, checksum in videos:
            self.report.videos_checked += 1
            self._check_main(video_id, file_path, file_size, checksum)

    def _check_main(self, video_id, file_path, file_size, checksum) -> None:
        try:
            path = self.storage.get_path(file_path)
        except StorageError:
            self._problem(
                Kind.MAIN_MISSING, file_path, video_id, gettext("invalid registered path")
            )
            return
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            self._problem(Kind.MAIN_MISSING, file_path, video_id)
            return
        except OSError as exc:
            self._error(file_path, exc)
            return
        if stat.S_ISLNK(info.st_mode):
            return  # Reported by the scan, never followed.
        if not stat.S_ISREG(info.st_mode):
            self._problem(Kind.MAIN_MISSING, file_path, video_id, gettext("not a regular file"))
            return
        if file_size is not None and info.st_size != file_size:
            self._problem(
                Kind.SIZE_MISMATCH,
                file_path,
                video_id,
                gettext("{registered} bytes registered, {found} found").format(
                    registered=file_size, found=info.st_size
                ),
                found=str(info.st_size),
            )
            return
        if self.report.checksums and checksum:
            try:
                found = self.storage.checksum(path)
            except OSError as exc:
                self._error(file_path, exc)
                return
            if found != checksum:
                self._problem(
                    Kind.CHECKSUM_MISMATCH,
                    file_path,
                    video_id,
                    gettext("found {checksum}").format(checksum=found),
                    found=found,
                )

    # Disk -> database ---------------------------------------------------------------------

    def _scan_library(self) -> None:
        known = tracked_paths()
        promoting = set()
        targets = (
            Download.objects.filter(status__in=ACTIVE_STATUSES)
            .exclude(target_path="")
            .values_list("target_path", flat=True)
        )
        for target in targets:
            # Main file and sidecars are promoted before the video is registered.
            promoting |= {target, *(str(PurePosixPath(target).with_suffix(s)) for s in SIDECARS)}

        def on_error(exc: OSError) -> None:
            where = Path(exc.filename) if exc.filename else None
            inside = where is not None and where.is_relative_to(self.root)
            self._error(_relative(self.root, where) if inside else "?", exc)

        for dirpath, dirnames, filenames in os.walk(self.root, onerror=on_error):
            current = Path(dirpath)
            if current == self.root and INCOMPLETE_DIR in dirnames:
                dirnames.remove(INCOMPLETE_DIR)
                self._scan_incomplete(self.root / INCOMPLETE_DIR)
            for name in list(dirnames):
                if (current / name).is_symlink():
                    dirnames.remove(name)  # os.walk would not follow it; report it instead.
                    self._problem(Kind.SYMLINK, _relative(self.root, current / name))
            for name in filenames:
                path = current / name
                relative = _relative(self.root, path)
                if name in IGNORED_NAMES or (current == self.root and name == MARKER_NAME):
                    continue
                self.report.files_scanned += 1
                if path.is_symlink():
                    self._problem(Kind.SYMLINK, relative)
                elif relative in promoting:
                    self.report.active.append(
                        Finding(Kind.INCOMPLETE_ACTIVE, relative, detail=gettext("being promoted"))
                    )
                elif relative not in known:
                    self._problem(Kind.UNREFERENCED, relative)

    def _scan_incomplete(self, incomplete: Path) -> None:
        downloads = dict(
            Download.objects.filter(status__in=ACTIVE_STATUSES).values_list("pk", "status")
        )
        preparations = dict(
            PlaybackPreparation.objects.filter(status__in=ACTIVE_PREPARATION_STATUSES).values_list(
                "pk", "status"
            )
        )
        try:
            entries = sorted(os.scandir(incomplete), key=lambda entry: entry.name)
        except OSError as exc:
            self._error(_relative(self.root, incomplete), exc)
            return
        for entry in entries:
            relative = f"{INCOMPLETE_DIR}/{entry.name}"
            if entry.is_symlink():
                self._problem(Kind.SYMLINK, relative)
                continue
            owner = self._work_dir_owner(entry.name, downloads, preparations)
            if entry.is_dir(follow_symlinks=False) and owner:
                self.report.active.append(Finding(Kind.INCOMPLETE_ACTIVE, relative, detail=owner))
            else:
                self._problem(Kind.INCOMPLETE_ABANDONED, relative)

    @staticmethod
    def _work_dir_owner(name: str, downloads: dict, preparations: dict) -> str:
        if name.isdigit() and int(name) in downloads:
            return gettext("download {id} ({status})").format(id=name, status=downloads[int(name)])
        suffix = name.removeprefix(WORK_DIR_PREFIX)
        if name.startswith(WORK_DIR_PREFIX) and suffix.isdigit() and int(suffix) in preparations:
            return gettext("preparation {id} ({status})").format(
                id=suffix, status=preparations[int(suffix)]
            )
        return ""

    # Helpers ------------------------------------------------------------------------------

    def _problem(
        self, kind: str, path: str, video_id: int | None = None, detail: str = "", found: str = ""
    ):
        self.report.problems.append(Finding(kind, path, video_id, detail, found))

    def _error(self, path: str, exc: OSError) -> None:
        self.report.errors.append(f"{path}: {exc.strerror or exc}")


def verify_library(storage: FilesystemStorage | None = None, checksums: bool = False) -> Report:
    return LibraryVerifier(storage, checksums=checksums).run()
