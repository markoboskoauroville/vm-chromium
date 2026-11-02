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
- 2.11.2026 (Mac session): Drive only now: vm-agent v10 sends every finished download (subfolders too) to Drive
  "Chromium Downloads/…" and deletes it from the VM; the viewer v3 no longer fetches to the Mac. New agent actions:
  capture (DevTools screenshot into ~/Downloads), cdp (raw DevTools), paste_files (VM files pasted into a page),
  status. Status bar (statusbar/, service chromium-vm-statusbar): bottom, mono, white names / orange values / green
  activity from the left, status right-aligned, 50% see-through band (pseudo-transparency), settings on click.
  Viewer full screen on the 2nd monitor: VM 1512×944 fine after the watcher fix (it had stretched the bar).
  Gemini life story (tools/gemini_life_story.py) on profile "Marko" ([address removed]), refs ~/refs on the VM
  (from markobosko.pages.dev); 06 verified on Drive. Instagram/Facebook are NOT signed in on the VM.
- 2.11.2026 (Mac session): **vm-router v1 + VM Router (Mantra) v1** (router/, README there). Router on 127.0.0.1:8891
  (MANTRA_PORTS `vm-router`), `vmr` on the PATH (symlink to router/vmr.py), Star row `vmrouter` (folder Mac).
  Verified: self-test 8/8 (own background tab, read, refusal of another session's tab and of a tab-less call, /u/N
  added, tab closed); the two live job tabs 09C5…/88C6… refused by id and by url match; browser-wide and Target.* cdp
  refused; navigation to another /u/M refused; capture forced under the session folder and `..` refused; the global
  lock queues (two dry holds of 1.5 s: 1.5 s and 3.0 s); pacing on one account across two sessions (gap 4 s: 0, 4, 4 s
  waited); downloads attributed by folder, also after release; `gemini_state` counts only `<generated-image> img`.
  App: built, signed, installed, opened in the background, screenshots at 860×680 and at its minimum 560×468 (no
  word cut), ② CHECK pressed through AX → PASSED 8/8, OFF through AX quit the app and the router stayed up.
  NOT verified (not allowed while the Gemini jobs ran): type / key / clip_set / clip_get through the lock with a real
  tab activation, `expect_download` with a real Chrome download, the Gemini scripts with `VMR_NAME` set, `--login`.
  No vm-agent change was needed (nothing to deploy). The running Gemini jobs still talk to :8890 directly; their next
  start can go through the router: `VMR_NAME=life-story python3 tools/gemini_life_story.py <tab>` (adopts the tab,
  account /u/0, folder Gemini/life-story; MPA: /u/1, Gemini/MPA-Academy).
  Next: try the focus actions on a router tab when the jobs are done; a finer download owner would need vm-agent to
  listen to Browser.downloadWillBegin (frameId → tab), only if the serialized claim proves too coarse.
