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
- 2.11.2026 (Mac session): **workers/** started. First: **gemini-images** (service chromium-vm-worker-gemini on the
  VM): the batch on Drive (Chromium Downloads/Gemini/_batch/batch.json, 270 items = 54 scenes + 4 variations; refs/
  = 14 face photos from his Instagram), one tab of the profile signed in as [address removed], two random refs,
  1:1 DevTools capture, human pace 60–150 s, stops at "Your limit resets at …", sleeps until then + 5 min,
  RESULTS.txt in Gemini/life-story on Drive. Measured: ~37 images per limit window on a free account.
- **Closed 2.11.2026 ~17:00 CT (Mac session "chromium vm machine at oracle cloud").** Running by itself on the VM:
  Chrome + Xvnc + session, vm-agent v10 (:8890), status bar, worker chromium-vm-worker-gemini (233 images to make,
  first one made alone 16:15 CT). Open: Chrome restart to load AutoplayAllowed=false (policy file is in place);
  Instagram tribal.jam.collective needs its own login; the Mantra Remote v21 connection test on the real Pixel 7
  (installed, password saved; ENTER not yet pressed); the Mac viewer's keys/mouse/drag never hand-tested by Marko.
  Next session: read Drive "Chromium Downloads/Gemini/life-story/RESULTS.txt" first.
- 2.11.2026 ~18:15 CT (MPA-ACADEMY session), Marko: "reset the Chrome, stop all the actions, or pause all the actions ...
  Then return actions after we finish". PAUSED: chromium-vm-worker-gemini.service stopped (sudo systemctl stop); Chrome
  restarted (chromium-vm-session.service); the Mac jobs stopped: the 18:34 chain (3 cover attempts gemini_mpa_cover.py, then
  gemini_mpa_drums.py SKIP=… MADE_BEFORE=13 TARGET=55 on tab auroville.community /u/1), life story finished its day (55 real,
  gmail limit until 20:35 CT). TO RESUME: `sudo systemctl start chromium-vm-worker-gemini.service`; reopen Gemini tabs; rerun the
  cover script, then the drums with the SKIP list (see tools/gemini_mpa_drums.log).
- 2.11.2026 ~19:30 CT (Mac session, subagent of "chromium vm"): **the desktop**: openbox instead of matchbox, three
  programs and the dock (desktop/, README "The desktop"). Claude Code in xfce4-terminal + tmux `claude`; **Claude =
  the official Claude Desktop for Linux beta** (Anthropic's apt repo, claude-desktop 4.4212.0 arm64, key fingerprint
  31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE; no community repackage); Chrome unchanged. Dock: three live screens +
  three layout displays (Halves, Thirds, Chrome + 2). Keys: **⌘Tab arrives as Super_L+Tab** (keysym 0xffeb) — only
  since viewer v5; before, ⌘ was always sent as Control_L and macOS ate ⌘Tab, so it never reached the VM. ⌃ arrives
  as Control_L, ⌥ as Alt_L only with arrows/Return/Backspace … and, since v5, with every key while ⌃ is held, so the
  Rectangle set (Ctrl+Alt+…) works. The viewer suspends the Mac's global hotkeys while it is the active app
  (CGSSetGlobalHotKeyOperatingMode), otherwise macOS ⌘Tab and the Mac's own Rectangle take the keys first.
  vm-agent v11: the DevTools HTTP 500 since the 16:56 Chrome restart was Chrome 156 listening on [::1]:9222 (it
  ignores --remote-debugging-address) while the agent asked 127.0.0.1; the agent now tries both. Default browser on
  the VM = the session's Chrome (chromium-vm-chrome.desktop); Claude Desktop's sign-in kept in a plain gnome-keyring.
  VERIFIED with screenshots (scratchpad of that session): Claude Code full screen + the dock peeking with three live
  thumbnails after Super+Tab; the dock on hover over the Claude app; the dock with six tiles over Halves; Super+Tab
  cycling Claude Code → Claude → Chrome; Ctrl+Alt+Right / U / BackSpace / Return measured by window geometry;
  `cvm tabs` and `cvm eval` after the changes. Marko himself used the dock (Halves) and logged Claude Code in.
  NOT verified: ⌘Tab and ⌃⌥keys pressed by Marko's hand through viewer v5 (needs his keyboard: the hotkey suspension
  cannot be tested without taking his focus); the dock click on a program tile by xdotool (Marko was working on the
  screen, signing Claude Desktop in); a screen-size change under openbox (maximized windows should follow).
  Known: Claude Desktop will not go below 600 px wide, so in a third (518 px on a 1554 px screen) it is wider than its
  slot; chromium-vm-snap keeps it inside the screen, overlapping its neighbour. The second session restart (openbox)
  brought Chrome back on the profile picker; opening profile Default (`google-chrome-stable --user-data-dir=… 
  --profile-directory=Default`) restored the 10 tabs. chromium-vm-worker-gemini left stopped.

- 2.11.2026 (evening, hub session): **viewer v6**: no top bar at all; one gear top-left (see-through, takes its own clicks)
  opens the panel: status, KEYS HELD FOR THIS MAC F1 Speechify | F2 Voice to Text (both on by default, never sent to the
  VM; the viewer suspends the Mac's global hotkeys for ⌘Tab, so it re-presses the key into the Mac with the hotkeys given
  back for 0.25 s: needs Accessibility, amber PERMISSIONS beside the gear until allowed), FULL SCREEN | RECONNECT,
  CLOSE WINDOW | QUIT. Notes (uploads, clipboard, not connected) beside the gear. **Status bar**: a drawn power button
  after UP, click → REBOOT | CANCEL (sudo -n systemctl reboot). **Dock**: a single program picked (tile or ⌘Tab) is
  maximized, out of any split layout. Waiting: Marko allows Accessibility, then tries F1/F2, the panel, the power button.
