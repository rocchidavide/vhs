"""verify_library: read-only comparison of the database with a real library folder."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from django.core.management import call_command

from core.models import Download, DownloadStatus, LocalStatus, PlaybackPreparation, Video
from services.verification_service import Kind, LibraryVerifier, verify_library
from storage import FilesystemStorage
from storage.filesystem import MARKER_NAME

pytestmark = pytest.mark.django_db

MAIN = "youtube/chan/2024-01-01 - Clip [abc].mp4"


def write(root: Path, relative: str, content: bytes = b"video") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def archived(root: Path, relative: str = MAIN, content: bytes = b"video", **fields) -> Video:
    """A registered video whose main file (and sidecars) really exist."""
    write(root, relative, content)
    stem = relative.rsplit(".", 1)[0]
    write(root, f"{stem}.info.json", b"{}")
    write(root, f"{stem}.webp", b"img")
    platform_id = fields.pop("platform_id", relative)
    defaults = {
        "platform": "youtube",
        "platform_id": platform_id,
        "title": "Clip",
        "source_url": f"https://www.youtube.com/watch?v={platform_id}",
        "local_status": LocalStatus.AVAILABLE,
        "file_path": relative,
        "thumbnail_path": f"{stem}.webp",
        "file_size": len(content),
        "checksum_sha256": hashlib.sha256(content).hexdigest(),
    }
    return Video.objects.create(**(defaults | fields))


def kinds(report) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for finding in report.problems:
        grouped.setdefault(finding.kind, []).append(finding.path)
    return grouped


def run_command(*args) -> tuple[int, str]:
    from io import StringIO

    out = StringIO()
    try:
        call_command("verify_library", *args, stdout=out)
        code = 0
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue()


def snapshot(root: Path) -> tuple:
    """Every file with size and mtime, and every row of the models involved."""
    files = sorted(
        (str(path.relative_to(root)), path.lstat().st_size, path.lstat().st_mtime_ns)
        for path in root.rglob("*")
    )
    rows = (
        list(Video.objects.order_by("pk").values()),
        list(Download.objects.order_by("pk").values()),
        list(PlaybackPreparation.objects.order_by("pk").values()),
    )
    return files, rows


def make_download(video: Video, status: str, **fields) -> Download:
    return Download.objects.create(video=video, status=status, **fields)


# A library in order -----------------------------------------------------------------------


def test_clean_library_reports_no_problem(storage, media_root):
    video = archived(media_root)
    write(media_root, ".browser/youtube/chan/2024-01-01 - Clip [abc].mp4")
    Video.objects.filter(pk=video.pk).update(
        playback_path=".browser/youtube/chan/2024-01-01 - Clip [abc].mp4"
    )
    # A replaced original still on disk is referenced (superseded_files), not an orphan.
    write(media_root, "youtube/chan/2024-01-01 - Clip [abc].webm")
    Video.objects.filter(pk=video.pk).update(
        superseded_files=[{"path": "youtube/chan/2024-01-01 - Clip [abc].webm"}]
    )
    write(media_root, "youtube/.DS_Store")

    report = verify_library(storage, checksums=True)

    assert report.complete and report.ok
    assert report.problems == [] and report.errors == []
    assert report.videos_checked == 1
    assert report.files_scanned == 5  # marker and .DS_Store are not counted


# Database -> disk -------------------------------------------------------------------------


def test_missing_main_file_and_size_mismatch(storage, media_root):
    gone = archived(media_root, "youtube/a/gone [g].mp4", platform_id="g")
    (media_root / gone.file_path).unlink()
    resized = archived(media_root, "youtube/a/resized [r].mp4", platform_id="r")
    (media_root / resized.file_path).write_bytes(b"longer content")
    # Not archived: its absence is not a problem.
    Video.objects.create(
        platform="youtube",
        platform_id="m",
        title="M",
        source_url="https://youtu.be/m",
        local_status=LocalStatus.MISSING,
        file_path="youtube/a/m [m].mp4",
    )

    report = verify_library(storage)

    assert kinds(report) == {
        Kind.MAIN_MISSING: [gone.file_path],
        Kind.SIZE_MISMATCH: [resized.file_path],
    }
    missing = report.problems[0]
    assert missing.video_id == gone.pk
    assert report.complete and not report.ok


def test_checksum_is_compared_only_on_request(storage, media_root):
    video = archived(media_root, content=b"original")
    (media_root / video.file_path).write_bytes(b"tampered")  # same size

    assert verify_library(storage).ok
    report = verify_library(storage, checksums=True)

    assert kinds(report) == {Kind.CHECKSUM_MISMATCH: [video.file_path]}
    # The observed value is part of the finding, so two different corruptions differ.
    found = hashlib.sha256(b"tampered").hexdigest()
    assert report.problems[0].found == found
    assert report.problems[0].detail == f"found {found}"


# Disk -> database -------------------------------------------------------------------------


def test_unreferenced_files_are_reported(storage, media_root):
    archived(media_root)
    write(media_root, "youtube/chan/stray [zzz].mp4")
    write(media_root, ".browser/youtube/chan/old copy [abc].mp4")

    report = verify_library(storage)

    assert sorted(kinds(report)[Kind.UNREFERENCED]) == [
        ".browser/youtube/chan/old copy [abc].mp4",
        "youtube/chan/stray [zzz].mp4",
    ]


def test_active_temporaries_are_not_problems(storage, media_root):
    video = archived(media_root)
    running = make_download(video, DownloadStatus.DOWNLOADING)
    finished = make_download(video, DownloadStatus.FAILED)
    preparation = PlaybackPreparation.objects.create(
        video=video, kind="transcode", status="running"
    )
    old_preparation = PlaybackPreparation.objects.create(
        video=video, kind="transcode", status="failed"
    )
    write(media_root, f".incomplete/{running.pk}/part.mp4.part")
    write(media_root, f".incomplete/{finished.pk}/part.mp4.part")
    write(media_root, f".incomplete/prep-{preparation.pk}/out.mp4")
    write(media_root, f".incomplete/prep-{old_preparation.pk}/out.mp4")
    write(media_root, ".incomplete/unknown/x")
    write(media_root, ".incomplete/loose-file")

    report = verify_library(storage)

    assert sorted(kinds(report)[Kind.INCOMPLETE_ABANDONED]) == sorted(
        [
            f".incomplete/{finished.pk}",
            f".incomplete/prep-{old_preparation.pk}",
            ".incomplete/unknown",
            ".incomplete/loose-file",
        ]
    )
    assert sorted(finding.path for finding in report.active) == sorted(
        [f".incomplete/{running.pk}", f".incomplete/prep-{preparation.pk}"]
    )
    assert list(kinds(report)) == [Kind.INCOMPLETE_ABANDONED]  # nothing else flagged


def test_file_being_promoted_is_not_an_orphan(storage, media_root):
    video = archived(media_root)
    target = "youtube/chan/2024-02-02 - New [new].mp4"
    make_download(video, DownloadStatus.PROCESSING, target_path=target)
    write(media_root, target)
    write(media_root, "youtube/chan/2024-02-02 - New [new].info.json")

    report = verify_library(storage)

    assert report.ok
    assert {finding.path for finding in report.active} == {
        target,
        "youtube/chan/2024-02-02 - New [new].info.json",
    }


def test_symbolic_links_are_reported_and_never_followed(storage, media_root, tmp_path):
    outside = tmp_path / "outside"
    for index in range(3):
        write(outside, f"secret-{index}.mp4")
    video = archived(media_root)
    (media_root / "youtube" / "linked-dir").symlink_to(outside, target_is_directory=True)
    (media_root / "youtube" / "linked-file.mp4").symlink_to(outside / "secret-0.mp4")
    # A registered main file replaced by a link: reported as a link, never read through it.
    main = media_root / video.file_path
    main.unlink()
    main.symlink_to(outside / "secret-1.mp4")

    report = verify_library(storage, checksums=True)

    assert sorted(kinds(report)[Kind.SYMLINK]) == sorted(
        ["youtube/linked-dir", "youtube/linked-file.mp4", video.file_path]
    )
    assert all("secret" not in finding.path for finding in report.problems)
    assert Kind.CHECKSUM_MISMATCH not in kinds(report)


# Incomplete checks ------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["missing", "new"])
def test_unavailable_library_is_never_reported_as_fine(media_root, case):
    media_root.mkdir()
    if case == "missing":
        Video.objects.create(
            platform="youtube",
            platform_id="x",
            title="X",
            source_url="https://youtu.be/x",
            local_status=LocalStatus.AVAILABLE,
            file_path="youtube/x/x [x].mp4",
        )

    report = verify_library(FilesystemStorage(media_root))
    code, output = run_command()

    assert not report.complete and not report.ok
    assert case in report.incomplete_reason
    assert report.problems == []  # absences mean nothing without the library
    assert code == 2 and "INCOMPLETE CHECK" in output
    assert list(media_root.iterdir()) == []  # nothing created, not even the marker


def test_library_disappearing_during_the_scan_makes_the_check_incomplete(storage, media_root):
    archived(media_root)
    verifier = LibraryVerifier(storage)
    original = verifier._scan_library

    def scan_then_disappear():
        original()
        (media_root / MARKER_NAME).unlink()

    verifier._scan_library = scan_then_disappear
    report = verifier.run()

    assert not report.complete
    assert "became unavailable" in report.incomplete_reason


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs permissions")
def test_read_errors_make_the_check_incomplete(storage, media_root):
    archived(media_root)
    locked = media_root / "youtube" / "locked"
    write(locked, "inside.mp4")
    locked.chmod(0)
    try:
        report = verify_library(storage)
    finally:
        locked.chmod(0o755)

    assert not report.complete
    assert "read error" in report.incomplete_reason
    assert any("youtube/locked" in error for error in report.errors)


# Read-only --------------------------------------------------------------------------------


def test_nothing_is_modified(storage, media_root):
    video = archived(media_root, content=b"original")
    (media_root / video.file_path).write_bytes(b"tampered")
    write(media_root, "youtube/chan/stray.mp4")
    write(media_root, ".incomplete/999/part")
    missing = archived(media_root, "youtube/b/gone [g].mp4", platform_id="g")
    (media_root / missing.file_path).unlink()
    before = snapshot(media_root)

    code, _ = run_command("--checksums")

    assert code == 1
    assert snapshot(media_root) == before
    assert Video.objects.get(pk=missing.pk).local_status == LocalStatus.AVAILABLE


# Command ----------------------------------------------------------------------------------


def test_command_output_and_exit_codes(storage, media_root):
    archived(media_root)
    code, output = run_command()
    assert code == 0 and "No problem found." in output

    write(media_root, "youtube/chan/stray.mp4")
    code, output = run_command()
    assert code == 1
    assert "Files not referenced in the database (1):" in output
    assert "1 problem found. Nothing was changed." in output

    code, output = run_command("--json")
    data = json.loads(output)
    assert code == 1
    assert data["complete"] is True and data["ok"] is False
    assert data["problems"] == [
        {
            "kind": "unreferenced",
            "path": "youtube/chan/stray.mp4",
            "video_id": None,
            "detail": "",
            "found": "",
        }
    ]
