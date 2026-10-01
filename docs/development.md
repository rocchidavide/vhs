# Developing VHS

This guide is for people who work on the code. To install and use VHS, see
[installation.md](installation.md). Architecture and design choices:
[architecture.md](architecture.md); code rules:
[conventions.md](conventions.md); storage and backups:
[storage-decisions.md](storage-decisions.md).

## How it works

VHS **always runs in containers**, in development too. The development environment uses
the same `docker-compose.yml` as an installation, plus the
`docker-compose.dev.yml` override, which:

- mounts the repository into the containers, so code changes take effect
  immediately;
- starts Django with `runserver`, which reloads by itself, and the worker with
  `watchfiles`, which restarts it when the Python code changes;
- adds the `frontend` service with the Vite development server (HMR);
- routes everything through **Nginx**, as in production: a single address,
  **http://localhost:8081**, reachable only from the computer itself.

The services talk to each other by name inside the Docker network, so the environment is
identical on Linux and macOS. There is one database (volume `vhs-dev_pgdata`) and one
video folder (`./video-library`, excluded from git).

## Requirements

- **Docker** with a recent **Docker Compose** that supports the `!override` and
  `!reset` tags in Compose files (VHS is tested with Compose 5.4; a version that is too
  old stops immediately with an error reading the files).
- **git**.
- Optional, for the editor only: **Node.js** 22.18+ or 24.12+, so that PyCharm
  understands the Vue and TypeScript code (see "PyCharm").

Python, uv, ffmpeg, deno and the dependencies are all in the images: you do not need
them on your computer.

## First start

```bash
cp .env.dev.example .env
```

```bash
mkdir -p video-library
```

```bash
./dev build
```

`./dev` is the development command (see "Daily use"): `./dev build` builds the images and
starts the environment.

The development `.env` contains `COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml`:
this is why, in the project folder, `./dev` and every `docker compose …` act on the
development environment, without `-f`. Do not use it for an installation: that one
starts from `.env.example`.

Then create your user:

```bash
./dev manage createsuperuser
```

and open **http://localhost:8081**.

**Linux:** if your user does not have uid and gid 1000 (`id -u`, `id -g`), set
`VHS_UID` and `VHS_GID` in the `.env`, so that the files created in the repository (for
example migrations) stay yours.

## Daily use

The `./dev` script, in the project folder, shortens the most frequent
commands. Each one prints the `docker compose` command it runs, so you can
always do without it. It contains no commands that delete data, and it refuses to
start if the `.env` is not the development one. `./dev help` lists everything.
Its counterpart for installations is `./vhs` ([installation.md](installation.md)),
which in turn refuses to start with the development `.env`.

| What | `./dev` | Equivalent command |
|---|---|---|
| Start the environment | `./dev start` | `docker compose up -d` |
| Stop it | `./dev stop` | `docker compose stop` |
| See the services | `./dev status` | `docker compose ps` |
| Follow the logs | `./dev logs [service]` | `docker compose logs -f [service]` |
| Rebuild the images | `./dev build` | `docker compose up -d --build` |
| Backend tests | `./dev test [arguments]` | `docker compose exec backend pytest` |
| Frontend tests | `./dev test-frontend` | `docker compose exec frontend npm run test:unit -- --run` |
| Lint and type-check | `./dev lint` | ruff in the backend, `npm run lint` and `npm run type-check` in the frontend |
| Django commands | `./dev manage <command>` | `docker compose exec backend python manage.py <command>` |
| New migration | `./dev makemigrations` | `… manage.py makemigrations` |
| Apply it right away | `./dev migrate` | `… manage.py migrate` |
| Django shell | `./dev shell` | `… manage.py shell` |
| After a PyCharm debug session | `./dev after-debug` | `docker compose up -d --no-deps backend worker` |
| Check the Compose files | `./dev check-config` | `scripts/check-dev-config.sh` |

Migrations are also applied on every `./dev start`, by the
`migrate` service, which uses the same mounted code as `backend` and `worker`.

**When you need to rebuild the images** (`./dev build`): only
if the dependencies (`pyproject.toml`/`uv.lock`) or the Dockerfiles change. Not for
code. If `frontend/package-lock.json` changes, restarting the
`frontend` service is enough (`docker compose restart frontend`): it runs
`npm install` at startup.

**`down` and `down -v`:** `docker compose down` removes the containers and touches
neither the database nor the videos. `down -v` **deletes the development database**.

To check the resulting configuration of the Compose files (ports, builds,
mounts), for example after editing them: `./dev check-config`.

## PyCharm

With PyCharm Professional, the Python used by the editor is the one in the container.

**Backend interpreter:** Settings → Project → Python Interpreter → Add
Interpreter → **On Docker Compose**.

- Configuration files: `docker-compose.yml` and `docker-compose.dev.yml`, in
  this order.
- Service: `backend`.
- Python: `/opt/venv/bin/python`.

**Debugging Django:** a **Django Server** run configuration with that interpreter,
host `0.0.0.0`, port `8000`. When you start it in Debug, PyCharm takes the place of the
`backend` container: Nginx keeps forwarding requests to it, so a
breakpoint stops when you open a page from http://localhost:8081.

