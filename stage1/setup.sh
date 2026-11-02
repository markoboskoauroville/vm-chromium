#!/bin/bash
# Stage 1 on chromium-vm: Xvnc on the Tailscale address + Chromium and nothing else, kept running by systemd.
# Run on the VM from a clone of this repository:   sudo ./stage1/setup.sh [--chromium chrome|deb|snap]
# Safe to run again (it updates files and restarts the services).
set -euo pipefail
cd "$(dirname "$0")"

SOURCE=chrome
VM_USER=${SUDO_USER:-ubuntu}
VNC_IP=100.102.86.30
while [ $# -gt 0 ]; do
  case "$1" in
    --chromium) SOURCE=$2; shift 2 ;;
    --user)     VM_USER=$2; shift 2 ;;
    --ip)       VNC_IP=$2; shift 2 ;;
    *) echo "usage: sudo $0 [--chromium chrome|deb|snap] [--user NAME] [--ip ADDR]" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
[ "$VM_USER" != root ] || { echo "--user must be the login user (e.g. ubuntu), not root" >&2; exit 1; }
case "$SOURCE" in chrome|deb|snap) ;; *) echo "--chromium chrome, deb or snap" >&2; exit 2 ;; esac
VM_UID=$(id -u "$VM_USER"); VM_HOME=$(getent passwd "$VM_USER" | cut -d: -f6)

echo "1. Packages: TigerVNC, matchbox, X tools, fonts"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  tigervnc-standalone-server tigervnc-tools matchbox-window-manager \
  x11-utils x11-xserver-utils xdotool dbus-user-session \
  fonts-noto-core fonts-noto-color-emoji fonts-dejavu-core fontconfig bc \
  ca-certificates software-properties-common gpg-agent

echo "2. Chromium ($SOURCE)"
if [ "$SOURCE" = chrome ]; then
  # Google Chrome: plain Chromium builds cannot sign into a browser profile or Sync (Google, March 2021).
  install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor --yes -o /etc/apt/keyrings/google-chrome.gpg
  echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -q
  apt-get install -y -q google-chrome-stable
  POLICY_DIRS=(/etc/opt/chrome/policies/managed)
  # Ubuntu ships /etc/apparmor.d/chrome (userns for /opt/google/chrome/chrome): make sure it is loaded.
  [ -f /etc/apparmor.d/chrome ] && apparmor_parser -r /etc/apparmor.d/chrome
  # First switch from Chromium: carry the profile (tabs, cookies, Google sign-in) over once.
  if [ -d "$VM_HOME/.config/chromium" ] && [ ! -d "$VM_HOME/.config/google-chrome" ]; then
    systemctl stop chromium-vm-session.service 2>/dev/null || true
    sleep 2
    cp -a "$VM_HOME/.config/chromium" "$VM_HOME/.config/google-chrome"
    rm -f "$VM_HOME/.config/google-chrome"/Singleton{Lock,Socket,Cookie}
  fi
elif [ "$SOURCE" = deb ]; then
  add-apt-repository -y ppa:xtradeb/apps
  # Take chromium* only from xtradeb; Ubuntu's chromium-browser is just a stub that installs the snap.
  cat > /etc/apt/preferences.d/chromium-vm-xtradeb <<'PIN'
Package: chromium*
Pin: release o=LP-PPA-xtradeb-apps
Pin-Priority: 1001

Package: *
Pin: release o=LP-PPA-xtradeb-apps
Pin-Priority: 100
PIN
  apt-get update -q
  apt-get install -y -q chromium
  POLICY_DIRS=(/etc/chromium/policies/managed)
else
  command -v snap >/dev/null || apt-get install -y -q snapd
  snap install chromium
  POLICY_DIRS=(/etc/chromium-browser/policies/managed)
fi
if [ "$SOURCE" = deb ]; then
  # Ubuntu 24.04's AppArmor blocks Chromium's sandbox (user namespaces) unless the binary has a profile.
  install -m 644 apparmor/chromium-vm /etc/apparmor.d/chromium-vm
  apparmor_parser -r /etc/apparmor.d/chromium-vm
fi
for d in "${POLICY_DIRS[@]}"; do install -D -m 644 policies/chromium-vm.json "$d/chromium-vm.json"; done

echo "3. Settings and scripts"
if [ -f /etc/chromium-vm.conf ]; then
  sed -i "s/^CHROMIUM_SOURCE=.*/CHROMIUM_SOURCE=$SOURCE/; s/^VM_USER=.*/VM_USER=$VM_USER/; s/^VNC_IP=.*/VNC_IP=$VNC_IP/" /etc/chromium-vm.conf
else
  sed "s/^CHROMIUM_SOURCE=.*/CHROMIUM_SOURCE=$SOURCE/; s/^VM_USER=.*/VM_USER=$VM_USER/; s/^VNC_IP=.*/VNC_IP=$VNC_IP/" chromium-vm.conf > /etc/chromium-vm.conf
fi
install -d /usr/local/lib/chromium-vm
install -m 755 bin/start-xvnc bin/chromium-vm-session /usr/local/lib/chromium-vm/
for u in chromium-vm-xvnc chromium-vm-session; do
  sed "s/@VM_USER@/$VM_USER/; s/@VM_UID@/$VM_UID/" "systemd/$u.service" > "/etc/systemd/system/$u.service"
done
# Linger: the user's runtime dir and D-Bus exist from boot, with no login.
loginctl enable-linger "$VM_USER"

echo "4. VNC password (kept on the VM only)"
PASSWD="$VM_HOME/.config/chromium-vm/vncpasswd"
install -d -o "$VM_USER" -g "$VM_USER" -m 700 "$VM_HOME/.config/chromium-vm"
if [ ! -s "$PASSWD" ]; then
  echo "   Type the VNC password (8 characters are used; no view-only password):"
  sudo -u "$VM_USER" vncpasswd "$PASSWD" </dev/tty
fi
chown "$VM_USER:$VM_USER" "$PASSWD"; chmod 600 "$PASSWD"

echo "5. Start"
systemctl daemon-reload
systemctl enable chromium-vm-xvnc.service chromium-vm-session.service
systemctl restart chromium-vm-xvnc.service
systemctl restart chromium-vm-session.service
sleep 5
systemctl --no-pager --lines=0 status chromium-vm-xvnc chromium-vm-session || true
echo "Done. Connect a VNC client to $VNC_IP:5901 (over Tailscale). Checks: sudo ./stage1/check.sh"
