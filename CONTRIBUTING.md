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
  request once the CI is green, then release a patch version (0.3.x).
- Installations run only releases: the images and the `vhs.tar.gz` bundle published for a
  tag. `main` is where development happens; merging to it reaches nobody until a release.

To release:

1. In a pull request, update the version in `pyproject.toml` (then run `uv lock`), in
   `frontend/package.json` (and `package-lock.json`) and in the two VHS images of
   `docker-compose.yml`; a test checks that they agree. Merge it.
2. Create an annotated tag on that commit and push it (`git tag -a v0.2.1`,
   `git push origin v0.2.1`). The release workflow
   ([.github/workflows/release.yml](.github/workflows/release.yml)) builds and publishes the
   images for x86_64 and arm64, installs VHS from the bundle on both, and creates a **draft**
   GitHub release with `vhs.tar.gz` attached.
3. Write the notes in the draft and publish it as the latest release: installations read it
   to announce the new version on their Home page, and `./vhs update` downloads it.

To test a release before publishing it, push a `vX.Y.Z-rc.N` tag: the workflow publishes
images under that tag and a pre-release, which installations never see.

By contributing, you agree that your contribution is released under the project's
[MIT License](LICENSE).
