# VHS — Video Hoarding System

## 1. Context

VHS is an open source project to download, archive, organize and play back videos from YouTube and, in the future, from other platforms.

The primary goal is to build a **personal video library**. The project is not meant to redistribute the archived content.

### Vision

VHS must be:

- simple to install;
- simple to understand;
- modular;
- API-first;
- independent of the UI;
- extensible to new platforms;
- suitable for a future open source community.

The Vue UI provided by the project will therefore be **a client of the API**, not the only way to use VHS.

In the future there may be:

- CLI;
- personal scripts;
- media server integrations;
- plugins;
- alternative clients;
- external automations.

---

# 2. Architectural principle

The fundamental principle is:

> **Every component must have a clear responsibility and must know as little as possible about the other components.**

The main pipeline is:

```text
URL
 │
 ▼
API
 │
 ▼
Service
 │
 ├──► Database
 │
 └──► Task
        │
        ▼
      Engine
        │
        ▼
      Storage
        │
        ▼
      Library

```

For playback:

```text
Browser
 │
 ├──► API ──► playback progress
 │
 └──► stream endpoint
          │
          ▼
        Django
          │
          │ authorization
          │ X-Accel-Redirect
          ▼
        Nginx
          │
          ▼
      Video file

```

The responsibilities are therefore:

| Component | Responsibility |
| --------- | -------------- |
| Vue | UI, player, local state |
| API | public HTTP contract |
| Services | application logic and use cases |
| Models | persistence and domain |
| Tasks | asynchronous execution |
| Engine | download and metadata extraction |
| Storage | physical file management |
| Nginx | proxy, HTTPS and file transfer |
| PostgreSQL | application data and job state |

---

# 3. Technology stack

| Component | Choice | Responsibility |
| ---------- | ------ | -------------- |
| Backend | Django 6.x | application, ORM, authentication, API |
| API | Django Ninja | REST/OpenAPI API |
| Frontend | Vue 3 + Vite + TypeScript | user interface |
| State management | Pinia | frontend state |
| Task queue | django-q2 | asynchronous execution and scheduling |
| Task broker/backend | PostgreSQL | task persistence |
| Database | PostgreSQL 16 | application data and search |
| Download engine | yt-dlp + ffmpeg | download and processing |
| Reverse proxy | Nginx | proxy, HTTPS, static files, protected media |
| Package manager | uv | Python dependencies |
| Container | Docker Compose | local and production environment |
| Storage | configurable filesystem | video library |
| Deployment | server or VM with Docker | production environment (for example a Proxmox VM) |
| Network storage | NFS | post-MVP, not supported in the MVP (§15) |

### Intentionally reduced infrastructure dependencies

VHS **does not use Redis**.

PostgreSQL is already required for the application domain, and django-q2 also uses it for task persistence.

This avoids introducing an additional infrastructure service without a concrete requirement.

If a real need for Redis emerges in the future, it can be introduced later.

---

# 4. Architecture

```text
                         ┌──────────────────────┐
                         │        Nginx         │
                         │                      │
                         │ HTTPS                │
                         │ Reverse proxy        │
                         │ Vue static files     │
                         │ Protected media      │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
             ┌──────────────┐               ┌──────────────┐
             │    Vue SPA   │               │ Django API   │
             │              │               │              │
             │ Player       │               │ /api/v1/*    │
             │ Library UI   │               │ Auth         │
             └──────────────┘               └──────┬───────┘
                                                    │
                              ┌─────────────────────┼──────────────────┐
                              │                     │                  │
                              ▼                     ▼                  ▼
                       ┌────────────┐       ┌──────────────┐   ┌────────────┐
                       │ Services   │       │ PostgreSQL   │   │ Task layer │
                       │            │       │              │   │ django-q2  │
                       └─────┬──────┘       └──────────────┘   └─────┬──────┘
                             │                                        │
                             ▼                                        │
                       ┌────────────┐                                 │
                       │   Engine   │◄────────────────────────────────┘
                       │            │
                       │ yt-dlp     │
                       │ ffmpeg     │
                       └─────┬──────┘
                             │
                             ▼
                       ┌────────────┐
                       │  Storage   │
                       │            │
                       │  local     │
                       └────────────┘

```

---

# 5. Architectural boundaries

## 5.1 Frontend

Vue knows about:

- the HTTP API;
- the interface state;
- the player;
- routes;
- components.

Vue **does not know about**:

- the Django ORM;
- PostgreSQL;
- the filesystem and storage;
- yt-dlp;
- django-q2.

---

## 5.2 API

Django Ninja exposes VHS's public contract.

The API:

- validates input;
- authenticates/authorizes;
- serializes data;
- invokes the services;
- returns HTTP responses.

The API **does not contain complex business logic**.

Example:

```text
POST /api/v1/downloads/
        │
        ▼
DownloadService

```

not:

```text
API endpoint
    ├── yt-dlp
    ├── filesystem
    ├── ORM
    ├── retry
    └── business logic

```

---

## 5.3 Services

The services represent the **application use cases**.

Examples:

```text
DownloadService
ChannelService
LibraryService
PlaybackService

```

They can be used by:

- the API;
- tasks;
- management commands;
- tests;
- any future clients.

The services must not depend on Vue.

The services may use:

- the ORM;
- the engine;
- storage;
- other required application components.

---

## 5.4 Tasks

django-q2 is an infrastructure detail.

Tasks must be thin:

```text
task
  ↓
service

```

and contain no business logic.

Example:

```text
download_task(download_id)
    ↓
DownloadService.execute(download_id)

```

The service must not know whether it was invoked:

- by django-q2;
- by a test;
- by a CLI;
- by another part of the application.

---

## 5.5 Engine

The engine is pure Python and does not depend on Django.

Responsibilities:

- interact with yt-dlp;
- extract metadata;
- download;
- report progress;
- use ffmpeg when needed.

The engine does not save Django models directly.

---

## 5.6 Storage

Storage is the boundary between VHS and the filesystem.

The domain should not depend directly on:

```python
open("/srv/video-library/...")

```

but on a storage abstraction.

Conceptual example:

```text
Storage
 ├── save()
 ├── exists()
 ├── delete()
 ├── move()
 ├── get_path()
 └── available_space()

```

Initial implementation:

```text
FilesystemStorage

```

which can point to:

- a folder on the local disk (development without Docker);
- a host folder mounted into the container (bind mount), with Docker.

NFS, SMB and NAS are not supported in the MVP (§15 and
[storage-decisions.md](storage-decisions.md)).

This leaves open the future possibility of implementing other storage backends without changing the domain.

---

# 6. Repository structure

```text
vhs/
├── backend/
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── asgi.py
│   │
│   ├── core/
│   │   ├── models/
│   │   │   ├── video.py
│   │   │   ├── channel.py
│   │   │   ├── source_playlist.py  # post-MVP (subscriptions)
│   │   │   ├── download.py
│   │   │   ├── tag.py
│   │   │   ├── collection.py
│   │   │   ├── playback.py
│   │   │   └── cookies.py        # deferred (§14)
│   │   │
│   │   ├── admin/
│   │   └── migrations/
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── videos.py
│   │   ├── channels.py
│   │   ├── source_playlists.py   # post-MVP (subscriptions)
│   │   ├── downloads.py
│   │   ├── library.py
│   │   ├── playback.py
│   │   ├── cookies.py            # deferred (§14)
│   │   └── schemas/
│   │
│   ├── engine/
│   │   ├── downloader/
│   │   │   ├── base.py
│   │   │   └── ytdlp.py
│   │   │
│   │   ├── extractors/
│   │   │   ├── base.py
│   │   │   ├── youtube.py
│   │   │   └── generic.py
│   │   │
│   │   └── naming.py
│   │
│   ├── storage/
│   │   ├── base.py
│   │   └── filesystem.py
│   │
│   ├── services/
│   │   ├── download_service.py
│   │   ├── channel_service.py          # post-MVP (subscriptions)
│   │   ├── source_playlist_service.py  # post-MVP (subscriptions)
│   │   ├── library_service.py
│   │   └── playback_service.py
│   │
│   ├── tasks/
│   │   ├── downloads.py
│   │   ├── channels.py         # post-MVP (polling)
│   │   └── source_playlists.py # post-MVP (polling)
│   │
│   └── manage.py
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── composables/
│   │   ├── layouts/
│   │   ├── pages/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── App.vue
│   │   └── main.ts
│   │
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── docker/
│   ├── Dockerfile.backend
│   └── nginx.conf
│
├── docs/
│   ├── installation.md         # for those who install and use VHS
│   ├── development.md          # for developers
│   └── architecture.md, conventions.md, storage-decisions.md
│
├── scripts/                    # backup.sh, restore.sh, compare_reports.py, check-dev-config.sh
│
├── vhs                         # commands for an installation
├── dev                         # commands for the development environment
│
├── docker-compose.yml
├── docker-compose.dev.yml
├── docker-compose.prod.yml
├── pyproject.toml
├── uv.lock
└── README.md

```

