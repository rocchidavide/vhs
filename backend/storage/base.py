from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath


class StorageError(Exception):
    """Physical storage failure (space, permissions, cross-filesystem promotion...)."""


class StorageConflict(StorageError):
    """A different file already exists at the destination: it is never overwritten."""


class StorageUnavailable(StorageError):
    """The library is not available (not initialized or missing).

    Raised before any write, so nothing is ever created where the library is not.
    """


class Storage(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """True when the library can be read and written (root and marker present)."""

    @abstractmethod
    def unavailable_reason(self) -> str:
        """Short machine-readable reason when is_available() is False."""

    @abstractmethod
    def work_dir(self, name: int | str) -> Path:
        """Private directory for an in-progress job, on the library filesystem.

        Downloads use their numeric ID; other jobs use a prefixed name (e.g. "prep-3").
        """

    @abstractmethod
    def remove_work_dir(self, name: int | str) -> None: ...

    @abstractmethod
    def work_dir_names(self) -> set[str]:
        """Names of the work directories that currently exist."""

    def work_dir_ids(self) -> set[int]:
        """IDs of the downloads that still have a work directory."""
        return {int(name) for name in self.work_dir_names() if name.isdigit()}

    @abstractmethod
    def finalize(
        self, src: Path, relative_path: PurePosixPath, *, replace: bool = False
    ) -> PurePosixPath:
        """Atomically promote a complete file into the library; returns its relative path.

        Without `replace` an existing different file is never overwritten (StorageConflict).
        `replace` is meant for regenerable sidecars only, never for archived media.
        """

    @abstractmethod
    def exists(self, relative_path: PurePosixPath | str) -> bool: ...

    @abstractmethod
    def delete(self, relative_path: PurePosixPath | str) -> None: ...

    @abstractmethod
    def get_path(self, relative_path: PurePosixPath | str) -> Path: ...

    @abstractmethod
    def get_media_path(self, relative_path: PurePosixPath | str) -> Path:
        """Path of an existing regular library file that is safe to serve.

        Raises StorageError for symlinks (on the file or any parent below the root),
        paths resolving outside the library, and missing files.
        """

    @abstractmethod
    def size(self, relative_path: PurePosixPath | str) -> int: ...

    @abstractmethod
    def available_space(self) -> int: ...

    def redact_paths(self, text: str) -> str:
        """Hide physical library paths in messages shown to users (the API exposes IDs only)."""
        return text

    @abstractmethod
    def checksum(self, path: Path) -> str:
        """SHA-256 hex digest of a file."""
