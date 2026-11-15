#!/bin/bash
# studio-stream/install.sh (run from the repo root on chromium-vm: sudo studio-stream/install.sh)
# Installs the Studio route's VM half: studio-ladder (RTMP in on the Tailscale address :1935 -> HLS ladder in /dev/shm)
# and studio-web (https :2053). Never touches MediaMTX (santoshi-relay) or its running stream.
# The Oracle security list needs tcp 2053 ingress (added once by oci CLI from the Mac, see README).
set -eu
cd "$(dirname "$0")/.."
L=/usr/local/lib/chromium-vm
id studio >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin studio
install -m 755 studio-stream/studio-ladder $L/studio-ladder
install -m 755 studio-stream/studio-web $L/studio-web
install -m 755 studio-stream/certbot-deploy-hook /etc/letsencrypt/renewal-hooks/deploy/studio-stream
/etc/letsencrypt/renewal-hooks/deploy/studio-stream || true
iptables -C INPUT -p tcp --dport 2053 -j ACCEPT 2>/dev/null || iptables -I INPUT 2 -p tcp --dport 2053 -j ACCEPT
command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null 2>&1 || true
install -m 644 studio-stream/systemd/studio-ladder.service studio-stream/systemd/studio-web.service /etc/systemd/system/
[ -f tools/vmctl/services.json ] && install -m 644 tools/vmctl/services.json /etc/chromium-vm/services.json
systemctl daemon-reload
systemctl enable studio-ladder.service studio-web.service
systemctl restart studio-ladder.service studio-web.service
sleep 1; systemctl is-active studio-ladder.service studio-web.service
curl -s -o /dev/null -w "studio-web health: HTTP %{http_code}\n" https://relay.ples-duse.org:2053/studio/health || true
