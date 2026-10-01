# Library storage decisions

This document records the **reasoning** behind how the library is handled when its folder
is missing, wrong or disappears, and the **limits** that remain. It also records the work
done and then removed on network storage (NFS) and the criteria for resuming it. The
operational commands are in [installation.md](installation.md); the rules the code must
follow are in [conventions.md](conventions.md); the overall picture is in §15 of
[architecture.md](architecture.md).

## 1. MVP scope

The MVP supports **only local storage**, always in a regular folder:

- a **host folder** on the server's disk, which must be specified with
  `VHS_HOST_LIBRARY` and is mounted in the containers as `/srv/video-library`
  (`VHS_MEDIA_ROOT`, fixed in the containers);
- this applies to installations (for example `/srv/vhs/library`) and to development
  (`./video-library`), which also runs in containers.

**Why a folder and not a Docker volume.** Videos are user data: in a folder chosen by
whoever installs VHS they stay visible and browsable, they can live on a dedicated disk,
they are backed up by copying them, and they do not disappear with a
`docker compose down -v`. A volume would hide them in Docker's internal area, on the
system disk. The volume remains only for PostgreSQL, whose files are not touched by hand.
Until this decision the volume was the default for the library; it was removed so that
there is only one way to configure it.

**Network shares (NFS, SMB, NAS) and separately mounted disks are not supported in the
MVP.** A dedicated mode was implemented, tested and then removed to keep complexity down
(§5); the criteria for resuming it are in §6.

## 2. The failures we want to avoid

**Writing in the wrong place.** If the library is not where VHS expects it (folder renamed
or moved, wrong `VHS_HOST_LIBRARY` after an update, folder replaced), an empty folder in its
place must not become a new library:

- a download would create `.incomplete/`, sidecars and the **video file** in a folder that
  nobody considers the library;
- the database would point to paths that do not exist in the real library, or vice versa;
- a disk's space would fill up without anyone noticing.

Before this work VHS fell into this trap: `available_space()` created the root,
`work_dir()` created `.incomplete/` with all its parent directories, and `finalize()`
created the destination folders.

**Losing track of the main file.** A new download of an already registered video, with a
changed title, could compute a new path and leave the old file on disk with no reference
to it (§39, Phase 3).

**Confusing "library gone" with "new library".** An empty folder can be the start of a
library or a library that no longer exists. Treating the second as the first means
starting to write in the wrong place again.

## 3. MVP protections

**The marker** (`.vhs-library`, in the library root) says "this is the library". It lives
**on the library itself**: if the folder is replaced or moved, the marker is not there in
its place.

- VHS writes only where it finds the marker. The check is **in the storage**
  (`FilesystemStorage._require_available()` before `work_dir`, `finalize`, `delete`), not
  left to each service remembering it: even new code cannot write to an unavailable
  library.
- The storage **never creates the root**, with a single exception: the new library,
  created explicitly by `prepare_for_write()`.
- The marker is created only explicitly (`init_library`) or for the new library; never by
  migrate, startup, reconciliations or health.

**New library and missing library.**

- A **truly new** library (no archived video in the database, folder absent or empty) is
  initialized **automatically** on the first download: no configuration for whoever
  installs VHS.
- An **already populated** library that disappears stays **blocked** (`missing`): the
  database says files existed, so an empty folder is not a new library.
- A non-empty folder without a marker (for example an installation predating this work) is
  `not_initialized` and is initialized once with `init_library`, which checks that the
  registered files are actually there.

**With the library unavailable:** downloads and preparations fail with
`error_code=storage` before touching the storage; streams and thumbnails respond 503;
`/health` responds `degraded`; reconciliations are skipped; the `vhs.W002` system check
and a banner in the UI show the reason and the command. `manage.py storage_status` shows
the folder, the marker and the status.

**Host folder with Compose.** `docker-compose.yml` mounts `VHS_HOST_LIBRARY` with a
long-syntax bind mount and `create_host_path: false`, read-write in `migrate`, `backend`
and `worker`, read-only in `nginx`. Without the variable, Compose stops with an error; if
the folder does not exist on the host, Docker does not create the containers and does not
create the folder (a short-syntax bind would create it empty, and VHS would treat it as a
new library). An empty folder becomes a new library on the first download; a folder with
files in it requires `init_library`.

