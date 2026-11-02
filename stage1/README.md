# Stage 1: chromium-vm shows Chromium and nothing else

What it builds on the VM (Ubuntu 24.04 Minimal, arm64):

| Piece | File here | Installed as |
|---|---|---|
| Settings (user, Tailscale IP, port, Chromium deb/snap) | `chromium-vm.conf` | `/etc/chromium-vm.conf` |
| Xvnc on **100.102.86.30:5901 only**, VNC password, follows the client's size | `bin/start-xvnc` | `/usr/local/lib/chromium-vm/` |
| The whole "desktop": matchbox (no titlebar/panel) + Chromium, started again when closed | `bin/chromium-vm-session` | `/usr/local/lib/chromium-vm/` |
| systemd: both start at boot, restart on failure; the session restarts with Xvnc | `systemd/*.service` | `/etc/systemd/system/` |
| Chromium policy: restore last session, no default-browser/promo nags | `policies/chromium-vm.json` | `/etc/chromium/policies/managed/` |

## Install (on chromium-vm)

```bash
git clone https://github.com/markoboskoauroville/vm-chromium.git && cd vm-chromium
```

```bash
sudo ./stage1/setup.sh
```

It asks once for the VNC password (stored in `~/.config/chromium-vm/vncpasswd` on the VM, mode 600, never in the
repo). Running it again updates everything and keeps the password and the Chromium profile.

## Chromium: .deb, not the snap (decision)

Ubuntu 24.04's `chromium-browser` package is only a stub that installs the snap. The default here is the
**xtradeb PPA .deb** (real arm64 build, 156.x on 2.11.2026), pinned so apt never swaps it for the snap stub. Why:
the snap starts slower (squashfs mount + confinement setup on every start, which this setup does each time Chromium is
closed), needs workarounds to run from a system service without a login session, and keeps its profile under
`~/snap/`. To confirm with numbers (PLAN.md 1.2), install the snap beside it and time both:

```bash
sudo snap install chromium && ./stage1/measure-chromium-start.sh
```

If the snap turns out faster, `sudo ./stage1/setup.sh --chromium snap` switches (the profile does not move with it).

## The checks (PLAN.md 1.7)

```bash
sudo ./stage1/check.sh --restart-test
```

Services running and enabled for boot, listening only on the Tailscale address, Chromium running, no other window,
and Chromium coming back after it is closed. Then by hand: connect from the Mac (`vnc://100.102.86.30:5901` in
Screen Sharing) and see only Chromium; open tabs, `sudo reboot`, connect again: Chromium is back with the tabs; resize
the window or connect from the phone in portrait: Chromium fills it.

## Notes

- Xvnc follows the client size (`-AcceptSetDesktopSize`); a watcher in the session script resizes Chromium to fill
  each new size. macOS Screen Sharing does not ask for a size change; the own Mac app (Stage 2) will.
- Sound: not in Stage 1 (VNC has no standard audio). Later: PulseAudio/PipeWire over a separate stream.
- Logs: `journalctl -u chromium-vm-xvnc -u chromium-vm-session -f`.
- Oracle's public ports are untouched (22 only); 5901 exists only on the tailnet.