### Principles

- a single Django app, `core`;
- `engine` completely independent of Django;
- `storage` separate from the domain;
- `services` as business logic;
- `tasks` as asynchronous adapters;
- `api` as the public interface;
- frontend completely separate from the backend.

---

# 7. Data model

## Platform

Enum or lookup table:

```text
youtube
vimeo
dailymotion
...

```

---

## Channel

In the MVP the channel is the **source channel** of the downloaded videos: metadata used
to show where a video comes from and to filter the Library. There are no subscriptions,
no polling and no automatic downloads.

Implemented fields (MVP):

```text
name
platform
platform_id
url

```

Fields planned for subscriptions (post-MVP):

```text
thumbnail_url
description
auto_download
check_interval
last_checked_at
min_duration_seconds
max_duration_seconds
include_shorts
max_initial_downloads
platform_metadata

```

`platform_id` identifies the channel on the source platform. The channel name can change
on the platform and is updated, but it is not part of the identity.

Personal collections stay independent of channels: VHS does not automatically create a
collection per channel.

When subscriptions are introduced (post-MVP), the auto-download rules will apply to the
videos discovered through the channel. `max_initial_downloads` limits only the first
population; later checks follow the normal policy. Missing or uncertain metadata must not
silently turn into an irreversible decision: the video stays discovered and can be chosen
manually.

Categorization coming from the platform stays separate from the tags and collections
assigned locally in VHS. Source playlists (post-MVP) have dedicated models, described in
section 10.

---

# 8. Video

`Video` represents **the content that VHS knows about and archives**.

It does not represent a download attempt.

Common fields:

```text
title
description
duration
thumbnail_url
source_url
platform
platform_id
upload_date
channel
platform_metadata

```

Fields about the local copy and provenance:

```text
file_path                  # archived copy
playback_path              # optional: derived browser copy
thumbnail_path             # optional: archived thumbnail (sidecar)
file_size
container
video_codec
audio_codec
resolution
downloaded_at
source_metadata_snapshot   # metadata collected at acquisition
acquired_at
checksum_sha256

```

The state of the local copy and the state of the source are independent:

```text
local_status: absent | available | missing
source_status: unknown | available | unavailable | deleted

```

For example, a video can stay `available` in the library even after being `deleted` from
the platform. A temporary extraction error is not enough to mark the source as deleted.
`queued` and `downloading` belong to the active `Download`, not to the persistent state of
the `Video`.

`local_status = available` means that the archived file exists, is complete and passes the
minimum integrity checks. Playability in the browser is a separate property: it depends on
container and codecs, or on the presence of `playback_path`.

### Paths

Every archived video has **one main file**, whose path relative to the library is stored
in `file_path`. Next to it are the thumbnail (`thumbnail_path`) and the `.info.json`
sidecar, with the same basename. The browser copy, if any (`playback_path`), lives instead
in a separate tree, `.browser/`, that mirrors the original's path (§18): the channel
folder holds a single video file per content item.

- The path is computed only once, when the file is archived, and from then on the database
  is the source of truth: no part of the application recomputes it from the title or the
  channel name.
- A change of title or channel name on the platform updates the metadata; it does not move
  the file. A **new download** of an already registered video also reuses the basename of
  the stored path.
- If a new download produces a different extension, the old path is always recorded in
  `superseded_files` (with checksum and date), whether the file exists or not: the
  previous file is never left orphaned without a trace.
- Tags and collections are relations of the `Video` in the database: they neither move nor
  duplicate files.
- The API and the UI identify the video by its ID; no response exposes paths.

### Identity

The video must have a unique constraint:

```text
UNIQUE(platform, platform_id)

```

This prevents duplicates from being created when the same video is found through
different URLs.

Example:

```text
youtube.com/watch?v=ABC
youtu.be/ABC
www.youtube.com/watch?v=ABC

```

must identify the same `Video`.

---

# 9. Download

`Download` represents **an operation/attempt to obtain a local copy of a Video**.

Relation:

```text
Video 1 ──── N Download

```

Not:

```text
Video 1 ──── 1 Download

```

because the same video can be downloaded several times over its lifetime.

Fields:

```text
video
status
progress
speed
eta
error_message
error_code
started_at
completed_at
last_heartbeat_at
last_progress_at

```

States:

```text
queued
downloading
processing
completed
failed
cancelled

```

This separation makes it possible to keep the history of attempts.

`error_code` is a stable category the UI can use, for example `authentication`,
`source_unavailable`, `network`, `storage` or `processing`. `error_message` holds the
diagnostic detail, stripped of sensitive URLs and credentials. `last_progress_at` makes it
possible to tell an active transfer from a job that looks stuck; a manual retry creates a
new attempt.

A video whose local copy is available is never downloaded again: the protection is based
on the state of the file (`local_status`), not on the existence of a completed attempt. A
request for an archived video with no completed attempt gets `409 already_archived` with
the video ID. If, at the start of an attempt, the stored file is present again with the
same checksum (for example after the storage comes back), the download is closed as
`completed` without a transfer (`recovered_existing`).

### A single active attempt per video

Creating a download must be idempotent: two concurrent requests for the same video either
return the attempt that is already active or create only one. A database constraint
prevents more than one `Download` in the `queued`, `downloading` or `processing` state at
the same time for the same `Video`; finished attempts stay in the history. Enqueueing
happens after the required records are committed, and a reconciliation check recovers
attempts left in `queued` if enqueueing fails.

The task receives only `download_id`, checks the current state and can be run again
without corrupting files or creating a second attempt. django-q2's timeout, `retry` and
attempt limit must be explicit and consistent with the maximum job duration: a task
redelivered while the first one is still working must not start a concurrent download.
The application-level retry after an error creates a new `Download` and keeps the failed
one.

---

# 10. Discovery vs Download

> **Post-MVP.** Discovery, channel and playlist polling and automatic downloads are part
> of subscriptions, outside the MVP (§39). In the MVP videos enter VHS only through a URL
> requested by the user.

Discovering a video and downloading it are two different operations.

Pipeline:

```text
Channel polling
       │
       ▼
   Discovery
       │
       ▼
    Video
       │
       ├──── auto_download = false ──► end
       │
       ▼
    Download
       │
       ▼
     Worker

```

In the future this makes it possible to:

- see new videos without downloading them;
- choose manually what to archive;
- implement auto-download rules;
- change the policy without modifying the discovery mechanism.

## Source playlists

`SourcePlaylist` represents a playlist created on the platform, independent of the local
`Collection`s created by the user in VHS:

```text
platform
platform_id
url
title
channel              # optional: may be unknown or not relevant
check_interval
last_checked_at
last_successful_check_at
platform_metadata

UNIQUE(platform, platform_id)

```

`SourcePlaylistVideo` keeps the membership and order of the playlist:

```text
source_playlist
video
position
last_seen_at

UNIQUE(source_playlist, video)

```

A playlist can contain videos from different channels; a video can appear in several
playlists. `position` is updated after a complete, successful check; a temporary
disappearance deletes neither the archived file nor the video's record. A `last_seen_at`
earlier than the last successful check makes it possible to flag a membership that is no
longer present in the source, while keeping a trace of it.

With subscriptions, discovery will be able to add a playlist by URL and check its content
periodically. Automatic download based on a playlist, with its own rules separate from
the channel's, remains a later choice: it must not be inferred from playlist membership
alone.

---

# 11. Tag

```text
name
slug
color

```

M2M relation with `Video`. A `Tag` is assigned locally in VHS: any platform tags stay in
`platform_metadata` and in the acquired snapshot. They are not automatically imported as
local tags.

Implementation (Phase 2b):

- case-insensitive unique name; `slug` generated from the name, with a numeric suffix on
  collision; `#RRGGBB` color chosen from a palette that is readable on the dark theme;
- in the interface local tags are called **"Personal tags"**, to set them apart from the
  platform metadata;
