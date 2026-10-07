# VHS — notes for Claude

Self-hosted video library: Django + Django Ninja + django-q2 (`backend/`), Vue 3 SPA
(`frontend/`), Nginx and PostgreSQL, in Docker Compose. Installations usually run on a local
network, often over plain HTTP: defaults must work there.

The project rules, loaded here:

@docs/conventions.md

Open when needed: [docs/architecture.md](docs/architecture.md) (the reference, cited as §N),
[docs/development.md](docs/development.md) (the environment),
[CONTRIBUTING.md](CONTRIBUTING.md) (pull requests and releases).

## Development environment

- Use `./dev` (`./dev help`), never `./vhs`, which is for installations. Never run
  `docker compose down -v`: it deletes the development database.
- Commands run inside the containers, so the environment must be up (`./dev start`). One
  backend test: `./dev test tests/test_x.py -k name` (paths are relative to `backend/`).
- New migrations: `./dev makemigrations`, and commit them with the model change.

## Before a pull request

- Always: `./dev test`, `./dev test-frontend`, `./dev lint`.
- Compose files changed: `./dev check-config`. Nginx configs: `./dev check-symlinks`.
  Shell scripts: `shellcheck`. GitHub workflows: `actionlint`.

## Workflow

- Every change goes through a pull request from a branch, docs included. `main` is
  development; users only get releases (steps in CONTRIBUTING.md, test with
  `vX.Y.Z-rc.N` tags first).
- After a pull request is merged: `./dev sync`.
