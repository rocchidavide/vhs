# VHS — Video Hoarding System

A personal video library to download, archive, organize and play videos
from YouTube (and, in the future, from other platforms). API-first: the Vue SPA is a
client of the `/api/v1/` API.

Status: **MVP in progress**: Phases 0, 1, 2a, 2b and the essential part of Phase 3
implemented; the first release still needs a license.

On the Downloads page you paste the URL of a YouTube video: VHS downloads it in the
background, archives it with the `.info.json` and `.webp` sidecars and records its SHA-256
checksum. The Library lets you search and filter videos (by source channel too); the video
page plays them through protected streaming and resumes where you left off. Videos are
organized with **personal tags** and sortable **collections**, separate from the
platform's tags and playlists.

## MVP scope and roadmap

In the MVP, videos enter VHS only through a URL requested by the user.

| Area | Status |
| ---- | ----- |
| On-demand downloads, library, playback, formats | MVP, implemented |
| Personal tags and collections | MVP, implemented |
| Essential reliability (Phase 3), with local storage: unavailable library, orphaned main file, file verification, backups with a restore test | MVP, implemented |
| Installation and development guides | MVP, written |
| License for the first release | MVP, to do |
| Metrics and advanced automation (Phase 3) | post-MVP |
| Subscriptions to channels and playlists (full archive, polling) | post-MVP |
| Jellyfin integration (NFO, layout, excluding `.browser/`) | post-MVP, independent of subscriptions |
| Library on network storage (NFS, SMB, NAS) | post-MVP, not supported ([criteria](docs/storage-decisions.md)) |
| Advanced organization and community (Phases 5 and 6) | post-MVP |
| Platform cookies | deferred as long as anonymous downloads work |

Source channels remain metadata and a Library filter; collections are never
created automatically from channels or playlists. Details in §39 of
[architecture.md](docs/architecture.md).

## Documentation

- **[Installing VHS](docs/installation.md)**: for users. Requirements,
  video folder, configuration, startup, HTTPS, library verification,
  backup and restore, updates.
- **[Developing VHS](docs/development.md)**: for people who work on the code. Development
  environment, player, tests, full test stack.
- [Architecture](docs/architecture.md), [conventions](docs/conventions.md) and
  [storage and backup decisions](docs/storage-decisions.md).

In short, an installation is a folder for the videos, a PostgreSQL database and
four Docker containers:

```bash
git clone https://github.com/rocchidavide/vhs.git && cd vhs
```

Then prepare the video folder and the `.env` as described in
[installation.md](docs/installation.md), and start with `./vhs start`. From then
on, `./vhs` gathers the everyday commands (`./vhs help`).

## License

To be defined before publication as an open source project.
