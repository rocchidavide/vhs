# Contributing to VHS

Thanks for your interest! Bug reports, ideas and pull requests are welcome.

- **Ideas, feature requests and questions:** start a discussion in
  [Discussions](https://github.com/rocchidavide/vhs/discussions) (Ideas or Q&A). What comes
  next in VHS depends on this feedback.
- **Bugs:** open an issue, with the VHS version, how you installed it and the steps to
  reproduce it.
- **Larger changes:** open an issue first to discuss the approach, so that no work goes
  into a direction that does not fit the project.
- **Security problems:** do not open a public issue; see [SECURITY.md](SECURITY.md).

## Working on the code

- Set up the development environment with [docs/development.md](docs/development.md):
  everything runs in containers, and `./dev` gathers the everyday commands.
- Follow the rules in [docs/conventions.md](docs/conventions.md) and the architecture in
  [docs/architecture.md](docs/architecture.md).
- Everything is in English: code, comments, commit messages and documentation. Interface
  texts go through i18n (`frontend/src/locales/en.json`, or gettext in Django), never
  written directly in the code.
- Before opening a pull request, run `./dev test`, `./dev test-frontend` and `./dev lint`.
  The CI runs the same checks on every pull request.

## Releasing

Dependabot opens pull requests for dependency updates ([.github/dependabot.yml](.github/dependabot.yml)):
Python every day, with yt-dlp in a pull request of its own, the rest every week.

- A **yt-dlp** update that fixes a platform change is released right away: merge the pull
  request once the CI is green, then release a patch version (0.1.x).
- To release: update the version in `pyproject.toml` and in `frontend/package.json` (and
  `package-lock.json`), merge to `main`, create an annotated tag (`git tag -a v0.1.2`) and a
  GitHub release with the notes. Installations see the new version on their Home page.

By contributing, you agree that your contribution is released under the project's
[MIT License](LICENSE).