- platform tags are shown on the video page as "Source tags", read-only and visually
  distinct; they are never converted into personal tags;
- deleting a tag removes only the associations: the videos stay;
- a tag can also be assigned to videos that are not archived; the counts distinguish
  `video_count` (all) and `archived_count` (with a local copy).

---

# 12. Collection

```text
name
description
cover_image

```

The relation with videos uses a through table with:

```text
collection
video
position

```

The through table is the `CollectionVideo` model, with the constraint
`UNIQUE(collection, video)`. `position` describes the order chosen by the user, not the
order of a `SourcePlaylist`. A video can belong to several collections without duplicating
the file. Local `Collection`s are not overwritten when the platform's playlists change.

Implementation (Phase 2b):

- `cover_image` is implemented as **`cover_video`**: the cover is the local thumbnail of a
  video in the collection. By default it is the thumbnail of the first video in order that
  has one (even if not archived, because the thumbnail is saved during the download);
  another video of the collection can be chosen. This way no image uploads are needed, nor
  a new kind of media to protect; an uploaded cover remains a possible evolution.
- `CollectionVideo` also has the constraint `UNIQUE(collection, position)`, deferred to the
  end of the transaction: two videos cannot have the same position, and reordering
  renumbers everything in a single transaction.
- Additions, removals and reorders take the same lock on the collection
  (`select_for_update`): concurrent operations are serialized and do not assign the same
  position. A video is added at the end; reordering requires exactly the set of current
  videos.
- A collection can contain videos that are not archived: its page shows them with a
  badge; `video_count` and `archived_count` have the same definition as for tags.
- Deleting a collection does not delete the videos.
- Collections are independent of channels and source playlists: VHS does not create any
  automatically, neither per channel nor per playlist.
- The folder layout does not represent collections: a video can belong to several
  collections and remains a single file, at the path decided at archiving time (§17).

---

# 13. PlaybackProgress

The playback position is application data, separate from the video file.

Model:

```text
PlaybackProgress
    user
    video
    position_seconds
    duration
    updated_at

```

Constraint:

```text
UNIQUE(user, video)

```

The frontend saves the position periodically.

Example:

```text
PUT /api/v1/videos/123/progress

{
    "position_seconds": 1815,
    "duration": 3600
}

```

On reopening:

```text
GET /api/v1/videos/123/progress

```

The player sets:

```javascript
video.currentTime = position

```

Playback persistence is therefore independent of the streaming system.

Implemented behavior:

- the position is saved every 10 seconds during playback and immediately on pause, after
  a seek, at the end of the video and when the page goes to the background (`fetch` with
  `keepalive`, which, unlike `sendBeacon`, allows the CSRF header);
- on reopening, the player resumes from the saved position, except in the first 5 seconds
  and the last 10, where it starts over from the beginning;
- the server clamps the position between 0 and the duration; a `GET` with no saved data
  returns `position_seconds: 0`.

---

# 14. CookieConfig

> **Status: deferred.** VHS currently downloads without platform cookies, and anonymous
> downloads work. This section describes the design to adopt when a source requires login
> or passes anti-bot checks only with cookies; no model, endpoint or page is implemented
> yet. Meanwhile, errors of this kind are classified as `authentication` (§9) and shown on
> the Downloads page.

When it is introduced:

- manual upload of `cookies.txt`;
- association with the platform;
- use by yt-dlp.

Cookies must be treated as **credentials**, not as plain metadata.

Their content must not be handled as normal application data.

Goal:

```text
CookieConfig
    ↓
encrypted at rest

```

The encryption key must be kept separate from the database.

Conceptual fields:

```text
platform
encrypted_cookies
last_updated_at
last_validated_at
validation_status       # unknown | valid | invalid | error
last_validation_error_code

```

The UI shows the status and the date of the last check, telling expired or invalid
cookies apart from temporary source errors. For example:

```text
Cookies valid ✓
Cookies expired ✗
Check failed — try again

```

Validity is checked periodically through a suitable metadata extraction operation.

Only an administrator can upload or replace the cookies. The worker decrypts them only
when they are needed and makes them available to yt-dlp in a temporary file with
restrictive permissions, outside the library and the logs; the file is removed even in
case of error. Key rotation, cookie deletion and the behavior when the key is missing are
defined. Database encryption alone does not protect the temporary plaintext copy, if any.

### Alternative to evaluate: `cookiesfrombrowser`

yt-dlp can read cookies directly from a browser profile (`cookiesfrombrowser`), without an
upload. It is more convenient, but:

- it works only where the worker has access to that profile, which is never the case in
  containers (neither in development nor in production);
- it gives yt-dlp access to all the profile's cookies, not only the platform's, and falls
  outside the credential handling described above.

The choice between the two solutions will be made when the feature becomes necessary.

---

# 15. Storage and filesystem

## Media root

The library is a **host folder**, set by the mandatory `VHS_HOST_LIBRARY` and mounted in
the containers as `/srv/video-library` (`VHS_MEDIA_ROOT`, fixed in the containers). This
applies to the installation (for example `/srv/vhs/library`) and to development
(`./video-library`), which also runs in containers (§34).

NFS, SMB, NAS and separately mounted disks **are not supported in the MVP**: a dedicated
mode was implemented and then removed, and it remains post-MVP (storage-decisions.md, §5
and §6).

The paths stored in the database (`file_path`, `playback_path`, `thumbnail_path`) are
relative to `VHS_MEDIA_ROOT`: the library can be moved by changing only
`VHS_HOST_LIBRARY`.

## Library availability

VHS never writes where it does not find the library. The case to avoid is an empty folder
in place of the library (folder renamed or moved, wrong `VHS_HOST_LIBRARY`, folder
replaced): VHS would write work dirs, sidecars and video files into it. Reasoning, tests
and limits are in [storage-decisions.md](storage-decisions.md).

- **`.vhs-library` marker** in the root of the library: the storage writes only where it
  finds it (`work_dir`, `finalize`, `delete`) and never creates the root, except for a new
  library (no archived video in the DB and the folder missing or empty), which is
  initialized automatically on the first download.
- **States:** `ok`, `new` (created on the first download), `not_initialized` (non-empty
  folder without a marker: `init_library` is needed once), `missing` (a populated library
  has disappeared).
- With the library unavailable: downloads and preparations fail with `error_code=storage`
  without writing; stream and thumbnails respond 503; `/health` responds `degraded`; the
  `vhs.W002` system check reports it at startup; the UI shows a warning.
- `manage.py storage_status` shows folder, marker and state; `manage.py init_library`
  explicitly initializes an existing library.
- **Limits:** the check narrows but does not close the window between check and write; a
  transfer already in progress can leave temporary files where the library was, but they
  enter neither the library nor the database (storage-decisions.md, §4).

---

# 16. Safe download to storage

A download must not make an incomplete file visible right away.

The principle is:

```text
download
   │
   ▼
temporary/incomplete file
   │
   ▼
processing
   │
   ▼
atomic finalize
   │
   ▼
final filename
   │
   ▼
Video.local_status = available

```

Example:

```text
.incomplete/
    abc123.part

```

then:

```text
youtube/
    Channel/
        2024-03-15 - Title [abc123].mp4

```

The `Video` is considered available only once the file and the required operations are
complete.

The temporary directory for the final file is on the **same filesystem** as the
destination. A rename across different filesystems turns into a copy and does not provide
the intended atomic finalization. Renaming the file does not also make the database update
atomic, nor the publication of several sidecars: the service checks all the required
outputs, promotes the file, then sets `local_status = available`. The API exposes only
files registered as available.

At startup and periodically, a reconciliation process compares jobs, temporary files and
final files. When the library is unavailable (§15), reconciliation is skipped: it does not
mark attempts as interrupted, register files or clean up work dirs until the library comes
back. It resumes interrupted jobs or marks them as failed, recognizes files that are
already finalized but not registered, and never overwrites a complete copy because of a
retry.

This is especially important in case of:

- a worker crash;
- a container restart;
- a temporarily unavailable library;
- an ffmpeg error;
- insufficient space.

---

# 17. File naming

Two built-in templates.

## Standard

```text
video-library/
  youtube/
    Channel Name/
      2024-03-15 - Video title [dQw4w9WgXcQ].mp4
      2024-03-15 - Video title [dQw4w9WgXcQ].info.json
      2024-03-15 - Video title [dQw4w9WgXcQ].webp

```

