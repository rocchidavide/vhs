# Installing VHS

This guide is for people who **use** VHS: installing it on a server or a home computer,
keeping it up to date, backing up its data. To work on the code, see
[development.md](development.md).

A VHS installation is made of:

- **a folder for the videos**, chosen by you (for example `/srv/vhs/library`);
- **a PostgreSQL database**, which Docker keeps in its own volume;
- four containers: `db`, `backend`, `worker` (the downloads) and `nginx`
  (the web interface).

## Requirements

- A Linux server, a VM or a home computer with a recent **Docker** and **Docker
  Compose** (the `docker compose` plugin) that supports the `!override` and `!reset`
  tags in Compose files. VHS is tested with Compose 5.4 and 5.5; with a version that is
  too old, `docker compose` stops immediately with an error while reading the files.
  Install Docker from its official packages
  ([instructions](https://docs.docker.com/engine/install/)), not from the snap package,
  whose confinement limits access to folders such as `/srv`.
- **Your user can run `docker` without `sudo`:** add it to the `docker` group, as in
  Docker's [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/)
  (`sudo usermod -aG docker $USER`), then log out and back in. Check with `docker ps`.
  Members of the `docker` group have root-level control of the machine: add only
  trusted users.
- **git**, to download and update VHS.
- **rsync**, for backups.
- Disk space for the videos: the library folder must be on the server's own disk.

> **Not supported in this version:** libraries on network shares (NFS, SMB, NAS) or
> on separately mounted disks, because VHS cannot detect a missing mount in every
> situation. Reasons and plans:
> [storage-decisions.md](storage-decisions.md).

### Tested environments

VHS 0.1 has been tried on these systems (October 2026). Others with a recent Docker and
Compose should work too: these are only the combinations checked so far.

| System | Architecture | Docker / Compose | What was checked |
|---|---|---|---|
| Ubuntu Server 26.04.1 LTS (virtual machine) | arm64 | 29.8.2 / 5.5.1 | the whole guide: installation, sign-in over HTTP from another computer, a real download, playback (including seeking), symlink protection, backup and restore with `sudo`, automatic restart after a reboot; the update from 0.1.0 to 0.1.1 |
| Linux Mint 22.2 (based on Ubuntu 24.04) | x86_64 | 29.8.1 / 5.5.1 | installation and everyday use, file ownership (uid 1000) |
| macOS 26.6 with Docker Desktop | arm64 (Apple Silicon) | 29.7.2 / 5.4.0 | installation with sign-in over HTTP from the local network; development environment |

Every change is also tested automatically on Ubuntu x86_64 (backend and frontend tests,
production images): see the CI in `.github/workflows/ci.yml`.

## 1. Download VHS

```bash
git clone https://github.com/rocchidavide/vhs.git
```

```bash
cd vhs
```

All the commands in this guide are run from this folder.

## 2. Prepare the video folder

The folder must exist before startup and be writable by the containers' user
(uid 1000):

```bash
sudo mkdir -p /srv/vhs/library && sudo chown 1000:1000 /srv/vhs/library
```

Nginx only reads it: the files VHS creates are readable by everyone.

If the folder does not exist, the containers are not created, and Docker does not
create it for you. An empty folder becomes the library at the first download.

## 3. Configure

Start from the template:

```bash
cp .env.example .env
```

and adjust the values in `.env`. These are the essential lines:

```text
# Secret key: a long, random string (see below)
DJANGO_SECRET_KEY=replace-with-a-random-string
DJANGO_DEBUG=false

# Names and addresses you use to open VHS in the browser
DJANGO_ALLOWED_HOSTS=vhs.lan,192.168.1.50

# HTTP on a local network (see "HTTPS or HTTP on a local network"): with HTTPS remove
# these two lines and use https:// origins
DJANGO_SECURE_COOKIES=false
DJANGO_CSRF_TRUSTED_ORIGINS=http://vhs.lan,http://192.168.1.50

# Database password: choose a strong one
POSTGRES_PASSWORD=replace-with-a-password

# The video folder prepared in step 2
VHS_HOST_LIBRARY=/srv/vhs/library

# Compose files to use: this way every command is simply "docker compose ..."
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

To generate the secret key:

```bash
openssl rand -base64 48
```

Keep a copy of `.env` somewhere safe: it contains the key and the password, and VHS
backups do not include it.

## 4. Start

```bash
./vhs start
```

On the first start the images are built and the database tables are created (this
takes a few minutes). Then create the user to sign in with:

```bash
./vhs create-user
```

Open `http://<server-address>/` and sign in. VHS answers on port 80 (and 443, if you
configure HTTPS).

## The `./vhs` command

`./vhs`, in the VHS folder, bundles the commands of this guide. Each one prints the
`docker compose` command it runs, so you can always do without it. It contains no
commands that delete data, and it refuses to start with the development `.env`.
`./vhs help` lists everything; the messages are in English.

| What | `./vhs` | Equivalent command |
|---|---|---|
| Start VHS | `./vhs start` | `docker compose up -d` |
| Stop it | `./vhs stop` | `docker compose stop` |
| See the services | `./vhs status` | `docker compose ps` |
| Follow the logs | `./vhs logs [service]` | `docker compose logs -f [service]` |
| Create a user | `./vhs create-user` | `docker compose exec backend python manage.py createsuperuser` |
| Library status | `./vhs storage-status` | `… manage.py storage_status` |
| Verify the library | `./vhs verify [--checksums]` | `… manage.py verify_library` |
| Initialize an existing library | `./vhs init-library` | `… manage.py init_library` |
| Backup | `sudo ./vhs backup <folder>` | `scripts/backup.sh <folder>` |
| Restore | `sudo ./vhs restore <backup>` | `scripts/restore.sh <backup>` |
| Update | `./vhs update` | `git pull` and `docker compose up -d --build` |
| Other Django commands | `./vhs manage <command>` | `… manage.py <command>` |

> `./dev` is **only for people who develop** VHS: in an installation it refuses to
> start. Use `./vhs`.

## HTTPS or HTTP on a local network

`DJANGO_SECURE_COOKIES` decides whether session cookies travel only over HTTPS.

- **HTTPS** (recommended): remove the `DJANGO_SECURE_COOKIES=false` line (the default
  is `true`) and use `https://` addresses in `DJANGO_CSRF_TRUSTED_ORIGINS`. Put the
  certificate and key in `certs/` (`fullchain.pem`, `privkey.pem`), and uncomment the
  `./certs:/etc/nginx/certs:ro` line in `docker-compose.prod.yml` and the TLS block in
  `docker/nginx.conf`.
- **HTTP on a trusted local network:** `DJANGO_SECURE_COOKIES=false`, otherwise
  sign-in does not work (the browser does not send `Secure` cookies back over HTTP).

> **Warning:** with HTTP the password and the session cookie travel **unencrypted**:
> anyone watching the traffic on the same network can read them. This is acceptable
> only on a trusted network. `./vhs manage check` reminds you of this with the
> `vhs.W001` warning.

## Using VHS

- **Downloading:** on the **Downloads** page, paste the URL of a YouTube video. VHS
  downloads it in the background together with its thumbnail and metadata. A failed
  download can be retried from the same page.
- **Library:** search and filter the videos, also by source channel.
- **Playback:** the video's page plays it and resumes where you left off. Videos in
  formats the browser cannot play directly are adapted: a container change happens
  automatically; a full conversion starts only if you press **"Prepare for
  playback"**. The original is never modified.
- **Organizing:** **personal tags** and sortable **collections**, independent of the
  platform's tags and playlists.

## The library

In the video folder VHS places a hidden file, `.vhs-library`, that identifies it.
**Do not delete it:** VHS writes only where it finds it. If the folder disappears or
is replaced (renamed, moved, wrong path in `.env`), VHS stops: downloads and
conversions fail without writing anything, videos do not play and the interface
shows a warning.

| Situation | What to do |
|---|---|
| New, empty folder | nothing: the marker is created at the first download |
| Existing VHS library without a marker (for example copied by hand) | once: `./vhs init-library` |
| "Library not available." warning | put the folder back in its place or fix `VHS_HOST_LIBRARY` |

`init_library` checks that the registered videos are really there, and refuses
otherwise.

To see the state of the library:

```bash
./vhs storage-status
```

### Verifying the library

`verify_library` compares the database with the video folder. It is **read-only**:
it changes nothing and does not follow symbolic links.

```bash
./vhs verify
```

It reports:

- **missing main files**;
- **size different** from the registered one;
- **different checksum**, only with `./vhs verify --checksums` (it rereads every
  video: on a large library this takes a long time);
- **files with no reference** in the database, for example files added by hand;
- **abandoned temporary files** from downloads or conversions that are no longer
  active;
- **symbolic links**.

Downloads and conversions still in progress are listed separately and are not
problems. Outcome: `0` no problems, `1` problems found, `2` **incomplete check** (for
example, library unavailable): an incomplete check never says that the library is in
order. The command fixes nothing.
On a fresh installation, before the first download, the check is incomplete because
the library is not initialized yet: this is normal.

## Backup and restore

The database and the video folder must be backed up **together**: each holds data the
other cannot rebuild.

| Data | Where it is stored | Restored from |
|---|---|---|
| Video files, thumbnails, `.info.json` metadata, browser copies (`.browser/`) | the library folder | the copy of the library |
| Video records (titles, checksums, playback analysis), **personal tags, collections, watch progress**, users, download history | the PostgreSQL database | the database dump only |
| Secret key, passwords and settings | `.env` | not included in the backup: keep a copy of `.env` separately |

**VHS 0.1 cannot rebuild the database from the library folder.** Without the database
dump, the videos and their `.info.json` files stay usable (they are plain files, readable
without VHS), but personal tags, collections and watch progress are lost. The `.info.json`
files keep the platform's full original metadata (title, description, channel, upload
date, tags), so each video stays identifiable even without VHS. The two scripts
below always save and restore the database and the library together. On Linux run them
with `sudo`, so that the copy preserves the file owners.

