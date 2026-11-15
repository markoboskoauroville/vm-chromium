#!/bin/bash
# santoshi-relay/apply-config.sh: render mediamtx.yml.in into /etc/mediamtx/mediamtx.yml (MediaMTX reloads it in place) without
# reinstalling anything else. 15.11.2026 "mixer only": also makes the mixer's own publish key (/etc/santoshi-relay/mixer-key,
# root:ubuntu 640, never printed) and its hash (/etc/mediamtx/mixer.hash). Run on the VM from the repo checkout, ONLY when nothing is
# on air (check: curl -s 127.0.0.1:8841/status; systemctl is-active cloud-mixer-show; the site's /api/live):
#   sudo santoshi-relay/apply-config.sh            (shows the changed lines with hashes masked, asks nothing, keeps a backup)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/.."
H=$(cat /etc/mediamtx/publish.hash)
if [ ! -s /etc/santoshi-relay/mixer-key ]; then
  ( umask 027; head -c 24 /dev/urandom | base64 | tr -d '/+=' > /etc/santoshi-relay/mixer-key )
  chown root:ubuntu /etc/santoshi-relay/mixer-key; chmod 640 /etc/santoshi-relay/mixer-key
  echo "made /etc/santoshi-relay/mixer-key"
fi
MH="sha256:$(tr -d '\n' < /etc/santoshi-relay/mixer-key | openssl dgst -binary -sha256 | base64)"
printf '%s\n' "$MH" > /etc/mediamtx/mixer.hash; chgrp mediamtx /etc/mediamtx/mixer.hash; chmod 640 /etc/mediamtx/mixer.hash
T=$(mktemp); trap 'rm -f "$T"' EXIT
sed -e "s|@PUBLISH_HASH@|$H|" -e "s|@MIXER_HASH@|$MH|" santoshi-relay/mediamtx.yml.in > "$T"
python3 -c 'import sys,yaml; yaml.safe_load(open(sys.argv[1]))' "$T"
diff <(sed -E 's/sha256:[A-Za-z0-9+\/=]+/sha256:<hash>/' /etc/mediamtx/mediamtx.yml) <(sed -E 's/sha256:[A-Za-z0-9+\/=]+/sha256:<hash>/' "$T") || true
B=/etc/mediamtx/mediamtx.yml.$(date -u +%Y%m%d-%H%M%S)
cp -p /etc/mediamtx/mediamtx.yml "$B"
install -m 640 -o root -g mediamtx "$T" /etc/mediamtx/mediamtx.yml
echo "installed; backup $B (MediaMTX reloads the file by itself; journalctl -u santoshi-relay -n 20)"
