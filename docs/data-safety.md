# Data safety

What VHS guarantees about your videos and your data, how each guarantee is enforced and
which tests check it (in `backend/tests/`), and what VHS cannot protect you from. The details
are in the documents linked from each point.

## Where your data lives

| Data | Where | Lost if |
|---|---|---|
| Video files, thumbnails, `.info.json` metadata, browser copies | the library folder (`VHS_HOST_LIBRARY`) | the disk fails or the folder is deleted |
| Video records, checksums, personal tags, collections, watch progress, users | the PostgreSQL database, in a Docker volume | the volume is deleted (`docker compose down -v`, a Docker reset) |
| Secret key, passwords, settings | `.env`, in the VHS folder | the VHS folder is deleted |

Each of the three holds something the others cannot rebuild: back them up together
([Backup and restore](installation.md#backup-and-restore)).

## What VHS guarantees

### A file in the library is always complete

Downloads and conversions are written to a work area on the same disk as the library. Only
a finished file is promoted into the library, with an atomic hard link (or an atomic rename
on filesystems without hard links), after it has been flushed to disk. A file in the library
is never half-written, even after a crash or a power cut.

- How: [architecture.md](architecture.md) §16.
- Tests: `test_storage.py`, `test_download_service.py`.

### Every archived file has a checksum

VHS computes the SHA-256 of every archived file and keeps it in the database. A file found
again with a different checksum is never registered as the archived copy.

- Tests: `test_storage.py`, `test_reconcile.py`.

### VHS never overwrites or deletes your videos

- VHS has no function that deletes a video file: missing files, different checksums and
  files with no reference are reported, and removing anything is your choice.
- Promoting a video never overwrites a different file: if another file already sits at
  that path, the download fails and the existing file stays as it is.
- A new download of an archived video reuses its registered path; if the file name has to
  change (for example a new extension), the previous file stays recorded.
- Preparing a video for the browser never touches the original: the browser copy is a
  separate file in `.browser/`, and a failed conversion never invalidates the archived video.

Tests: `test_storage.py`, `test_redownload.py`, `test_playback_service.py`.

### VHS writes only into its own library

The library folder carries a hidden marker, `.vhs-library`. Without it VHS writes nothing:
if the folder disappears, is replaced or the path in `.env` is wrong, downloads and
conversions fail without writing, and the interface shows a warning. The marker is placed
only in a new, empty folder at the first download, or by `./vhs init-library` after
checking the videos it holds: never at startup or by a check.

- How: [The library](installation.md#the-library),
  [storage-decisions.md](storage-decisions.md) §3.
- Tests: `test_library_availability.py`.

### Nothing is reported as fine unless it was checked

`./vhs verify` compares the database with the library. It is read-only, never follows
symbolic links, and a check that could not see everything says that it is incomplete,
never that the library is in order. A video is marked missing only while the library is
available, so a disconnected disk never turns into "every video is missing".

- How: [Verifying the library](installation.md#verifying-the-library).
- Tests: `test_verification.py`, `test_redownload.py`.

### Interrupted work recovers without damage

Every background task can run again without duplicate effects. A reconciliation every 5
minutes resumes downloads that were interrupted, recovers a file that was promoted just
before a crash (only if its checksum matches) and cleans the work area. It never touches
library files.

- How: [architecture.md](architecture.md) §16.
- Tests: `test_reconcile.py`, `test_tasks.py`.

### There is room before anything is written

Before a download or a conversion, VHS checks that the library disk has room for the file
plus a reserve (`VHS_MIN_FREE_BYTES`, 1 GiB by default), and fails before writing otherwise.

- Tests: `test_download_service.py`, `test_playback_service.py`.

### A thumbnail never costs the video

The thumbnail is converted before the video is downloaded, so that it shows up early. If
the conversion fails (an image in an unexpected format, a damaged file), VHS records a
warning and downloads the video without a thumbnail: no download fails because of it.

- Tests: `test_engine_ytdlp.py`.

### A restored backup is verified

`./vhs backup` saves the database and the library together, with a verification report.
`./vhs restore` only restores into an empty installation, verifies every file with
checksums and compares the result with the report taken at backup time. VHS starts only if
the restore introduced no new problem.

- How: [Backup and restore](installation.md#backup-and-restore),
  [storage-decisions.md](storage-decisions.md) §4b.
- Tests: `test_compare_reports.py` (the outcome of a restore).

### A new installation never takes over a database in silence

The database volume outlives the VHS folder. `./vhs start` and `./vhs update` ask before
starting with a database this installation did not use (a previous installation's, a
recreated one) and before replacing a database that disappeared with an empty one.

- How: [Troubleshooting](installation.md#troubleshooting).
- Tests: the release workflow installs VHS in two folders and checks the question.

### Your library stays readable without VHS

The library is plain folders (platform, channel, date and title), with the platform's
original metadata in `.info.json` next to each video. If VHS disappears, your videos are
still ordinary files that any player opens.

## What VHS cannot protect you from

- **A failing disk.** `./vhs verify --checksums` detects damaged files, but VHS keeps one
  copy: only a backup **on another disk** protects your videos.
- **Losing the database.** VHS cannot rebuild it from the library: without a backup,
  personal tags, collections and watch progress are lost (the video files and their
  `.info.json` stay). Never run `docker compose down -v` unless you mean to delete the
  database.
- **Changes made by hand.** Files moved, edited or deleted outside VHS are reported by
  `./vhs verify`, not prevented.
- **Checks you do not run.** VHS does not verify the library on a schedule yet: run
  `./vhs verify` from time to time, and `--checksums` after a disk problem.
- **A library that disappears during a write.** VHS checks the library right before
  every write, which narrows this window but cannot close it
  ([storage-decisions.md](storage-decisions.md) §4).
- **Network storage.** NFS and SMB shares are not supported for the library yet
  ([storage-decisions.md](storage-decisions.md) §5–§6).
- **Bypassing `./vhs`.** `docker compose up -d` does not check which database it uses.
- **`.env`.** It is not part of the backup: keep a copy of it separately.