## TV Show

```text
video-library/
  youtube/
    Channel Name/
      Season 2024/
        s2024.e0315 - Video title [dQw4w9WgXcQ].mp4
        s2024.e0315 - Video title [dQw4w9WgXcQ].info.json
        s2024.e0315 - Video title [dQw4w9WgXcQ].nfo
        s2024.e0315 - Video title [dQw4w9WgXcQ].webp

```

### Rules

- the platform ID is always present;
- sidecars share the same basename;
- invalid characters are sanitized;
- titles are truncated to a reasonable length;
- the channel name is readable;
- custom templates are post-v1;
- the template is applied at archive time: changing the template, or the title and the
  channel name on the platform, does not move files that are already archived (the
  registered path stays valid);
- folders represent only provenance (source platform and channel), never personal tags or
  collections;
- browser copies are not stored in the channel folders but in `.browser/` (§18), so each
  folder contains only one video file per item.

The readable basename can change, but the stable identity remains
`(platform, platform_id)`. For preservation, VHS keeps the acquisition date, the original
URL, a snapshot of the metadata and the SHA-256 checksum of the archived copy. A periodic
check reports missing files or mismatched checksums without automatically deleting the
video's record. `.info.json` files can contain personal data: they stay protected like the
other media and are not published by default.

The `.nfo` file in the TV Show example is **not generated in the MVP**: the Jellyfin
integration is a dedicated phase, outside the MVP and independent of subscriptions (§39).
The TV Show template already exists as a folder layout. In that phase the preset will be
able to generate a basic `.nfo` using the fields already present in `Video` (title,
description, channel, date and source ID), without a Django model for the sidecar; the
layout and the files must be verified with Jellyfin. Plex compatibility requires tests and
specific rules; the presence of an NFO does not guarantee it.

The current choices keep that integration possible without implementing it ahead of time:
each video has a main file with a registered path (and browser copies live outside the
channel folders), identity does not depend on the path, metadata
(`source_metadata_snapshot`, `.info.json`) and thumbnails remain available for an export,
and folders do not try to represent collections.

---

# 18. Download engine

Abstract class:

```python
class BaseDownloader:
    def extract_info(self, url):
        ...

    def download(self, url, output_path, options):
        ...

    def get_progress(self):
        ...

```

Initial implementation:

```text
YTDLPDownloader

```

which uses the yt-dlp Python API.

The engine does not know about the Django models.

### Format policy for v1

When the source offers one, the engine prefers a format that plays in HTML5 in the target
browsers, for example MP4 with H.264 video and AAC audio. The downloaded copy always
remains the main archive and is never modified.

After the download is registered, `ffprobe` analyzes the **archived file**: the `.mp4`
extension or the source metadata alone do not guarantee playback. The browser target is:
MP4 container, 8-bit H.264 video (`yuv420p`), AAC or MP3 audio, or no audio.

```text
ffprobe on the archived file
        │
        ├── native      → plays the original
        ├── remux       → automatic derived copy (container change only)
        ├── transcode   → "Prepare for playback", on request only
        └── unsupported → no video stream

```

- **Remux**: the codecs are already compatible but in another container (for example
  H.264/AAC in MKV). The derived copy is created automatically with `ffmpeg -c copy`: it
  is fast and loses no quality.
- **Transcode**: video, audio or both must be re-encoded (VP9, AV1, HEVC, 10-bit H.264,
  Opus, Vorbis...). The conversion costs CPU, so it starts only when the user requests it
  from the video page; it re-encodes only the streams that need it (`libx264`/`aac`,
  configurable preset and quality).
- The derived copy lives in a separate tree that mirrors the original's path,
  `.browser/<path of the original>.mp4`, and is registered in `playback_path`. This way
  the channel folder contains only one video file per item, and a media server, which
  transcodes on the fly on its own, does not need the derived copies. How to exclude
  `.browser/` from the scan must be validated in the phase dedicated to Jellyfin. Before
  registering it, `ffprobe` checks that it is actually playable.
- Each preparation is a `PlaybackPreparation` (only one active per video, with history,
  heartbeat and reconciliation like downloads). A preparation or analysis error **does not
  invalidate** the archived video: it stays `available`, and the UI shows the reason and
  lets the user retry.
- The UI shows the state of the browser copy: **Ready** (original or derived copy),
  **Preparing** (analysis, remux or conversion, with a percentage) or **Unavailable**
  (with the reason and, if a conversion is needed, the button).
- Videos archived before analysis existed are analyzed by the periodic reconciliation or
  with `manage.py analyze_media`.

---

# 19. Metadata extraction

Metadata mapping is kept separate from the downloader.

```text
MetadataExtractor
    │
    ├── YouTubeMetadataExtractor
    └── GenericMetadataExtractor

```

The downloader produces raw data.

The extractor decides how to map it.

This makes it possible to add platforms without changing the downloader core.

---

# 20. Download progress

The yt-dlp callback produces, for each stream:

```text
downloaded bytes
total bytes
speed
eta

```

With separate video and audio formats yt-dlp downloads the streams one after the other
and reports each one on its own, starting again from zero. The downloader sums them
(`StreamProgress`), so the progress of the whole download never goes back. The total is
the larger of the size estimated before starting (every selected format) and the
reported one (only the streams started so far). The percentage stays below 100% until
the file is archived. yt-dlp's `eta` covers only the current stream. The ETA VHS shows
is an **estimate** for the whole download: the bytes still missing from the estimated
total, divided by the current speed. It changes with the speed and is only as accurate as
the size estimate; without an estimate made before starting it is unknown.
When merging starts the download switches to `processing`, so a long merge is not taken
for a stall. At completion the download records the size of the archived file.

Progress does not have to be written to the database on every callback.

The service/task updates the state with reasonable throttling. It updates
`last_progress_at` when it receives actual progress and uses `last_heartbeat_at` to signal
that the worker is still alive, even during extraction or processing. The UI shows the
error category and detail and offers a manual retry for failed attempts.

The v1 frontend uses polling:

```text
GET /api/v1/downloads/{id}

```

In the future:

```text
SSE

```

or possibly:

```text
WebSocket

```

---

# 21. Video streaming

Video files are **not streamed through Django**.

Django handles:

- authentication;
- authorization;
- locating the file;
- deciding whether the video is playable.

Nginx handles:

- transferring the bytes;
- HTTP Range Requests;
- seeking;
- long-lived connections;
- serving the file.

---

# 22. Protected media with Nginx

Library files must not be exposed directly as a public directory.

The intended pattern is:

```text
Browser
   │
   │ GET /api/v1/videos/123/stream
   ▼
Django
   │
   ├── checks authorization
   │
   └── X-Accel-Redirect
             │
             ▼
           Nginx
             │
             ▼
       /srv/video-library/...

```

The Nginx location that contains the media will be `internal`.

So the client knows:

```text
/api/v1/videos/123/stream

```

and not:

```text
/srv/video-library/youtube/...

```

This keeps the filesystem an internal detail of the application.

### Thumbnails

The archived thumbnail uses the same mechanism. The other sidecars, for example
`.info.json`, are not exposed by default (§17).

```text
GET /api/v1/videos/123/thumbnail
        │
        ▼
Django ── authorization ── X-Accel-Redirect
        │
        ▼
Nginx ── /media-internal/.../Title [id].webp

```

The UI uses the local copy when the video is archived: the thumbnail stays visible even
after the video is removed from the platform, and browsing the library makes no requests
to external services. `thumbnail_url` remains source metadata; it can be used as a
fallback only for videos not yet archived, or replaced by a placeholder.

The thumbnail is published in the library as soon as yt-dlp downloads and converts it,
before the video transfer: the UI already shows it during the download, and also if the
download fails. While the download is queued and the worker has not picked it up yet, the
UI shows the placeholder.

Django does not transfer media bytes even in development: streams and thumbnails always go
through `X-Accel-Redirect`, and to work on the player you start the development Nginx
proxy described in §34.

The internal URI is made only of the fixed prefix `VHS_MEDIA_ACCEL_PREFIX`
(`/media-internal/`) and the relative path registered on the `Video`, validated by the
storage: absolute paths, `..`, the `.incomplete/` work area and symbolic links (on the file
or on an intermediate directory) are rejected. Nginx also applies `disable_symlinks on`
and rejects `/media-internal/.incomplete/`.

---

# 23. Seeking

The player uses HTML5 `<video>`.

