"""Filesystem storage: a local folder, a Docker volume or a host folder bind mounted."""

import errno
import hashlib
import logging
import os
import re
import shutil
from pathlib import Path, PurePosixPath

from storage.base import Storage, StorageConflict, StorageError, StorageUnavailable

logger = logging.getLogger("vhs.storage")

INCOMPLETE_DIR = ".incomplete"
# Lives on the library itself: if the folder is replaced or moved, it is simply not there.
MARKER_NAME = ".vhs-library"
MARKER_TEXT = "VHS library. Do not delete: VHS writes only where it finds this file.\n"
_WORK_DIR_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CHUNK_SIZE = 1024 * 1024
_NO_HARDLINK_ERRNOS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EMLINK}


class FilesystemStorage(Storage):
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    # Availability -----------------------------------------------------------------------

    @property
    def marker_path(self) -> Path:
        return self.root / MARKER_NAME

    def unavailable_reason(self) -> str:
        if not self.root.is_dir():
            return "root_missing"
        if not self.marker_path.is_file():
            return "marker_missing"
        return ""

    def is_available(self) -> bool:
        return self.unavailable_reason() == ""

    def _require_available(self) -> None:
        reason = self.unavailable_reason()
        if reason:
            raise StorageUnavailable(f"Library not available ({reason}): {self.root}")

    def create_marker(self, create_root: bool = False) -> None:
        """Mark this directory as the VHS library. Only called by explicit initialization
        or by the automatic set-up of a brand-new library (library_service)."""
        if create_root:
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise StorageUnavailable(f"Library root does not exist: {self.root}")
        if not self.marker_path.exists():
            self.marker_path.write_text(
                "VHS library. Do not delete: VHS writes only where it finds this file.\n"
            )

    # Work directories -------------------------------------------------------------------

    def _incomplete_root(self) -> Path:
        return self.root / INCOMPLETE_DIR

    def _work_dir_path(self, name: int | str) -> Path:
        name = str(name)
        if not _WORK_DIR_NAME.match(name):
            raise StorageError(f"Invalid work directory name: {name!r}")
        return self._incomplete_root() / name

    def work_dir(self, name: int | str) -> Path:
        path = self._work_dir_path(name)
        self._require_available()
        # Only .incomplete/<name> inside an available library; never the root itself.
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_work_dir(self, name: int | str) -> None:
        path = self._work_dir_path(name)
        if not self.is_available():
            return  # Nothing to clean where the library is not: never touch that directory.
        shutil.rmtree(path, ignore_errors=True)

    def work_dir_names(self) -> set[str]:
        root = self._incomplete_root()
        if not self.is_available() or not root.is_dir():
            return set()
        return {entry.name for entry in root.iterdir() if _WORK_DIR_NAME.match(entry.name)}

    # Library files ----------------------------------------------------------------------

    def get_path(self, relative_path: PurePosixPath | str) -> Path:
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise StorageError(f"Invalid library path: {relative}")
        if relative.parts[0] == INCOMPLETE_DIR:
            raise StorageError("The work area is not part of the library.")
        return self.root.joinpath(*relative.parts)

    def get_media_path(self, relative_path: PurePosixPath | str) -> Path:
        path = self.get_path(relative_path)
        # VHS only writes regular files: a symlink anywhere below the root is never legitimate.
        current = self.root
        for part in PurePosixPath(relative_path).parts:
            current = current / part
            if current.is_symlink():
                raise StorageError("Symbolic links are not served from the library.")
        resolved = Path(os.path.realpath(path))
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise StorageError("The file is not available in the library.")
        return resolved

    def exists(self, relative_path: PurePosixPath | str) -> bool:
        return self.get_path(relative_path).is_file()

    def delete(self, relative_path: PurePosixPath | str) -> None:
        path = self.get_path(relative_path)
        self._require_available()
        path.unlink(missing_ok=True)

    def size(self, relative_path: PurePosixPath | str) -> int:
        return self.get_path(relative_path).stat().st_size

    def available_space(self) -> int:
        # Never creates the root: a missing root means a missing library, not a new one.
        if not self.root.is_dir():
            raise StorageUnavailable(f"Library root does not exist: {self.root}")
        return shutil.disk_usage(self.root).free

    def redact_paths(self, text: str) -> str:
        roots = {str(self.root), os.path.realpath(self.root)}
        for root in sorted(roots, key=len, reverse=True):
            text = text.replace(root + os.sep, "").replace(root, "[library]")
        return text

    def checksum(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    def finalize(
        self, src: Path, relative_path: PurePosixPath, *, replace: bool = False
    ) -> PurePosixPath:
        dst = self.get_path(relative_path)
        # Checked right before promotion. This narrows, but cannot close, the window in which
        # the library could disappear between the check and the write
        # (docs/storage-decisions.md).
        self._require_available()
        try:
            _fsync_file(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if replace:
                _replace(src, dst)
            else:
                self._promote(src, dst)
            _fsync_dir(dst.parent)
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(f"Cannot finalize {relative_path}: {exc.strerror or exc}") from exc
        return PurePosixPath(relative_path)

    def _promote(self, src: Path, dst: Path) -> None:
        if dst.exists():
            self._accept_existing(src, dst)
            return
        try:
            # link() fails if dst exists: an atomic, no-clobber promotion.
            os.link(src, dst)
        except FileExistsError:
            self._accept_existing(src, dst)
            return
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                raise StorageError(
                    "The work area is on a different filesystem than the library."
                ) from exc
            if exc.errno not in _NO_HARDLINK_ERRNOS:
                raise
            # Filesystems without hard links: same-filesystem rename.
            if dst.exists():
                self._accept_existing(src, dst)
                return
            os.rename(src, dst)
            return
        src.unlink()

    def _accept_existing(self, src: Path, dst: Path) -> None:
        """An identical file means a previous attempt already promoted it."""
        if self.checksum(src) != self.checksum(dst):
            raise StorageConflict(f"A different file already exists: {dst.name}")
        logger.info("file already promoted, keeping existing copy: %s", dst.name)
        src.unlink()


def _replace(src: Path, dst: Path) -> None:
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise StorageError(
                "The work area is on a different filesystem than the library."
            ) from exc
        raise


def _fsync_file(path: Path) -> None:
    with open(path, "rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
