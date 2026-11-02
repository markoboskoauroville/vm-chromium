#!/bin/bash
# Installs vm-agent on chromium-vm (run with sudo after stage1/setup.sh). Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"
VM_USER=${SUDO_USER:-ubuntu}; VM_HOME=$(getent passwd "$VM_USER" | cut -d: -f6)
apt-get install -y -q --no-install-recommends python3-websocket xclip xdotool x11-apps imagemagick >/dev/null
grep -q '^AGENT_PORT=' /etc/chromium-vm.conf || echo 'AGENT_PORT=8890' >> /etc/chromium-vm.conf
install -m 755 vm-agent.py /usr/local/lib/chromium-vm/vm-agent.py
TOK="$VM_HOME/.config/chromium-vm/agent-token"
if [ ! -s "$TOK" ]; then ( umask 077; head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40 > "$TOK" ); fi
chown "$VM_USER:$VM_USER" "$TOK"; chmod 600 "$TOK"
sed "s/@VM_USER@/$VM_USER/" chromium-vm-agent.service > /etc/systemd/system/chromium-vm-agent.service
systemctl daemon-reload; systemctl enable --now chromium-vm-agent.service; systemctl restart chromium-vm-agent.service
echo "vm-agent on $(. /etc/chromium-vm.conf; echo $VNC_IP):8890"
