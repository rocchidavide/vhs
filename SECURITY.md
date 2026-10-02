# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately through
GitHub's [private vulnerability reporting](https://github.com/rocchidavide/vhs/security/advisories/new)
(the "Report a vulnerability" button in the repository's Security tab).

Include what you can:

- the affected version or commit;
- the steps to reproduce the problem, and what an attacker could do with it;
- whether the installation used HTTPS or plain HTTP (`DJANGO_SECURE_COOKIES`).

VHS is a personal project maintained in spare time: reports are handled on a best-effort
basis, with no guaranteed response time. You will get an answer as soon as possible, and
credit in the fix if you wish.

## Supported versions

Only the latest release receives security fixes.

## Scope

- **In scope:** VHS's own code and configuration: the API, authentication and sessions,
  the protected media served by Nginx, the scripts and the Docker setup.
- **Out of scope:** problems in yt-dlp, ffmpeg, Django or other dependencies, which should
  be reported to their projects (a VHS release will update them once fixed), and the
  documented trade-off of plain HTTP on a trusted local network (see
  [installation.md](docs/installation.md#https-or-http-on-a-local-network)).