The file is transferred through HTTP Range Requests.

So:

```text
user drags to 45:00
        │
        ▼
browser requests a portion of the file
        │
        ▼
Nginx
        │
        ▼
filesystem

```

There is no need to transfer the whole file before seeking.

The Django backend does not transfer the video bytes.

---

# 24. Playback

Frontend:

```text
HTML5 <video>

```

Possibly a wrapper:

```text
Video.js

```

or:

```text
Plyr

```

The player handles:

- play/pause;
- seeking;
- volume;
- fullscreen;
- subtitles, if any.

Before opening the player, the API checks that a browser-compatible copy exists. If
`playback_path` exists, the stream points to the derived copy; otherwise it uses the
archived file only if it is compatible (§18). A video that was just downloaded and not yet
analyzed is served as is, so that watching it is not blocked during the few seconds of the
analysis. An archived copy that cannot be played stays visible in the library, and the
stream responds `404` with the code `not_playable`.

The frontend periodically saves:

```text
currentTime

```

through the API.

The position is restored when the video is reopened.

---

# 25. Public API

The API is a central component of the project.

Versioning:

```text
/api/v1/

```

Initial resources:

```text
/videos
/channels           # MVP: read-only (filters); management post-MVP
/source-playlists   # post-MVP (subscriptions)
/downloads
/library
/tags
/collections
/playback
/cookies            # deferred (§14)

```

Examples:

```text
POST   /api/v1/downloads/
GET    /api/v1/downloads/{id}

GET    /api/v1/videos/
GET    /api/v1/videos/{id}
GET    /api/v1/videos/{id}/stream
GET    /api/v1/videos/{id}/thumbnail

GET    /api/v1/videos/{id}/progress
PUT    /api/v1/videos/{id}/progress

GET    /api/v1/channels/                 # MVP: read-only, for the filters
POST   /api/v1/channels/                 # post-MVP (subscriptions)

GET    /api/v1/source-playlists/         # post-MVP (subscriptions)
POST   /api/v1/source-playlists/         # post-MVP
GET    /api/v1/source-playlists/{id}/videos/   # post-MVP

GET    /api/v1/tags/
POST   /api/v1/tags/
PATCH  /api/v1/tags/{id}
DELETE /api/v1/tags/{id}
PUT    /api/v1/videos/{id}/tags

GET    /api/v1/collections/
POST   /api/v1/collections/
GET    /api/v1/collections/{id}
PATCH  /api/v1/collections/{id}
DELETE /api/v1/collections/{id}
POST   /api/v1/collections/{id}/videos
DELETE /api/v1/collections/{id}/videos/{video_id}
PUT    /api/v1/collections/{id}/videos/order

```

Django Ninja generates the OpenAPI schema automatically.

The API must be designed as a contract independent of the Vue app. The `source-playlists`
resources and channel management (`POST /channels/`) are part of subscriptions, post-MVP;
local tags and collections are in Phase 2b; `cookies` is deferred until it is needed
(§14). The endpoints listed describe the target contract, not everything that is already
available.

For v1, single-user administrative access is defined, with a session and CSRF protection
for operations that modify data. Authorization also covers the stream endpoint, metadata,
downloads and, once they are introduced, platform cookies. Authentication for external
clients and multi-user management remain later developments; the API nevertheless keeps a
stable, documented contract.

---

# 26. Frontend

## Layout

Dark theme by default.

Style:

```text
home theater / media center

```

Sidebar:

```text
Home
Library
Collections
Personal tags
Downloads

```

Post-MVP, with subscriptions: `Channels` and `Source playlists`.
`Settings` will return once there are settings that can be used from the UI
(today all configuration lives in environment variables).

## MVP pages

1. Dashboard
2. Library (with a filter by source channel)
3. Video detail
4. Collections and collection detail (editable order)
5. Personal tags
6. Downloads

Channel management (subscriptions, check status) is post-MVP; a Settings page will be
introduced only together with real settings.

---

# 27. Dashboard

Shows:

- recent videos;
- downloads in progress;
- any errors;
- available space, when available.

With subscriptions (post-MVP), channel status is added.

---

# 28. Library

Features:

- video grid;
- search;
- filter by channel;
- filter by source playlist (post-MVP, with subscriptions);
- filter by tag;
- filter by collection;
- filter by status;
- manual creation and assignment of tags and collections, with ordering of the
  videos within the collection;
- sorting.

Initial search (Phases 2a and 2b): simple case-insensitive search over title,
description, channel name and **personal tag names**. Filters by channel, personal tags
(multiple tags combined with AND), collection, local status and browser copy status;
sorting by date added, publication date, title, duration and, when a collection is
selected, collection order (the default in that case); pagination. Filters and search
are reflected in the page's query string.

Text search does **not** include:

- platform tags: they are source metadata, often numerous and meant for ranking, and
  they would make results unpredictable;
- collection names: to find the videos in a collection there is the dedicated filter.

Evolution (Phase 5):

```text
PostgreSQL full-text search

```

---

# 29. Video detail

Displays:

- player;
- title;
- description;
- channel;
- date;
- duration;
- metadata;
- tags;
- collections;
- notes (Phase 5);
- local status;
- playback position.

---

# 30. Channels and source playlists

> **Post-MVP.** This view belongs to subscriptions (§39). In the MVP the source
> channel is a video metadata field and a Library filter; there is no dedicated
> channels page.

It will allow:

- adding a channel;
- viewing the last check;
- configuring the interval;
- enabling/disabling auto-download;
- minimum/maximum duration, inclusion of Shorts and initial download limit.

Polling uses django-q2 Schedule. Checking a channel never starts two simultaneous
discoveries for the same channel; it records the last outcome and distinguishes a
temporary error from a genuine absence of new videos.

A dedicated view will allow adding source playlists, browsing their videos in the
original order and starting a check. This view stays separate from the Library's local
collections, which subscriptions never create or modify.

---

# 31. Downloads

Shows:

- queue;
- active downloads;
- progress;
- speed;
- ETA;
- history;
- error category and details;
- last activity and flagging of apparently stuck jobs;
- manual retry that keeps the previous attempt.

---

# 32. Docker Compose

Services:

```yaml
services:
  db:
    image: postgres:16-alpine

  backend:
    build: .
    command: uvicorn config.asgi:application --host 0.0.0.0 --port 8000

  worker:
    build: .
    command: python manage.py qcluster

  nginx:
    image: nginx:alpine

```

There is no Redis.

The django-q2 worker uses PostgreSQL as the backend/broker configured for the project.

Nginx serves:

- the Vue build;
- reverse proxy to Django;
- protected media.

The backend and the worker have write access to the library; Nginx mounts it
read-only. The library is a host folder given by `VHS_HOST_LIBRARY` (required), mounted
with `create_host_path: false`: if the folder is missing, the containers are not
created. PostgreSQL uses a Docker volume; the library does not (storage-decisions.md,
§1). In production, Compose handles health checks, startup after the migrations and the
services' restart policies. The PostgreSQL volume and the media need backups and a
restore test, because the database alone cannot rebuild the archived videos.

---

# 33. Nginx

Responsibilities:

```text
/
    → Vue SPA

/api/
    → Django

/media-internal/
    → filesystem, only via internal redirect

```

Nginx contains no business logic.

Django does not transfer videos.

The boundary is:

```text
Django = authorization
Nginx  = transport

```

---

# 34. Local development

Development **always runs in containers**, with the same services as the installation:
`docker-compose.yml` plus the `docker-compose.dev.yml` override (project `vhs-dev`). The
development `.env` (`.env.dev.example`) sets
`COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml`, so inside the project folder
every `docker compose …` acts on the development environment. The `./dev` script
shortens frequent commands, printing what it runs. Commands and PyCharm:
[development.md](development.md).

```text
Browser ── http://localhost:8081  (127.0.0.1 only, VHS_DEV_HTTP_PORT)
              │
              ▼
        nginx (nginx:alpine, docker/nginx.dev.conf)
              │
              ├── /api/ /admin/ /static/ ──► backend:8000   runserver, code mounted
              │
              ├── /  (HTTP + WebSocket HMR) ──► frontend:5173  Vite, code mounted
              │
              └── /media-internal/  (internal, disable_symlinks)
                        │
                        ▼
                  /srv/video-library  ◄── ./video-library (read-only)

        worker  (qcluster under watchfiles, code mounted)
        migrate (migrate, collectstatic, reconciliation on every up)
        db      (volume vhs-dev_pgdata)
```