## 4. MVP limits

- **Between the check and the write.** `finalize` runs the check again before promoting a
  file; this reduces the risk of writing in the wrong place but does not eliminate it: the
  folder can disappear between the check and the write.
- **A transfer already in progress can leave temporary files where the library used to
  be.** yt-dlp creates output directories on its own: if the library disappears midway
  (folder moved), it can recreate `.incomplete/<id>` and keep writing there. The check
  before promotion prevents those files from entering the library or the database
  (download `failed/storage`), but the temporary files remain and must be removed by hand.
  This behavior is covered by a test that simulates the directory being recreated. With
  local storage the case is rare; with a network share that disappears it is the typical
  case, and it is one of the reasons NFS is outside the MVP (§6).
- **Library on an unsupported mount.** Anyone who puts the library on a share or on a
  separately mounted disk anyway is protected only by the marker, which lives on the
  mount: with videos already archived, a missing mount blocks VHS (`missing`). Still
  uncovered are the **first installation** with the mount absent (the empty local folder
  looks like a new library) and the mount disappearing during a download (previous point).
- **Reconciliation.** With the library unavailable, reconciliations do not mark
  `interrupted`, do not register promoted files and do not clean up work dirs: they act
  only when the library becomes available again.

## 4b. Backup: consistency and deferred choices

- **Who writes to the library:** only the worker's tasks (downloads, preparations,
  periodic reconciliation) and the `migrate` service at startup, besides commands run by
  hand (`init_library`, which creates the marker). The backup therefore
  stops only the worker, after checking that no jobs are running, and checks again after
  the stop: a job started in the meantime would have been interrupted, and the backup
  stops. The worker is restarted as a container, not with `docker compose start`, which
  would rerun `migrate` and its reconciliation.
- **Order:** first the database dump, then the file copy. A file that appeared after the
  dump can only end up without a reference, never missing.
- **Restore outcome:** the `verify_library --checksums` reports taken at backup time and
  after the restore are compared. A problem is identified by type, path and observed value
  (size or checksum found): a file that was already different at backup time and is
  different in another way after the restore counts as new. The comparison lives only in
  the restore procedure; the exit codes of `verify_library` do not change.
- **Deferred:** `rsync --link-dest`. Hard links would save space, but they tie the files
  of later backups to those of earlier ones and add cases to handle (attributes that must
  match for the linking to happen). In the MVP every backup is a full copy.

## 5. Network storage: the work done and removed

The mounted mode was implemented in commit `207fc9a` and removed in the following
simplification commit, `a9dbf01`. Both belong to the development history before the
first public release, kept in a private archive of the maintainer: the code can be
recovered from there (`library_service.py`, `docker-compose.mounted.yml`, tests in
`test_library_availability.py`).

**How it worked.**

- It was enabled with `VHS_STORAGE_MODE=mounted` and by declaring the **expected mount**:
  filesystem type (`VHS_MOUNT_FSTYPE`, for example `nfs4`) and source
  (`VHS_MOUNT_SOURCE`, for example `nas.lan:/volume1/vhs`).
- Before every access, VHS read the kernel's mount table (`/proc/self/mountinfo`), found
  the most specific mount containing `VHS_MEDIA_ROOT` and compared its type and source
  with the declared ones; if they differed, the status was `mount_mismatch` and nothing
  was written, even with the marker present.
- No automatic initialization: only `init_library`, and only after the mount verification
  (no option bypassed it).
- The library lived in a **subfolder** of the share, and `docker-compose.mounted.yml`
  mounted it with `create_host_path: false`.

**Reasoning that still holds.**

- **The marker alone is not enough with a mount.** A local directory under a mount point
  can contain a marker: created by hand, copied, left behind by a mistake. Proof is needed
  that the library really is on the expected mount.
- **Why not `os.path.ismount`:** inside Docker every bind mount is a mount point, so
  `ismount` is always true and says nothing about whether NFS is present.
- **Why not comparison with the parent directory:** inferring the mount from device
  differences is indirect and fragile; declaring the expected mount makes it possible to
  verify its **source and type**.
