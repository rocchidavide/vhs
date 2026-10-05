#!/bin/sh
# Entrypoint of the production backend image (docker/Dockerfile.backend).
#
# Emergency option VHS_YTDLP_AUTO_UPDATE (docs/installation.md, "Troubleshooting"): when it
# is on, the backend and the worker install the latest yt-dlp at every start, into a folder
# of the container that takes precedence over the image's version. That version is not
# tested with VHS; by default VHS uses the yt-dlp of its release. If the installation fails
# (no network, for example), VHS starts with the image's version.
set -e

case "$*" in
  *uvicorn* | *qcluster*) ;;
  *) exec "$@" ;; # migrate and one-off commands do not download videos
esac

case "$(printf '%s' "${VHS_YTDLP_AUTO_UPDATE:-}" | tr '[:upper:]' '[:lower:]')" in
  1 | true | yes | on)
    target=/tmp/vhs-ytdlp
    if UV_HTTP_TIMEOUT=20 uv pip install --quiet --python /opt/venv/bin/python \
        --target "$target" --upgrade "yt-dlp[default]"; then
      export PYTHONPATH="$target${PYTHONPATH:+:$PYTHONPATH}"
      version=$(python -c 'from yt_dlp.version import __version__; print(__version__)')
      echo "vhs: VHS_YTDLP_AUTO_UPDATE is on: using yt-dlp $version (not tested with this release)"
    else
      echo "vhs: VHS_YTDLP_AUTO_UPDATE is on, but the latest yt-dlp could not be installed: using the image's version" >&2
    fi
    ;;
esac

exec "$@"