- **Multi-stage image** (`docker/Dockerfile.backend`): `prod` for the installation
  (dependencies without the dev group, code copied in), `dev` for development (with
  pytest, ruff, watchfiles; the repository is mounted on `/app`). `migrate`, `backend`
  and `worker` use the same `dev` image and the same mounted code: a new migration is
  seen by all of them at the same moment. The frontend uses
  `docker/Dockerfile.frontend-dev`, with `node_modules` in a volume separate from any
  that may exist on the computer.
- **Network:** services reach each other by name inside Docker's network, the same on
  Linux and on macOS; no `host.docker.internal`. `nginx.dev.conf` uses variables in
  `proxy_pass` with Docker's resolver, so a container recreated with a new address is
  found. The only published port is `127.0.0.1:8081`; the backend, Vite and the
  database cannot be reached from outside.
- **Overrides and the resulting configuration.** In an override, ports and volumes are
  added to those of the main file, while build, image and command replace them.
  `docker-compose.dev.yml` therefore uses `ports: !override`, `volumes: !override` and
  `build: !reset null` (for nginx, which must not build the SPA).
  `scripts/check-dev-config.sh` checks the **resulting** configuration (ports, build,
  images, mounts, commands, user, project) for both development and the installation.
  Without `!override`, for example, Nginx would also publish port 8080 on all
  interfaces.
- **Protected media as in production:** Django checks the session and responds with
  `X-Accel-Redirect: /media-internal/<relative path>`; Nginx serves the file and
  handles HTTP Range Requests (`206`, `Content-Range`, `416`). Django does not implement
  Range responses. `/media-internal/` requested directly returns `404`.
- Nginx passes `Host` with the port (`localhost:8081`): Django sees the same origin as
  the browser. Vite's HMR client connects to the page's port, so the WebSocket goes
  through Nginx with no extra configuration.
- **Container user:** `VHS_UID`/`VHS_GID` (default 1000), so that on Linux the files
  created in the mounted repository remain owned by the developer's user.
- **Debugger (PyCharm Professional):** Docker Compose interpreter on the `backend` (or
  `worker`) service. When debugging, PyCharm recreates that service's container with the
  debugger, with the same network name: Nginx forwards requests to it and breakpoints
  stop on pages opened from `:8081`. Verified on the Mac for backend and worker; on
  Linux, connecting the debugger to the IDE is still to be verified.
- **Times measured on the Mac (Docker Desktop):** `runserver` reload in about 1 s,
  worker restart in about 1 s, HMR in under 0.1 s, test suite in about 22 s (about 17 s
  with the old setup on the Mac).

To try a real installation (`prod` images, built SPA, `DEBUG=false`), install VHS in
another folder following [installation.md](installation.md).

---

# 35. Production

Planned deployment:

```text
Proxmox
  │
  ▼
Minimal Debian VM
  │
  ▼
Docker Compose

```

Library (MVP: local storage only, §15):

```text
VM host
/srv/vhs/library        (folder on the VM's disk, uid 1000)
   │
   │ bind mount (create_host_path: false)
   ▼
container
/srv/video-library

```

A library on a NAS (NFS) is post-MVP (§39, "Network storage").

Deployment:

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

```

---

# 36. Complete flow: download

The fundamental flow of v1 is:

```text
User
 │
 │ POST URL
 ▼
API
 │
 ▼
DownloadService
 │
 ├── normalize URL
 ├── extract metadata
 ├── deduplicate Video
 └── create Download
 │
 ▼
django-q2
 │
 ▼
DownloadService.execute()
 │
 ▼
YTDLPDownloader
 │
 ▼
temporary file
 │
 ▼
ffmpeg / processing
 │
 ▼
Storage.finalize()
 │
 ▼
Video.local_status = available

```

This is the **main vertical slice of the project**.

---

# 37. Complete flow: playback

```text
User opens Video
        │
        ▼
GET /api/v1/videos/123
        │
        ▼
Vue shows metadata
        │
        ▼
GET /api/v1/videos/123/stream
        │
        ▼
Django
        │
        ├── authorization
        │
        └── X-Accel-Redirect
                  │
                  ▼
                Nginx
                  │
                  ▼
                file

```

In parallel:

```text
HTML5 video
     │
     ├── play
     ├── pause
     └── seek
          │
          ▼
PUT /api/v1/videos/123/progress
          │
          ▼
PostgreSQL

```

---

# 38. Complete flow: channel discovery

> **Post-MVP.** Planned flow for subscriptions (§39); not implemented in the MVP.

```text
django-q2 Schedule
        │
        ▼
ChannelService.check(channel)
        │
        ▼
extract channel entries
        │
        ▼
normalize / deduplicate
        │
        ▼
create/update Video
        │
        ├── auto_download = false
        │       └── stop
        │
        └── auto_download = true
                │
                ▼
             Download

```

Discovery and download remain separate.

For a `SourcePlaylist`, the check normalizes the video IDs, updates
`SourcePlaylistVideo.position` and `last_seen_at`, and reuses the `Video` records that
are already known. A change to the remote order does not change
`CollectionVideo.position`. Playlist discovery does not automatically queue downloads
and does not create personal collections.

---

# 39. Development order

The priority is not to implement every feature right away.

The priority is to build **solid foundations and a complete vertical slice**.

## MVP scope

| Phase | Content | MVP |
| ----- | ------- | --- |
| 0 | Foundation | yes (implemented) |
| 1 | Reliable download core | yes (implemented) |
| 2a | Library, playback and formats | yes (implemented) |
| 2b | Local organization (personal tags, collections) | yes (implemented) |
| 3 | Operational reliability: essential part | yes (implemented) |
| 3 | Operational reliability: advanced metrics and automation | no |
| 4 | Channel and playlist subscriptions | no |
| — | Jellyfin integration | no |
| — | Network storage (NFS, SMB, NAS) | no |
| 5 | Advanced organization | no |
| 6 | Community / extensibility | no, except documentation and license for the first release |

In the MVP, videos enter VHS only through a URL requested by the user. The source channels
of downloaded videos remain as metadata and as a Library filter; personal collections stay
independent of the source's channels and playlists. What remains to complete the MVP is the
documentation and license needed to publish the first release, and the pre-release checks
(§39).

## Phase 0 — Foundation

- repository, uv and test framework;
- Django, PostgreSQL and Vue;
- Docker Compose and Nginx;
- environment configuration and directory structure;
- explicit convention: source metadata and playlists kept separate from local tags and
  collections, without anticipating their models in this phase;
- single-user administrative authentication and CSRF protection;
- django-q2 configuration with timeout, retry and attempt limit;
- migrations, health endpoint and essential logging.

## Phase 1 — Reliable download core

- `Video` and `Download`, with independent states for the copy and the source;
- `error_code`, `last_progress_at`, readable diagnosis and manual retry;
- `YTDLPDownloader` and metadata extraction;
- filesystem storage and naming;
- asynchronous download, API and progress;
- deduplication and a single active attempt per video;
- enqueueing after commit and reconciliation of `queued` jobs;
- temporary files, finalization on the same filesystem and recovery after a crash;
- checksum, upfront free-space check and initial limit on concurrent downloads;
- tests on retry, worker restart and storage failures.

Goal:

```text
URL → archived file, complete, verified and recoverable after a crash

```

## Phase 2 — Library and protected playback

The phase is split into two stages.

### Phase 2a — Library, playback and formats

- video list, detail and thumbnail;
- thumbnails served from the local copy through protected media (§22), with the source's
  `thumbnail_url` only as a fallback for videos that are not archived;
- format policy with `ffprobe`: automatic remux, conversion on request, browser copy
  state (§18);
- player, protected streaming and HTTP Range;
- stream authorization with the administrative account;
- playback progress and basic search.

### Phase 2b — Local organization

- local `Tag`, `Collection` and `CollectionVideo`, with essential manual management
  (implemented: personal tags, sortable collections, filters and search, §11, §12, §28).

The Jellyfin integration (NFO and library layout) has a dedicated phase, outside the MVP.

Management of platform cookies is deferred as long as anonymous downloads work; the design
and the alternatives are described in §14.

Goal:

```text
download → archive → play → resume where I left off

