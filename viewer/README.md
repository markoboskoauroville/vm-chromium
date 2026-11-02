# Chromium Virtual Machine (Mantra)

The Mac's window onto chromium-vm (Oracle Cloud, Tailscale 100.102.86.30). Swift, no Xcode: `./build.sh` builds,
signs "Mantra Apps", installs in /Applications and quits the running copy. Star: folder Mac, row `chromiumvm`.

- **Screen:** own RFB 3.8 client (VncAuth, ZRLE / CopyRect / Raw). The VM follows the window size
  (ExtendedDesktopSize). FULL SCREEN or ⌃⌘F hides the top row.
- **Keys:** ⌘ is Ctrl on the VM (⌘C ⌘V ⌘T ⌘W ⌘L), ⌥ composes characters the Mac way, ⌘Q / ⌘H / ⌃⌘F stay the Mac's.
  v5 (2.11.2026): **⌘Tab arrives as Super_L+Tab** (keysym 0xffeb + Tab; Ctrl let go around it), the VM's only
  screen-switching key; **⌃⌥ + any key arrives as Ctrl+Alt+key** (Rectangle's keys on the VM's openbox). While the
  viewer is the active app the Mac's global hotkeys are suspended (CGSSetGlobalHotKeyOperatingMode), so macOS's ⌘Tab
  and the Mac's own Rectangle do not take these keys; they come back as soon as another app is in front.
- **Clipboard both ways, UTF-8:** Mac → VM when the window becomes active and before ⌘V; VM → Mac when the VM's
  clipboard changes (Xvnc's ServerCutText only signals; the text comes from vm-agent). Replaces `vmpaste`/`vmcopy`.
- **Drag and drop:** Mac files dropped on the window go to ~/Downloads on the VM (vm-agent PUT), progress in the top row.
- **Remote door:** 127.0.0.1:8962 (MANTRA_PORTS `chromium-vm`): `/health`, `/api`, `POST /api/status|show|fullscreen|
  reconnect|send_file|push_clipboard`.
- **Keys it reads:** ~/Downloads/API/chromium-vm-vnc.txt (VNC password) and chromium-vm-agent.txt (agent token).