### Backup

```bash
sudo ./vhs backup /path/to/backups
```

It creates `vhs-backup-YYYYMMDD-HHMMSS/` with the database (`database.dump`), a full
copy of the video folder (`library/`), the verification report at backup time
(`verify-at-backup.json`) and a summary (`manifest.txt`).

- It refuses if the library is unavailable, if the destination is inside the library
  or if a download or a conversion is **running**: in that case, try again later.
- During the backup it stops the downloads (the `worker` service) and restarts them
  at the end, only if they were running. The interface stays available.
- An interrupted backup stays in a `.vhs-backup-….partial` folder: it is not a usable
  backup and cannot be restored.
- Every backup is a **full copy**, and the checksum verification rereads every video:
  on a large library this takes time.

Keep the backups **on another disk** whenever possible: a copy on the same disk does
not protect against that disk failing. And keep the `.env` file separately.

### Restore

You restore into a **new, never-started** installation: follow steps 1–3 of this
guide (the `.env` can be the one you saved), but **not** step 4. Then:

```bash
sudo ./vhs restore /path/to/backups/vhs-backup-YYYYMMDD-HHMMSS
```

The backup and restore scripts write their messages in English.

The script refuses if the video folder is not empty or if the database already
contains data: it never overwrites an installation in use. It restores the database
and the videos, verifies everything with checksums before re-enabling downloads, and
saves the outcome in `restore-reports/`:

