# Conventions

Rules that apply to all of the VHS code. The complete reference is
[architecture.md](architecture.md).

## Source data vs local organization

- Metadata, categories and tags coming from the platform stay in
  `platform_metadata` and in the acquired snapshot (`source_metadata_snapshot`).
  **They are not imported automatically** as local `Tag`s.
- Collections created in VHS are `Collection` / `CollectionVideo` (order
  chosen by the user). Platform playlists, with subscriptions
  (post-MVP), will be `SourcePlaylist` / `SourcePlaylistVideo` (source
  order). The two worlds do not overwrite each other: a remote change does not touch
  local choices and does not delete archived files.
- `Tag` and `Collection` are always local VHS data; in the interface tags are
  called "personal tags". No collection is created automatically from a
  channel or a playlist.

## Files and paths

- Every archived video has a main file; its path relative to
  `VHS_MEDIA_ROOT` is in `Video.file_path` and is computed only
  at archive time. Afterwards it is read from the database: do not recompute it from the title,
  channel or template.
- Identity and the API use `(platform, platform_id)` and the video ID, never the
  path, the title or the channel name.
- Tags, collections and other relations neither move nor duplicate files; folders
  represent only provenance.
- Storage never creates `VHS_MEDIA_ROOT` (sole exception: the new library
  created by `library_service.prepare_for_write()`) and does not write without an
  available library: every method that creates or modifies files calls
  `_require_available()`. The `.vhs-library` marker is created only by
  `init_library` or for the new library, never at startup, during reconciliations
  or by health checks. New code that writes to the library goes through storage.
- Before writing, tasks call `prepare_for_write()`; reconciliations
  stop if the library is unavailable; a video is marked `missing` only when
  the library is available (`can_mark_missing()`).
- No library file is deleted automatically to "tidy up":
  missing files, mismatched checksums and orphans are reported; removal
  is an explicit choice. A new path for an already archived video must
  not lose track of the previous file.
- File verification (`verification_service`) is read-only: no
  `save`, no writes to the library, symbolic links never followed. A
  check that could not see everything declares itself incomplete, never "in
  order".
- Sidecars (`.webp`, `.info.json`) have the same basename as the main
  file. The browser copy instead lives in `.browser/`, with the same
  path as the original and a `.mp4` extension: channel folders
  contain only one video file per item.

## Boundaries between layers

| Layer | May use | Must not |
| ------- | --------- | -------- |
| `api/` | services, schemas | contain business logic, call yt-dlp or the filesystem |
| `services/` | ORM, engine, storage | know whether it is invoked by the API, a task, the CLI or a test |
| `tasks/` | services | contain logic: `task(id)` → `Service.method(id)` |
| `engine/` | Python, yt-dlp, ffmpeg | import Django, Ninja, django-q2 or the models (checked by `tests/test_boundaries.py`) |
| `storage/` | filesystem | know about the Django models |

- The API works with IDs (`video_id`), never with filesystem paths.
- Tasks receive only IDs and must be re-runnable without duplicate effects.
- Platform cookies are credentials: never in logs, never returned in plain text.

## Style

- Python: `ruff check` and `ruff format` (configured in `pyproject.toml`).
- Frontend: `npm run lint`, `npm run type-check`.
- UI and API texts are English source texts through i18n (vue-i18n in the SPA, gettext in
  Django): no text written directly in the interface code. Documentation, code comments,
  logs, commits and script messages are in English.
