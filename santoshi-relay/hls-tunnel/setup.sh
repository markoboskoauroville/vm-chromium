#!/bin/bash
# santoshi-relay/hls-tunnel/setup.sh: live.santoshiband.org, the cached HLS door of the Santoshi relay (15.11.2026).
#   1. sudo santoshi-relay/hls-tunnel/setup.sh install   cloudflared from Cloudflare's apt repo + the user cloudflared
#   2. santoshi-relay/hls-tunnel/setup.sh login          (as ubuntu) prints the authorization URL; Marko clicks santoshiband.org → Authorize;
#                                                        ~/.cloudflared/cert.pem (600) appears. The only hand step.
#   3. sudo -E santoshi-relay/hls-tunnel/setup.sh tunnel  creates the tunnel, its DNS CNAME, /etc/cloudflared, the unit, starts it
#   4. (optional) python3 …/cache_rule.py: a Cache Rule; not needed, the proxy makes the URLs cacheable by default (needs a token with Cache Rules)
# No token or certificate is ever printed. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"
NAME=santoshi-hls HOST=live.santoshiband.org
CERT=/home/ubuntu/.cloudflared/cert.pem
case "${1:-}" in
install)
  [ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
  if ! command -v cloudflared >/dev/null; then
    install -d -m 755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq && apt-get install -y -qq cloudflared
  fi
  id cloudflared >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin cloudflared
  cloudflared --version ;;
login)
  [ -s "$CERT" ] && { echo "cert.pem is already there"; exit 0; }
  cloudflared tunnel login 2>&1 | grep --line-buffered -oE 'https://dash\.cloudflare\.com/argotunnel\?[^ ]+|You have successfully logged in.*|error.*' || true
  chmod 600 "$CERT" ;;
tunnel)
  [ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
  export TUNNEL_ORIGIN_CERT=$CERT
  ID=$(cloudflared tunnel list -o json 2>/dev/null | python3 -c "import sys,json;print(next((t['id'] for t in json.load(sys.stdin) if t['name']=='$NAME'),''))")
  install -d -m 750 -o root -g cloudflared /etc/cloudflared
  if [ -z "$ID" ]; then cloudflared tunnel create --credentials-file /etc/cloudflared/$NAME.json $NAME >/dev/null; ID=$(cloudflared tunnel list -o json | python3 -c "import sys,json;print(next(t['id'] for t in json.load(sys.stdin) if t['name']=='$NAME'))"); fi
  [ -s /etc/cloudflared/$NAME.json ] || { echo "credentials missing for $ID (made elsewhere?)" >&2; exit 1; }
  chown root:cloudflared /etc/cloudflared/$NAME.json; chmod 640 /etc/cloudflared/$NAME.json
  sed "s/TUNNEL_ID/$ID/" santoshi-hls.yml > /etc/cloudflared/$NAME.yml; chown root:cloudflared /etc/cloudflared/$NAME.yml; chmod 640 /etc/cloudflared/$NAME.yml
  cloudflared tunnel --config /etc/cloudflared/$NAME.yml ingress validate
  cloudflared tunnel route dns --overwrite-dns $NAME $HOST
  install -d -m 755 /opt/santoshi-hls; install -m 644 hls_cache_proxy.py /opt/santoshi-hls/
  install -m 644 santoshi-hls-proxy.service santoshi-hls-tunnel.service /etc/systemd/system/
  systemctl daemon-reload; systemctl enable --now santoshi-hls-proxy; systemctl restart santoshi-hls-proxy
  systemctl enable --now santoshi-hls-tunnel; systemctl restart santoshi-hls-tunnel; sleep 3; systemctl is-active santoshi-hls-tunnel
  echo "tunnel $NAME ($ID) → $HOST" ;;
*) sed -n 2,8p "$0"; exit 1 ;;
esac