| Outcome | Meaning | VHS |
|---|---|---|
| `0` restore succeeded (`RESTORE SUCCEEDED`) | no problems | started |
| `3` data restored, with problems already present in the backup (`DATA RESTORED, WITH PROBLEMS ALREADY PRESENT IN THE BACKUP`) | the problems found were already there at backup time | started |
| `1` restore failed (`RESTORE FAILED`) | new problems (for example a file missing from the copy) or incomplete verification | **not** started: check the listed problems |

## Updating VHS

Make a backup first, then:

```bash
./vhs update
```

It asks for confirmation, downloads the new version (`git pull`) and rebuilds the
images (`docker compose up -d --build`). Database migrations are applied
automatically at startup.

**Knowing when to update.** The Home page shows the versions of VHS and yt-dlp, and announces
a newer VHS release with a link to its notes. To find out, the server asks GitHub's public
API for the latest release at most twice a day. The request carries only the VHS version
(in its User-Agent header); like any request, it shows GitHub the server's IP address. Set
`VHS_UPDATE_CHECK=false` to turn this off.

New VHS releases often carry a newer yt-dlp: when a platform changes something and
downloads break, a fixed yt-dlp reaches VHS as a regular release, tested with the rest of
VHS. Updating regularly keeps downloads working.

## Stopping and restarting

```bash
./vhs stop
```

```bash
./vhs start
```

`docker compose down` removes the containers and touches neither the videos nor the
database. **Never use `docker compose down -v`**: it deletes the database volume.

## Settings

Besides those in step 3, in `.env` you can adjust:

| Variable | Default | Description |
| --------- | ------- | ----------- |
| `VHS_NAMING_TEMPLATE` | `standard` | folder layout: `standard` or `tvshow` |
| `VHS_MIN_FREE_BYTES` | `1073741824` | free space (bytes) that must remain after a download |
| `VHS_DOWNLOAD_STALL_SECONDS` | `300` | after how many seconds without progress a download is reported as stalled |
| `VHS_WORKERS` | `2` | concurrent downloads and conversions |
| `VHS_TRANSCODE_PRESET` | `veryfast` | conversion speed (`libx264` preset) |
| `VHS_TRANSCODE_CRF` | `21` | conversion quality (lower = higher quality, larger file) |
| `VHS_TRANSCODE_AUDIO_BITRATE` | `160k` | audio bitrate of conversions |
| `VHS_FFMPEG_THREADS` | `0` | ffmpeg threads (`0` = automatic) |
| `VHS_MEDIA_TOOL_TIMEOUT` | `21600` | maximum duration of an analysis or conversion, in seconds |
| `VHS_TASK_TIMEOUT` | `21600` | maximum duration of a download, in seconds |
| `VHS_TASK_RETRY` | `22500` | seconds before an unacknowledged job is handed out again; must exceed `VHS_TASK_TIMEOUT` |
| `VHS_LOG_LEVEL` | `INFO` | log level |
| `VHS_TIME_ZONE` | `UTC` | time zone used to display dates, for example `Europe/Rome` (dates are always stored in UTC) |
| `VHS_UPDATE_CHECK` | `true` | ask GitHub for the latest VHS release, at most twice a day, to announce it on the Home page |
| `VHS_YTDLP_AUTO_UPDATE` | `false` | emergency only: install the latest yt-dlp at every start ([Troubleshooting](#troubleshooting)) |
| `POSTGRES_DB` / `POSTGRES_USER` | `vhs` | database name and user |

## Troubleshooting

**A download fails with "The platform requires signing in".** The platform asked for a
login or for proof that the request does not come from a bot; the detail under the error
often says "Sign in to confirm you're not a bot". VHS downloads without platform cookies
in this version, so it cannot sign in. Most often the cause is the reputation of the
server's internet address, not VHS:

- servers in a data center (a VPS, a cloud machine) and VPNs are blocked much more often
  than a home connection: run VHS at home, or turn the VPN off for the server;
- many downloads in a short time can trigger the check: wait a while and use **Retry**;
- the platform may have changed something that yt-dlp has fixed since: update VHS
  ([Updating VHS](#updating-vhs)), which brings a newer yt-dlp;
- videos that really require an account (age-restricted, members-only, private) cannot
  be downloaded yet: support for platform cookies is planned.

**Downloads started failing after a platform change, with "Unexpected error" or "Network
error" on videos that used to work.** The platform probably changed something that only a
newer yt-dlp handles. Update VHS ([Updating VHS](#updating-vhs)): the Home page and each
failed download show the yt-dlp version in use. If no VHS release with a fix is out yet, you
can turn on the emergency option `VHS_YTDLP_AUTO_UPDATE=true` in `.env` and run
`./vhs start`: the backend and the worker then install the latest yt-dlp at every start.
That version has not been tested with VHS, and the Home page says so; turn the option off
again once a VHS release with the fix is out.

**Every download fails with "Network error".** The server cannot reach the platform: check
its internet connection and DNS. A VPN or firewall on the server, or on the computer that
runs a virtual machine, can block the containers even when the browser works.

**`./vhs start` fails with "permission denied" on `docker.sock`.** Your user cannot run
Docker without `sudo`: add it to the `docker` group ([Requirements](#requirements)), then
log out and back in.

**The page opens, but sign-in fails with "Sign-in failed. Try again shortly."** If the API
answers "Bad Request (400)" (for example at `http://<address>/api/v1/health`), the address
you used to open VHS is not in `DJANGO_ALLOWED_HOSTS`: add the name or IP address to
`.env`, together with its origin in `DJANGO_CSRF_TRUSTED_ORIGINS`, and run `./vhs start`
again.

**Sign-in keeps failing with "Your session has expired".** You are using plain HTTP with
secure cookies: set `DJANGO_SECURE_COOKIES=false` and use `http://` addresses in
`DJANGO_CSRF_TRUSTED_ORIGINS`, or switch to HTTPS
([HTTPS or HTTP on a local network](#https-or-http-on-a-local-network)).

**The "Library not available." warning appears.** VHS cannot find its library folder, or
the folder is not the one it knows: see [The library](#the-library). Nothing is written
until it is back.

**A download fails with "Storage error" and "Not enough space".** The library disk does not
have room for the video plus the reserve set by `VHS_MIN_FREE_BYTES`: free some space or
lower the reserve ([Settings](#settings)).

**A video does not play.** Open its page: if the browser copy is not ready, press
**"Prepare for playback"** to convert it (the original file is not changed).

If none of this helps, open an issue with the VHS version, how you installed it and the
error shown on the Downloads page.
