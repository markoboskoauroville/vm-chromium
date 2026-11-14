#!/bin/bash
# ttt-relay/install.sh: TTT's transcription relay on chromium-vm (Marko, 14.11.2026). Run on the VM from the repo checkout:
#   sudo ttt-relay/install.sh
# Installs the relay, its own system user (the keys file is readable by nobody else), the unit, and enables it at boot:
# TTT's dictation must always find Frankfurt (registry: core, ~20 MB idle, in vmsvc.slice below ckbond). Safe to run again.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/.."
. /etc/chromium-vm.conf 2>/dev/null || true
OWNER=$(tailscale status --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['User'][str(d['Self']['UserID'])]['LoginName'])")
id ttt-relay >/dev/null 2>&1 || useradd --system --home /var/lib/ttt-relay --shell /usr/sbin/nologin ttt-relay
install -d -m 700 -o ttt-relay -g ttt-relay /var/lib/ttt-relay
install -m 755 ttt-relay/ttt_relay.py /usr/local/lib/chromium-vm/ttt_relay.py
[ -f /etc/ttt-relay.conf ] || printf '# who may call the relay: the Tailscale user of the phones\nOWNER=%s\n' "$OWNER" > /etc/ttt-relay.conf
chmod 644 /etc/ttt-relay.conf
install -m 644 ttt-relay/systemd/ttt-relay.service /etc/systemd/system/ttt-relay.service
# The registry entry (vmctl list / the gear / the status bar).
install -m 644 tools/vmctl/services.json /etc/chromium-vm/services.json
systemctl daemon-reload
systemctl enable ttt-relay.service
systemctl restart ttt-relay.service
sleep 1.5
IP=$(tailscale ip -4)
curl -fsS "http://$IP:8897/health" && echo && echo "ttt-relay: active on $IP:8897, owner $(grep OWNER= /etc/ttt-relay.conf | cut -d= -f2 | sed 's/@.*/@…/')"
