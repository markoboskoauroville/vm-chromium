# TAKEOVER

- 2.11.2026: the repository and the plan only; nothing installed on the VM yet (fresh Ubuntu 24.04 Minimal).
- 2.11.2026: Stage 1 files written by the cloud session (`stage1/`: setup.sh, session + Xvnc scripts, systemd units,
  policy, check.sh, measure-chromium-start.sh). Not yet run on the VM: this session has no tailnet access. Next: run
  `sudo ./stage1/setup.sh` on chromium-vm and `sudo ./stage1/check.sh --restart-test`.
- 2.11.2026 (Mac session): Stage 1 installed and verified on chromium-vm: Chromium 156.0.8078.73 (xtradeb deb),
  Xvnc on 100.102.86.30:5901 only, check.sh 7/7 incl. close-and-return, and 6/6 after a reboot. VNC password made
  on the VM, copy in ~/Downloads/API/chromium-vm-vnc.txt (never in the repo). Not yet: hand check with Mac Screen
  Sharing / phone, snap vs deb timing (measure-chromium-start.sh), Stage 2.
- 2.11.2026 (Mac session): switched to Google Chrome 156.0.8078.79 arm64 for profile sign-in and Sync (Marko's
  choice); check.sh 6/6, sandbox on. Mac Screen Sharing works (no shared clipboard with a Linux VNC server: the
  viewer's feature request in PLAN.md; `vmpaste` / `vmcopy` on the Mac meanwhile). Old Chromium profile kept in
  ~/.config/chromium on the VM.
- 2.11.2026 (Mac session): **vm-agent v4 + cvm** live. Verified: tabs, clipboard both ways, file put/get, page text,
  `cvm ask` round trip in a fresh claude.ai chat (6.8 s, "received"). Chrome profile moved to
  ~/.config/chromium-vm-chrome (DevTools needs a non-default folder); ~/.config/google-chrome and ~/.config/chromium
  are the old copies. Next: the Swift viewer (2b) using the same agent (clipboard, drag and drop), then Stage 3.
  The Claude *extension* (side panel) is not driven yet; only claude.ai tabs.
- 2.11.2026 (Mac session): **Chromium Virtual Machine (Mantra) v1** built (viewer/), in /Applications and the Star
  (folder Mac). Verified by me: connects, picture right, VM resizes to the window (1280×798), clipboard both ways with
  Č ć ž š đ, a file through the door's send_file (same path as a drop) landed in the VM's Downloads, door answers.
  Not yet verified: Marko's hand on keys, mouse, scroll, a real drag from Finder.
- 2.11.2026 (Mac session): **Chromium Downloads** working: vm-agent v6 journals every finished Chrome download;
  the viewer v2 fetches them into ~/Downloads/Chromium Downloads (while it runs; catches up on open); the VM
  copies each to Google Drive "Chromium Downloads" (rclone remote `gdrive`, scope drive.file, account
  [address removed], Marko allowed it). Verified with two real downloads: Mac + Drive both.
