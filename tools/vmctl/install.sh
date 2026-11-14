#!/bin/bash
# tools/vmctl/install.sh: chromium-vm boots with the core only; every other program is a vmctl service (Marko, 14.11.2026).
# Run on the VM from the repo checkout: sudo tools/vmctl/install.sh
# It installs vmctl (CLI + API), the registry, the priority slices (Connection Keeper first), the Chrome service split from
# the session, the Firefox/Brave user units, and switches every optional unit OFF AT BOOT (disable only: nothing is
# stopped, deleted or recreated; containers keep their data). Stops happen at the next reboot. Safe to run again.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/../.."
. /etc/chromium-vm.conf
U=${VM_USER:-ubuntu}; UH=$(getent passwd "$U" | cut -d: -f6); UID_=$(id -u "$U")
L=/usr/local/lib/chromium-vm
as_user() { sudo -u "$U" XDG_RUNTIME_DIR=/run/user/$UID_ DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UID_/bus "$@"; }

echo "== vmctl and the registry"
install -m 755 tools/vmctl/vmctl.py $L/vmctl
install -m 644 tools/vmctl/vmctl_client.py $L/vmctl_client.py
ln -sf $L/vmctl /usr/local/bin/vmctl
install -d -m 755 /etc/chromium-vm
install -m 644 tools/vmctl/services.json /etc/chromium-vm/services.json
as_user python3 -c "import importlib.machinery as m; v=m.SourceFileLoader('v','$L/vmctl').load_module(); v.token()"
sed "s/@VM_USER@/$U/" tools/vmctl/systemd/system/chromium-vm-vmctl.service > /etc/systemd/system/chromium-vm-vmctl.service

echo "== desktop pieces that call vmctl"
install -m 755 stage1/bin/chromium-vm-session stage1/bin/chromium-vm-chrome $L/
install -m 755 desktop/chromium-vm-phone desktop/chromium-vm-snap desktop/vm-whatsapp desktop/vm-open-url $L/
install -m 755 statusbar/chromium-vm-statusbar.py $L/
sed "s/@VM_USER@/$U/" stage1/systemd/chromium-vm-chrome.service > /etc/systemd/system/chromium-vm-chrome.service

echo "== priority: vm-core.slice (ckbond, tailscaled) over vm-services.slice (everything optional)"
install -m 644 tools/vmctl/systemd/system/vm-core.slice tools/vmctl/systemd/system/vm-services.slice /etc/systemd/system/
for d in ckbond.service.d tailscaled.service.d; do
  install -d /etc/systemd/system/$d; install -m 644 tools/vmctl/systemd/dropins/$d/10-priority.conf /etc/systemd/system/$d/
done
# Optional system units (from the registry, plus helpers that belong to them)
OPT_SYS=$(python3 -c "
import json; r=json.load(open('/etc/chromium-vm/services.json'))['services']
print(' '.join(u for s in r if not s.get('core') and s['kind']=='systemd' for u in s['units'] if u.endswith('.service')))")
OPT_SYS="$OPT_SYS chromium-vm-reaper.service chromium-vm-pixel7.service chromium-vm-pixel7b.service chromium-vm-pixel7-bar.service"
for u in $OPT_SYS; do
  [ "$u" = chromium-vm-chrome.service ] && continue      # has Slice= in its own unit
  install -d /etc/systemd/system/$u.d; install -m 644 tools/vmctl/systemd/dropins/optional/50-vm-services.conf /etc/systemd/system/$u.d/
done
# Docker's containers in the low slice too (takes effect when docker next starts; never recreates a container)
if [ ! -f /etc/docker/daemon.json ]; then install -d /etc/docker; echo '{"cgroup-parent": "vm-services.slice"}' > /etc/docker/daemon.json; fi

echo "== user units (Firefox, Brave, the user slice)"
UD=$UH/.config/systemd/user
as_user install -d "$UD"
as_user install -m 644 tools/vmctl/systemd/user/vm-firefox.service tools/vmctl/systemd/user/vm-brave.service tools/vmctl/systemd/user/vm-services.slice "$UD/"
OPT_USR=$(python3 -c "
import json; r=json.load(open('/etc/chromium-vm/services.json'))['services']
print(' '.join(u for s in r if not s.get('core') and s['kind']=='user' for u in s['units'] if u.endswith('.service') and not u.startswith('vm-')))")
OPT_USR="$OPT_USR yt-upload.service two-locations-sync.service"
for u in $OPT_USR; do
  as_user install -d "$UD/$u.d"; as_user install -m 644 tools/vmctl/systemd/dropins/user-optional/50-vm-services.conf "$UD/$u.d/"
done

systemctl daemon-reload
as_user systemctl --user daemon-reload

echo "== the core stays enabled"
systemctl enable ckbond.service tailscaled.service ssh.socket chromium-vm-xvnc.service chromium-vm-session.service \
  chromium-vm-statusbar.service chromium-vm-agent.service chromium-vm-vmctl.service
as_user systemctl --user enable queen.service pulseaudio.socket

echo "== everything else OFF AT BOOT (disable only, nothing stopped now)"
systemctl disable chromium-vm-claude-app.service chromium-vm-claude-code.service chromium-vm-dock.service chromium-vm-refit.service \
  chromium-vm-reaper-evaluating.service chromium-vm-aooserver.service chromium-vm-reaper.timer chromium-vm-worker-gemini.service \
  chromium-vm-pixel7.service chromium-vm-pixel7b.service chromium-vm-pixel7-bar.service chromium-vm-chrome.service \
  pixel7d.service pixel7-jobs.service docker.service docker.socket containerd.service 2>&1 | grep -v '^Removed' || true
as_user systemctl --user disable mantra-macro.service wa-door.service yt-monitor.service yt-transcribe.service \
  yt-upload.timer two-locations-sync.timer 2>&1 | grep -v '^Removed' || true
if systemctl is-active --quiet docker.service; then
  for c in pixel7 pixel7b; do docker update --restart no --cpu-shares 128 "$c" >/dev/null && echo "container $c: restart no, cpu-shares 128"; done
fi

echo "== the API now"
systemctl restart chromium-vm-vmctl.service
sleep 2; systemctl is-active chromium-vm-vmctl.service
echo "enabled at boot:"; systemctl list-unit-files --state=enabled --no-pager | grep -E 'chromium-vm|ckbond|tailscale|ssh|docker|containerd|pixel7' || true
as_user systemctl --user list-unit-files --state=enabled --no-pager | grep -vE '^$|unit files' || true