```

## Phase 3 — Operational reliability

### Essential part (MVP)

Status: **first block completed** with local storage (library unavailable and orphaned
main file, §15 and [storage-decisions.md](storage-decisions.md)). The MVP supports only
local storage (a host folder with Docker): the mode for network shares was implemented and
then removed, and the related open work (temporary files written to the local disk when the
mount disappears, a test on real NFS, an unresponsive NAS) has moved to post-MVP (see
"Network storage" below).

**Second block completed:** read-only file verification (`manage.py verify_library`,
`services/verification_service.py`). It compares the database with the folder and reports
missing main files, mismatched sizes, mismatched checksums (only with `--checksums`),
unreferenced files (anything not in `tracked_paths()`), abandoned `.incomplete` temporary
files, and symbolic links, which are not followed. The work dirs of active downloads and
preparations and the files being promoted are listed separately, as "in progress". When the
library is unavailable, when there are read errors, or when the library disappears during
the scan, the check is declared **incomplete** (exit code 2) and reports no missing files.
It modifies neither the database nor the files. Deferred: cleanup, state changes
(`missing` only with `can_mark_missing()`), periodic execution, API and UI.

**Third block completed:** backup with a restore test (`scripts/backup.sh`,
`scripts/restore.sh`, "Backup and restore" in [installation.md](installation.md)). The
backup stops only the worker (the only service that writes files) after checking that no
jobs are running, and restarts it only if it was running. It saves the
`verify_library --checksums` report, the database dump and **then** the full copy of the
library (without `.incomplete`), in a `.partial` folder that is renamed only once the
backup has succeeded. The restore runs only on a new installation (empty folder, empty
database), with the worker stopped until the verification, and compares the final report
with the backup's: `0` succeeded, `3` data restored with problems already present in the
backup, `1` failed (stack not started). Incremental backups (`--link-dest`), scheduling,
rotation and remote backups are deferred.

With these three blocks, the essential part of Phase 3 is complete.

**Pre-release checks** (final verifications, not roadmap blocks):

- end-to-end test that Nginx, with `nginx.conf` and `nginx.dev.conf`, refuses to serve a
  symbolic link in the library through `/media-internal/` (`disable_symlinks on`) even
  when the path comes from an `X-Accel-Redirect`: an error response and no bytes of the
  external file. Today the refusal is proven by tests only on the Django side
  (`get_media_path()`).

- handling of and recovery from storage and download failures: library unavailable (done),
  storage full, errors during writing, worker restarts, with dedicated tests;
- (done, read-only; periodic runs and state changes deferred) file verification: missing
  files (`local_status = missing`), mismatched checksums, files present on disk but not
  registered, without ever automatically deleting a video's record;
- detection of **orphans** (files in the library not referenced by the database: sidecars,
  copies in `.browser/`, main files) and reporting them; removal remains an explicit
  choice;
- (done) explicit check: **re-downloading a video whose title has changed can leave the
  main video file orphaned**, not just sidecars and derived copies. Known cases:
  - the "an archived video is not re-downloaded" protection is currently based on the
    presence of a completed `Download`, not on the file: an `available` video without a
    completed attempt (registered by hand or, in the future, imported) is re-downloaded
    and, if the title has changed, the new path replaces the registered one, leaving the
    old file on disk;
  - a video marked `missing` because of temporarily unreachable storage, re-downloaded
    with the new title, leaves an orphan when the storage comes back;
  - expected fix: base the protection on the file state (`local_status` and presence of
    the registered file) and, if a new download changes the path of a file that still
    exists, keep the old file and report it instead of losing track of it;
- (done) backup of database and library with a documented restore test.

### Advanced (post-MVP)

- backoff and more elaborate retry policies;
- metrics, advanced diagnostics and automation;
- tuning of parallelism based on the storage.

## Network storage (post-MVP)

Library on NFS, SMB or NAS: **not supported in the MVP**. A mounted mode (verification of
the expected mount through `/proc/self/mountinfo`) was implemented and removed before the
first public release (commit `207fc9a` of the private development archive). The reasoning,
the tests carried out and the criteria for picking it up again are in
[storage-decisions.md](storage-decisions.md), §5 and §6: before declaring it supported, it
needs the fix for temporary files written to the local disk during a download in progress,
a test on real NFS with an independent test mount and an isolated database, and a decision
on the unresponsive NAS. It can be tackled together with the Jellyfin integration, which
shares the library.

## Phase 4 — Channel and playlist subscriptions (post-MVP)

Subscriptions to the source's channels and playlists, with download of the archive and
polling for new videos:

- `Channel`, discovery, scheduling and auto-download;
- per-channel filters on duration and Shorts, and a limit on the initial download;
- `SourcePlaylist` and `SourcePlaylistVideo`, with discovery and the source's order;
- separate views for channels, remote playlists and local collections;
- deduplication tests when a video appears in several playlists;
- no personal collection created automatically for a channel or playlist.

## Jellyfin integration (post-MVP)

A dedicated phase, outside the MVP and **independent of subscriptions**: it can be tackled
before or after phase 4. It requires verification with a real Jellyfin instance and
touches the library layout, not just the generated files:

- basic NFO preset (§17) generated from the `Video` fields, without a Django model for the
  sidecar;
- folder layout and naming templates verified with Jellyfin (for example the TV Show
  preset);
- NFO generation for videos already archived;
- verification with a real Jellyfin library, for example a temporary container that reads
  the library read-only;
- how to exclude the `.browser/` folder of browser copies from the scan (it is already
  kept separate from the channel folders today);
- no promise of automatic compatibility with Plex: any specific rules are evaluated here,
  with dedicated tests.

It starts from the constraints the MVP already respects (§8, §17): one main file per video
with a registered path, identity independent of the path, metadata and thumbnails
available, folders that do not represent collections. No change to the existing layout is
needed to prepare for it.

## Phase 5 — Organization (post-MVP)

- full-text search;
- combined filters and advanced local organization;
- favorite;
- watched;
- notes.

## Phase 6 — Community / extensibility (post-MVP)

The MVP includes only what is needed to publish the first release: the choice of an open
source license and the essential documentation (installation, configuration, usage). The
rest is post-MVP:

- open source license chosen before the repository is published (MVP);
- API documentation and the already generated OpenAPI schema;
- dedicated authentication for external clients;
- CLI;
- documented extension points;
- contributor documentation;
- plugin/integration APIs when real requirements emerge.

Importing existing archives requires a separate specification covering recognition of
files and sidecars, deduplication and protection against overwrites. An `ImportJob`, if
any, is introduced only if persistent state is needed for the import's progress, errors
and resumption.

---

# 40. What NOT to implement initially

Do not introduce complexity just to make VHS "extensible".

In particular, the following are not needed initially:

- plugin registry;
- plugin manager;
- event bus;
- microservices;
- Redis;
- WebSocket;
- distributed storage;
- additional messaging systems;
- premature abstractions.

Also outside the MVP are the product features deferred by choice (§39):

- channel and playlist subscriptions, archive download and polling;
- Jellyfin integration (NFO, dedicated layout);
- collections created automatically from channels or playlists.

Extensibility must come from clean boundaries.

---

# 41. Testing

## Unit tests

Every service must be testable independently.

Test separately:

```text
models
services
engine
storage
naming
API schemas

```

## Engine

The engine must be testable without Django.

Use:

- yt-dlp mocks;
- real JSON fixtures;
- metadata extraction tests.

## Integration tests

Test the flow:

```text
API
 → service
 → task
 → engine
 → storage
 → Video

