#!/bin/bash
# Installs openbox (Rectangle keys), the four screens + the dock on chromium-vm (run with sudo after stage1/setup.sh and agent/install.sh).
# Safe to run again. Screen 1: Claude Code (xfce4-terminal + tmux), screen 2: Claude Desktop (official, Anthropic's
# apt repo), screen 3: the session's Chrome, screen 4: the Pixel 7 (scrcpy onto vm-android's pixel7 container, 5.11.2026). The dock binds Super+Tab (= Command-Tab from the Mac viewer).
set -euo pipefail
cd "$(dirname "$0")"
VM_USER=${SUDO_USER:-ubuntu}; VM_HOME=$(getent passwd "$VM_USER" | cut -d: -f6)
apt-get install -y -q --no-install-recommends openbox wmctrl xfce4-terminal tmux fonts-jetbrains-mono gir1.2-keybinder-3.0 libsecret-tools xdg-utils \
  python3-xlib python3-gi gir1.2-gtk-3.0 xdotool xclip x11-utils gnome-keyring scrcpy curl gnupg >/dev/null
# Claude Desktop for Linux (beta): Anthropic's apt repository, key fingerprint 31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE.
KEY=/usr/share/keyrings/claude-desktop-archive-keyring.asc
[ -s "$KEY" ] || curl -fsSLo "$KEY" https://downloads.claude.ai/claude-desktop/key.asc
gpg --show-keys "$KEY" 2>/dev/null | grep -q 31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE || { echo "wrong Claude Desktop key" >&2; exit 1; }
echo "deb [arch=amd64,arm64 signed-by=$KEY] https://downloads.claude.ai/claude-desktop/apt/stable stable main" \
  > /etc/apt/sources.list.d/claude-desktop.list
dpkg -s claude-desktop >/dev/null 2>&1 || { apt-get update -q >/dev/null; apt-get install -y -q --no-install-recommends claude-desktop >/dev/null; }

install -m 755 chromium-vm-claude-code chromium-vm-claude-app chromium-vm-pixel7 chromium-vm-snap /usr/local/lib/chromium-vm/
install -m 644 config/openbox-rc.xml /usr/local/lib/chromium-vm/openbox-rc.xml
install -m 755 chromium-vm-dock.py /usr/local/lib/chromium-vm/chromium-vm-dock.py
install -m 644 config/matchbox-kbdconfig /usr/local/lib/chromium-vm/matchbox-kbdconfig
as_user() { sudo -u "$VM_USER" "$@"; }
as_user mkdir -p "$VM_HOME/.config/xfce4/terminal" "$VM_HOME/.cache/chromium-vm"
as_user install -m 644 config/terminalrc "$VM_HOME/.config/xfce4/terminal/terminalrc"
as_user install -m 644 config/tmux.conf "$VM_HOME/.tmux.conf"
# The first version padded the terminal above the status bar with gtk.css; openbox's margin does that now.
grep -qs 'chromium-vm: the terminal keeps' "$VM_HOME/.config/gtk-3.0/gtk.css" && rm -f "$VM_HOME/.config/gtk-3.0/gtk.css"
# Links opened by other programs (Claude Desktop's sign-in, Claude Code's login) go to the session's Chrome, where
# Marko is signed in, not to the old plain Chromium (2.11.2026).
as_user mkdir -p "$VM_HOME/.local/share/applications"
sed "s#@VM_HOME@#$VM_HOME#" config/chromium-vm-chrome.desktop > "$VM_HOME/.local/share/applications/chromium-vm-chrome.desktop"
chown "$VM_USER:$VM_USER" "$VM_HOME/.local/share/applications/chromium-vm-chrome.desktop"
as_user env HOME="$VM_HOME" xdg-settings set default-web-browser chromium-vm-chrome.desktop || true
grep -q 'local/bin' "$VM_HOME/.bashrc" || echo 'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac' >> "$VM_HOME/.bashrc"

for u in chromium-vm-claude-code chromium-vm-claude-app chromium-vm-pixel7 chromium-vm-dock; do
  sed "s/@VM_USER@/$VM_USER/" "systemd/$u.service" > "/etc/systemd/system/$u.service"
done
systemctl daemon-reload
systemctl enable chromium-vm-claude-code chromium-vm-claude-app chromium-vm-pixel7 chromium-vm-dock >/dev/null 2>&1
systemctl restart chromium-vm-claude-code chromium-vm-claude-app chromium-vm-pixel7 chromium-vm-dock
echo "four screens + dock installed; openbox (and its keys) starts with the next chromium-vm-session start"
