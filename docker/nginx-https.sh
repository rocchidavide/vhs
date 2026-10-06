#!/bin/sh
# Turns HTTPS on in VHS's Nginx when VHS_HTTPS is true (docs/installation.md). The entrypoint
# of the nginx image runs it before starting Nginx (/docker-entrypoint.d); a failure stops the
# container with this message instead of an Nginx error.
set -eu

case "$(printf '%s' "${VHS_HTTPS:-false}" | tr '[:upper:]' '[:lower:]')" in
  1 | true | yes | on) ;;
  *)
    rm -f /etc/nginx/vhs/https.conf
    exit 0
    ;;
esac

for file in fullchain.pem privkey.pem; do
  if [ ! -r "/etc/nginx/certs/$file" ]; then
    echo "vhs: VHS_HTTPS is true, but certs/$file is missing: put the certificate (fullchain.pem) and its key (privkey.pem) in the certs folder of VHS" >&2
    exit 1
  fi
done
cp /etc/nginx/vhs-https.conf /etc/nginx/vhs/https.conf
echo "vhs: HTTPS on"