```

Verify that the API exposes a useful error category without including cookies or other
secrets, and that a retry creates a new attempt without losing the history. Check that a
job with no progress can be told apart from an active worker during processing.

## Local organization (MVP)

Test:

- personal tags and collections neither move nor duplicate files;
- `CollectionVideo` unique constraints and ordering under concurrent changes;
- platform tags never imported as personal tags;
- search and filters by personal tags and collections.

## Discovery (post-MVP)

With subscriptions, test:

- channel filters on duration, Shorts and initial population;
- missing or uncertain metadata without silent exclusion;
- a single `Video` present in several source playlists;
- updating the remote order without altering local `Collection`s;
- a temporarily unreachable playlist without deleting memberships;
- `SourcePlaylistVideo` unique constraints.

## Storage

Implemented (first block of Phase 3, local storage): new library initialized on the first
download (host folder with Docker), populated library that disappeared is blocked (no
writes, not even of `.incomplete` files or the marker), non-empty folder without a marker,
library that disappears during a download, new download to the same path,
`superseded_files`, recovery without transfer. The tests of the mounted mode (later
removed) are described in storage-decisions.md, §5.

Test:

- local file;
- temporary file;
- finalize;
- missing file;
- insufficient space;
- failure during writing;
- rename on the same filesystem and crash before/after promotion;
- duplicate request, re-executed job and database reconciliation;
- mismatched checksum and file present on disk but not registered (implemented in
  `test_verification.py`: library in order, missing file, mismatched size and checksum,
  unreferenced file, active and abandoned temporary files, files being promoted, symbolic
  links not followed, library unavailable or disappeared during the scan, read errors, no
  changes to DB and files);
- new download of a video whose title has changed (an `available` video without a
  completed attempt, or `missing` because of unreachable storage): the previous main file
  must not remain orphaned without a trace (phase 3).

## Streaming

Test:

- authorization;
- X-Accel-Redirect;
- direct access denied;
- Range Requests;
- nonexistent file;
- Nginx with the media mounted read-only;
- unplayable file and derived copy available.

In the phase dedicated to Jellyfin (post-MVP), verify the NFO preset with a real Jellyfin
library. The outcome does not automatically imply compatibility with Plex.

## Playback

Test:

- progress creation;
- progress update;
- progress retrieval;
- one progress per user/video.

---

# 42. Deployment verification

The full Compose setup must be able to start from scratch.

Verify:

```text
docker compose up

```

and:

- database;
- migrations;
- API;
- worker;
- Nginx;
- Vue;
- streaming;
- protected media.

Test, with the library in a host folder:

- small files;
- large files;
- files during download;
- worker restart;
- container restart;
- library temporarily unavailable;
- joint restore of database and media from a backup (done: end-to-end test
  with two isolated Compose projects. Personal data, superuser, 206 stream and a
  queued download that stayed queued until the verification; negative cases:
  destination inside the library, library unavailable, job running, job started
  while the worker was stopping, worker already stopped, failed copy that leaves
  a `.partial` that cannot be restored, non-empty folder or database, problem
  already present in the backup (outcome `3`), file removed from the backup
  (outcome `1`)).

Tests on real NFS belong to the post-MVP "Network storage" phase.

---

# 43. Security

Priorities:

### API

- authentication;
- authorization;
- input validation;
- API versioning;
- CSRF protection for operations that modify data;
- size limit on API requests (and on cookie uploads, once they are introduced,
  §14);
- validation of the URLs accepted by yt-dlp: supported schemes and hosts;
  redirects and local or private addresses must not allow requests to the
  server's internal network.

### Session and transport

The security of the session and CSRF cookies is a per-installation choice,
independent of `DEBUG`:

```text
DJANGO_SECURE_COOKIES=true   (default)  → Secure: requires HTTPS
DJANGO_SECURE_COOKIES=false             → HTTP installation on a LAN

```

- With HTTPS (own certificate, or a reverse proxy that sets
  `X-Forwarded-Proto`) the cookies stay `Secure`.
- An HTTP installation on a local network turns them off **explicitly**: login
  credentials and session cookies travel unencrypted and can be read by anyone
  observing traffic on the same network. This is acceptable only on a trusted
  network; Django flags it with the `vhs.W001` system check when `DEBUG=false`.
- The flag does not change per request: with `Secure` on, access over HTTP does
  not work (the browser does not even send back the CSRF cookie).
- In both cases the cookies stay `HttpOnly` (session) and `SameSite=Lax`.

### Media

Files are not public.

Access:

```text
API authorization
        ↓
X-Accel-Redirect
        ↓
Nginx internal location

```

This applies to videos, derived copies and thumbnails. The other sidecars are not
exposed by default.

### Platform cookies

Today VHS does not use platform cookies (§14, deferred). When they are
introduced, they must be treated as credentials.

They must be:

- encrypted at rest;
- excluded from logs;
- never returned in clear text by the APIs;
- managed as secrets;
- present in temporary files only for as long as the worker needs them;
- accessible and replaceable only by the administrator.

### Filesystem

The client must not be able to choose an arbitrary filesystem path.

The API works with:

```text
video_id

```

not with:

```text
/path/to/file.mp4

```

---

# 44. Architectural decisions

## Decision: PostgreSQL without Redis

PostgreSQL is already required for VHS.

django-q2 uses PostgreSQL for task persistence.

Redis will be introduced only if a concrete requirement arises that justifies it.

---

## Decision: Nginx instead of Caddy

Nginx is used as the reverse proxy because VHS needs a clear model for:

- protected media;
- `X-Accel-Redirect`;
- HTTP Range Requests;
- efficient transfer of large files;
- separation between application authorization and I/O.

Django decides whether the user can access the video.

Nginx transfers the file.

---

## Decision: Video separate from Download

`Video` represents the content.

`Download` represents an operation.

A Video can have multiple Downloads over time.

---

## Decision: MVP scope

The MVP covers on-demand downloads, the library, playback, local organization,
the essential part of operational reliability (storage and download failures,
verification of files and orphans, backup with a restore test) and what is
needed to publish the first release (essential documentation and license).
Subscriptions to channels and playlists (full archive and polling) and the
Jellyfin integration are outside the MVP and independent of each other;
advanced metrics and automation, advanced organization and the rest of the
community phase are post-MVP. Source channels remain metadata and filters.
MVP storage is local only (with Docker, a host folder); a library on network
storage (NFS, SMB, NAS) is post-MVP (storage-decisions.md).

---

## Decision: Recorded path, folders that do not represent collections

Every video has a main file whose relative path is recorded in the database,
computed at archive time and never recomputed. Identity and the API do not
depend on the path, title or channel name. Tags and collections are relations in
the database and neither move nor duplicate files; folders represent only
provenance. This keeps future integrations (media servers, exports) open without
changing the layout.

---

## Decision: Discovery separate from Download

Discovering that a video exists does not necessarily mean downloading it (this
applies to subscriptions, post-MVP).

This makes it possible to implement different archiving policies later without changing the discovery system.

---

## Decision: Source playlists separate from local collections

Personal collections are not created automatically per channel or playlist.

`SourcePlaylist` and `SourcePlaylistVideo` keep the platform's membership and
order. `Tag`, `Collection` and `CollectionVideo` represent organization created
in VHS. Changes to or deletion of the remote playlist do not overwrite local
choices and do not delete archived files.

---

## Decision: API-first

The Vue app uses the same API that will be available to external users.

The API must not be designed around the needs of a single Vue page.

---

## Decision: Engine independent of Django

The downloader and the metadata extractors are pure Python.

This makes it possible to test them and potentially reuse them independently of the web backend.

---

## Decision: Abstract storage

The domain does not know the concrete filesystem.

The first implementation is the local filesystem; network storage is post-MVP.

Other backends may be added in the future if a real use case arises.

---

# 45. Deferred decisions

- multi-user authentication;
- advanced role/permission management;
- subtitles;
- notifications;
- setup wizard;
- subscriptions to channels and playlists, with archive download and polling
  (Phase 4, post-MVP);
- automatic download of remote playlists with a policy distinct from the channels' one;
- import of existing archives and the related `ImportJob` model, if needed;
- custom naming templates;
- advanced backoff strategy beyond the v1 minimum retry limits;
- automation of yt-dlp updates;
- advanced quality and conversion profiles beyond the v1 base policy;
- configurable parallelism beyond the v1 safe limit;
- auto-pause on insufficient space beyond the v1 preventive check;
- advanced monitoring;
- CLI;
- official API client;
- plugin system;
- additional storage backends;
- possibly Redis;
- platform cookies (§14): encrypted `cookies.txt` or `cookiesfrombrowser`, to be
  decided when anonymous downloads are not enough;
- SSE/WebSocket;
- Jellyfin integration (NFO, verified layout) and evaluation of Plex, in a
  dedicated post-MVP phase.

These decisions must not block the v1 core. The license can be chosen after the
private prototype, but it must be defined before presenting the repository as an
open source project.

---

# 46. Project philosophy

VHS must not try to be everything from the start.

The foundation must be:

```text
                 VHS
                  │
       ┌──────────┴──────────┐
       │                     │
     API                  Library
       │                     │
       ▼                     ▼
   Services              Storage
       │
       ▼
     Engine
       │
       ▼
     yt-dlp

```

Every component must be able to evolve without dragging the whole project along with it.

The goal is not to build a complex architecture.

The goal is to build **simple, solid boundaries**.

If the boundaries are right, extensibility toward the community will emerge naturally.
