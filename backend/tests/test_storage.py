import errno
import hashlib
from pathlib import PurePosixPath
from unittest import mock

import pytest

from storage import FilesystemStorage, StorageConflict, StorageError

TARGET = PurePosixPath("youtube/Canale/2024-03-15 - Titolo [abc].mp4")


@pytest.fixture
def storage(tmp_path):
    library = FilesystemStorage(tmp_path / "library")
    library.create_marker(create_root=True)
    return library


def write_work_file(storage, download_id=1, name="abc.mp4", content=b"video-bytes"):
    path = storage.work_dir(download_id) / name
    path.write_bytes(content)
    return path


def test_work_dir_lives_on_the_library_filesystem(storage):
    work_dir = storage.work_dir(7)

    assert work_dir == storage.root / ".incomplete" / "7"
    assert work_dir.is_dir()
    assert storage.work_dir_ids() == {7}

    storage.remove_work_dir(7)
    assert storage.work_dir_ids() == set()


def test_finalize_promotes_the_file(storage):
    src = write_work_file(storage)

    assert storage.finalize(src, TARGET) == TARGET

    assert not src.exists()
    assert storage.exists(TARGET)
    assert storage.get_path(TARGET).read_bytes() == b"video-bytes"
    assert storage.size(TARGET) == len(b"video-bytes")


def test_finalize_accepts_an_identical_existing_file(storage):
    storage.finalize(write_work_file(storage, content=b"same"), TARGET)
    src = write_work_file(storage, content=b"same")

    storage.finalize(src, TARGET)

    assert not src.exists()
    assert storage.get_path(TARGET).read_bytes() == b"same"


def test_finalize_never_overwrites_a_different_file(storage):
    storage.finalize(write_work_file(storage, content=b"original"), TARGET)
    src = write_work_file(storage, content=b"different")

    with pytest.raises(StorageConflict):
        storage.finalize(src, TARGET)

    assert storage.get_path(TARGET).read_bytes() == b"original"
    assert src.exists()


def test_finalize_with_replace_updates_sidecars(storage):
    sidecar = PurePosixPath("youtube/Canale/x.info.json")
    storage.finalize(write_work_file(storage, name="a.json", content=b"old"), sidecar)

    storage.finalize(write_work_file(storage, name="b.json", content=b"new"), sidecar, replace=True)

    assert storage.get_path(sidecar).read_bytes() == b"new"


def test_cross_filesystem_promotion_is_refused(storage):
    src = write_work_file(storage)
    cross_device = OSError(errno.EXDEV, "Invalid cross-device link")

    with mock.patch("storage.filesystem.os.link", side_effect=cross_device):
        with pytest.raises(StorageError, match="different filesystem"):
            storage.finalize(src, TARGET)

    assert src.exists()
    assert not storage.exists(TARGET)


def test_filesystems_without_hard_links_fall_back_to_rename(storage):
    src = write_work_file(storage)
    unsupported = OSError(errno.EPERM, "Operation not permitted")

    with mock.patch("storage.filesystem.os.link", side_effect=unsupported):
        storage.finalize(src, TARGET)

    assert storage.exists(TARGET)
    assert not src.exists()


def test_write_failure_is_a_storage_error(storage):
    src = write_work_file(storage)
    no_space = OSError(errno.ENOSPC, "No space left on device")

    with mock.patch("storage.filesystem.os.link", side_effect=no_space):
        with pytest.raises(StorageError, match="No space left"):
            storage.finalize(src, TARGET)


@pytest.mark.parametrize(
    "path", ["../outside.mp4", "/etc/passwd", ".incomplete/1/abc.mp4", "youtube/../../x"]
)
def test_paths_outside_the_library_are_rejected(storage, path):
    with pytest.raises(StorageError):
        storage.get_path(path)


def test_checksum_is_sha256(storage):
    src = write_work_file(storage, content=b"x" * 3_000_000)

    assert storage.checksum(src) == hashlib.sha256(b"x" * 3_000_000).hexdigest()


def test_available_space(storage):
    assert storage.available_space() > 0


def test_media_path_of_a_regular_file(storage):
    storage.finalize(write_work_file(storage), TARGET)

    assert storage.get_media_path(TARGET) == storage.get_path(TARGET)


def test_media_path_rejects_a_symlink_outside_the_library(storage, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    link = storage.get_path("youtube/escape.mp4")
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    with pytest.raises(StorageError):
        storage.get_media_path("youtube/escape.mp4")


def test_media_path_rejects_a_symlink_inside_the_library(storage):
    storage.finalize(write_work_file(storage), TARGET)
    link = storage.get_path("youtube/alias.mp4")
    link.symlink_to(storage.get_path(TARGET))

    with pytest.raises(StorageError):
        storage.get_media_path("youtube/alias.mp4")


def test_media_path_rejects_a_symlinked_directory(storage, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "video.mp4").write_bytes(b"x")
    storage.root.mkdir(parents=True, exist_ok=True)
    (storage.root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StorageError):
        storage.get_media_path("linked/video.mp4")


def test_media_path_rejects_missing_files(storage):
    with pytest.raises(StorageError):
        storage.get_media_path(TARGET)


def test_redact_paths_hides_the_library_location(storage):
    message = f"ffprobe: {storage.root}/youtube/Canale/video.webm: Permission denied"

    redacted = storage.redact_paths(message)

    assert str(storage.root) not in redacted
    assert redacted == "ffprobe: youtube/Canale/video.webm: Permission denied"
    assert storage.redact_paths(f"cannot open {storage.root}") == "cannot open [library]"