- In a container, `mountinfo` reports the filesystem behind the bind: with NFS mounted on
  the host, `nfs4` appears with its source; with a local directory, the local filesystem
  appears (for example `ext4`, or `virtiofs` on Docker Desktop).
- **The container's view can remain different from the host's.** The bind mount is taken
  when the container is created: if the NAS is unmounted or remounted on the host, the
  container may keep seeing the initial mount or a different view. After an unmount or a
  remount you must **recreate the containers** (`up -d --force-recreate`, or `down` and
  `up`, never with `-v`); `restart` is not enough. `bind.propagation: rslave` was an
  alternative to evaluate.
- **NAS mounted but unresponsive.** With a "hard" mount even a `stat` can block
  indefinitely. A check in a thread with a timeout was discarded: it frees the request,
  not the thread blocked in the kernel.

**Tests carried out.**

- Pytest tests of the logic, with realistic `mountinfo` lines: different type or source
  rejected, most specific mount wins, path escaping, system without `/proc` unsupported.
- **Decisive test** in an isolated Compose project, with its own database: NFS absent,
  `mnt/library` present **on the local disk** with a hand-made `.vhs-library`, mounted
  mode with `nfs4` and an expected source. The stack started; `storage_status` in the
  container showed `virtiofs` and `mount_mismatch`; `/health` responded `degraded`;
  `init_library --allow-empty` was rejected; a real download failed with
  `error_code=storage`; on the host, `mnt/library` contained **only the pre-existing
  marker**. With the bind source absent, the containers were not created.

**What was never tested.** That the mode worked with a real NFS: a local folder with a
marker only demonstrates the rejection. The positive path was covered only by the parser
tests.

**Why it was removed.** In the MVP it added variables, a mode and procedures to
understand, and it left open work items that do not exist with local storage: temporary
files written to the local disk when the mount disappears, the test on real NFS, the
unresponsive NAS. The protections that are also useful for local storage (§3) were kept.

## 6. Criteria for resuming NFS after the MVP

To be resumed when a library on a NAS is actually needed, in a dedicated phase (for
example together with the Jellyfin integration, which shares the same library). Before
declaring it supported:

1. **Restore the mount verification** from commit `207fc9a` (private archive, §5),
   reassessing whether an explicit mode is still needed or whether the expected-mount
   variables are enough.
2. **Temporary files during a transfer:** a download in progress must not be able to
   write to the local disk when the share disappears, or else those files must be
   detected and reported. This is the first work item, before any real test.
3. **Test on real NFS**, with an **independent test NFS mount point** (a dedicated export,
   or the same export mounted a second time on another point, for example
   `/mnt/vhs-test`) and a separate Compose project with its own database. A subfolder of
   the library in use cannot be unmounted on its own, and renaming a folder is not
   equivalent to a mount that disappears. Steps: `storage_status` shows the type and
   source of the test mount; `init_library`; a real download completes; unmount **only
   the test mount** and recreate the containers (VHS rejects the library and writes
   nothing under the mount point); remount and the library becomes available again. The
   real mount is never touched.
4. **Mount view in the containers:** verify on real NFS the recreation procedure and,
   possibly, `bind.propagation: rslave`.
5. **Unresponsive NAS:** choose between a check in a separate process that can be
   terminated, health delegated to an external process, and mount options (`soft`,
   `timeo`, `retrans`) with their trade-offs on data integrity.
6. Document the configuration and procedure in `installation.md` only after points 2
   and 3.

## 7. Main file and new downloads (related decisions)

- An `available` video is never downloaded again: the guard is the file's status, not the
  existence of a completed attempt (409 `already_archived`).
- A new download of an already registered video reuses the basename of the registered
  path: a changed title or channel does not move the file. Promotion without overwriting
  accepts an identical file and rejects a different one.
- If the extension changes, the old path is **always** recorded in
  `Video.superseded_files`, whether or not the file exists: a file that is absent today
  can reappear when the folder comes back. `tracked_paths()` includes these paths, so
  `verify_library` does not report them as unreferenced files.
- If the registered file reappears before the download (same checksum), the video becomes
  available again without a transfer.
- A video may be marked `missing` only while the library is available
  (`can_mark_missing()`). For now `verify_library` only reports; when it starts updating
  statuses it must follow this rule.