**Debugging the worker:** a second On Docker Compose interpreter with Service
`worker`, and a **Python** run configuration with script `backend/manage.py`,
parameters `qcluster` and working directory `backend`. In Debug, PyCharm takes the
place of the `worker` container: a breakpoint in the download code stops
when a download starts.

**After debugging**, the service that PyCharm replaced stays stopped.
Bring it back up with `./dev after-debug` (`docker compose up -d --no-deps
backend worker`: `--no-deps` avoids also relaunching the `migrate` service).

The run configurations are needed **only in Debug**: the containers already run with
automatic reloading. A configuration started in Run would replace the
container in the same way, with no benefit; for the worker, also without the
automatic restart of `watchfiles`. Host and port must stay `0.0.0.0` and
`8000`, otherwise Nginx cannot reach the backend (502).

**Frontend in the editor:** for completion and errors in Vue and TypeScript,
PyCharm must see the dependencies. Run `npm install` once in
`frontend/` on your computer: it is only for the editor. The container uses its own
`node_modules`, in a volume, and the two do not mix.

## How a download works

1. `POST /api/v1/downloads/` normalizes the URL (only YouTube hosts are accepted
   today), extracts the metadata and deduplicates the video on
   `(platform, platform_id)`. There is at most one active download per video.
2. The django-q2 worker downloads into `.incomplete/<id>/` inside the library, on the
   same filesystem.
3. The file is promoted with an atomic hard link that never overwrites an
   existing copy; only after that does the `Video` become `available`.
4. Every 5 minutes (and on every `./dev start`) the reconciliation re-enqueues
   downloads left in the queue, marks those without a heartbeat as `interrupted`,
   registers files already promoted before a crash and cleans up `.incomplete`.
   Manually: `./dev manage reconcile_downloads`.

After each download, `ffprobe` analyzes the file and decides how to play it
(original, automatic container change, on-demand conversion into
`.browser/`). To analyze videos that are already archived: `./dev manage analyze_media`
(`--all` to re-analyze all of them).

Library commands, useful in development too, with `./dev manage`: `storage_status`,
`init_library`, `verify_library` (see
[installation.md](installation.md#the-library)).

## Translations

Source texts are English, in the code: the English catalog is the code itself (Django)
and `frontend/src/locales/en.json` (SPA). English is the only language available today;
the environment is ready for more. No text is written directly in the interface code
([conventions.md](conventions.md#style)): ESLint reports raw text in the templates and
keys missing from a catalog.

The language follows the browser (`Accept-Language`, sent by the SPA to the API); a
language saved in the user account will come later. Platform metadata (titles,
descriptions, tags) is never translated.

**Adding a language** (for example Italian, `it`):

1. SPA: create `frontend/src/locales/it.json` with the same keys as `en.json`, then in
   `frontend/src/i18n/index.ts` import it, add `'it'` to `SUPPORTED_LOCALES` and to
   `messages`.
2. Django: add `("it", "Italiano")` to `LANGUAGES` in `backend/config/settings.py`,
   then extract and translate the messages:

   ```bash
   mkdir -p backend/locale
   ```

   ```bash
   ./dev manage makemessages -l it
   ```

   Translate `backend/locale/it/LC_MESSAGES/django.po`, then compile it for the
   development environment:

   ```bash
   ./dev manage compilemessages
   ```

   Commit the `.po` files only: the production image compiles the catalogs when it is
   built.
3. Run `./dev lint` and `./dev test-frontend`, and check the pages with the browser set
   to the new language.

## Trying VHS the way a user installs it

The development environment uses the same services as the installation, but with mounted
code and `DEBUG=true`. To try a real installation (built images,
compiled SPA, `DEBUG=false`, backup and restore), install VHS **in another
folder** following [installation.md](installation.md), with its own
`.env` and its own video folder, and remove it when you are done.

If you try it on the same machine, give the test installation its own project
name and port (`COMPOSE_PROJECT_NAME=vhs-test`,
`VHS_HTTP_PORT=8090` and `COMPOSE_FILE=docker-compose.yml` in its `.env`),
because `docker-compose.prod.yml` uses port 80. Clean up with
`docker compose down -v` **from its folder**: there it acts only on
that installation.

## Development variables

Those in `.env.dev.example`, in addition to the settings described in
[installation.md](installation.md#settings):

| Variable | Default | Description |
| --------- | ------- | ----------- |
| `COMPOSE_FILE` | — | `docker-compose.yml:docker-compose.dev.yml`: every `docker compose` uses the development environment |
| `DJANGO_DEBUG` | `false` | `true` in development |
| `VHS_HOST_LIBRARY` | — | development video folder, `./video-library` |
| `VHS_DEV_HTTP_PORT` | `8081` | Nginx port in development, only on `127.0.0.1` |
| `VHS_UID` / `VHS_GID` | `1000` | user of the development containers; on Linux, your ids if different from 1000 |
| `VHS_MEDIA_ACCEL_PREFIX` | `/media-internal/` | internal Nginx location used for `X-Accel-Redirect` |
