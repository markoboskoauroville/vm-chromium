**19.11.2026 v43:** Marko: "custom password without any security limitations. It can be even one one number." The share
password is whatever he types (gear PASSWORD + SET PASSWORD, door share {"password": ...}), stored in UserDefaults
(sharePassword), empty = RFB None. Tested: "1" → auth ok + full ZRLE frame from 100.79.251.19:5901, "2" refused, empty →
types [1] and ServerInit; the app's viewer connected to its own server with "1". After the test a random password was left
(NEW PASSWORD); Marko sets his own. Run 44470989234 (the first v43 run 44470860186 failed on a quote in Door.swift).

**19.11.2026: Remote Viewing (Mantra) v39-v42, built-in VNC viewer and server (Mac).** Marko: "update my application to have
built in server and viewer for VNC inside the app ... The user does not need to install anything". Read viewer/README.md
(Built-in VNC). New files viewer/app/VNCServer.swift (server: NWListener :5901, ScreenCaptureKit, CGEvent, ZRLE/Raw,
DesktopSize, cut text) and ARDAuth.swift (Apple login type 30: DH with own Montgomery modPow, MD5, AES-128-ECB). RFB.swift:
auth types 30/2/1, Hextile, `viewOnly`. Peers.swift: PeerLogin (Keychain), selfIPs, Share menu. Settings.swift: LOGIN per
target, SHARE THIS MAC, PERMISSIONS top right. Built only by GitHub (runs 44469477705 v39, 44469881147 v40, 44470124455 v41,
v42 after), installed from the release, re-signed Mantra Apps. Tested 19.11.2026: python RFB client on 127.0.0.1:5901 and on
the tailnet address 100.79.251.19:5901: wrong password refused, right password → ServerInit 2560×1440 (the BenQ, main
display), full frame Raw and ZRLE (920 tiles, 593 kB) decoded to PNG = the Mac's screen; the app's own viewer on
127.0.0.1:5901 showed the Mac's screen; viewer on chromium-vm unchanged. Screen Recording was allowed by Marko during the test;
Accessibility was already allowed. NOT yet tested: input from a remote viewer (clicks/keys into the Mac), the Apple login (ARD)
against a real Mac's Screen Sharing (no second Mac on the tailnet), a phone's built-in server (the Android app's server was
not up on pixel-7 / nothing-phone-2a at :5900/:5901 yet).

**15.11.2026: session-ack (receipts between Claude sessions).** New core service `session-ack` (short ACK, :8899 on the
Tailscale address + 127.0.0.1, user session-ack, sqlite in /var/lib/session-ack, vmsvc.slice, owner check by tailscale
whois). Source and installer: repo SESSION_ACK (`sudo server/install.sh`); rule MANTRA_MANIFEST modules/session-ack.md.
The VM's Claude Code has `ccmsg` + its hooks (~/SESSION_ACK, install.sh).

**15.11.2026: ttt-relay version 2 (lang=auto).** Voice to Text (Mantra) on the Mac also uses the relay; lang=auto added to every adapter, additive (en/hr unchanged, test 7/7). Installed on the VM with install.sh, /health version 2. Mac keys come in via POST /keys replace:false.

**14.11.2026: ttt-relay (TTT's transcription in Frankfurt).** New core service `ttt-relay` (short TTT, :8897 on the
Tailscale address, user ttt-relay, keys in /var/lib/ttt-relay, vmsvc.slice). Read ttt-relay/README.md. Not installed yet:
`sudo ttt-relay/install.sh`.

# TAKEOVER

**14.11.2026: core-only boot, every program a service (vmctl).** Marko: "only thing which is running is connection keeper
... all other services are optional ... on the gear icon". Read tools/vmctl/README.md.
- Core (enabled, locked): ckbond (vmcore.slice, Nice -15, OOM -1000), tailscaled, ssh.socket, chromium-vm-xvnc,
  chromium-vm-session (openbox ONLY now), chromium-vm-statusbar, chromium-vm-agent, chromium-vm-vmctl (:8896), user queen,
  Oracle agents. Everything else disabled at boot (nothing deleted): claude-app, claude-code, Chrome (new unit
  chromium-vm-chrome, split from the session), Firefox (user vm-firefox + wa-door), Brave (user vm-brave), pixel1/pixel2
  (containers restart=no, cpu-shares 128), pixel-door (pixel7d + pixel7-jobs), docker+containerd, idle reaper, macro,
  dock+refit, gemini worker, yt-monitor/yt-upload/yt-transcribe, two-locations sync, aooserver, reaper-daw helper.
- `vmctl list|start|stop|lease` on the VM; API + leases; client tools/vmctl/vmctl_client.py (= `vmctl` on the Mac,
  token ~/Downloads/API/chromium-vm-vmctl.txt). Status bar shows CKBOND (green/red) | TSCALE | QUEEN | running services.
- Callers: chromium-vm-snap/dock (vmctl start), vm-open-url (starts brave/chrome service first), vm-whatsapp start (goes
  through the firefox service), chromium-vm-phone (docker + idle reaper as --auto deps, gc after stop), Mac `pixel7`
  (ensures pixel-door, 30 min lease). Viewer v33 (Mac) and Android v51: gear → SERVICES.
- Rebooted 14.11.2026 08:13 UTC: up in < 1 min, only core running, 654 MB used (3.4 GB before). Deploy copy used:
  ~/vmctl-deploy (git archive); ~/vm-chromium-git on the VM has diverged local commits (not touched).
- Known: starting firefox starts wa-door, whose call bridge starts Pixel 2 (and docker); the reaper keeps Pixel 2
  (CVM_REAPER_KEEP_PHONES=2), so stop pixel2 by hand. Proposed, not done: disable unified-monitoring-agent (fluentd, ~80 MB),
  ModemManager, avahi, rpcbind, udisks2.

**Renamed 13.11.2026:** VM Machine Remote Viewer (Mantra) is now **Mantra Remote Viewing** (Marko). Done by Queen.

**9.11.2026 (idle reaper, task 66):** the two cloud phones are on demand. `chromium-vm-reaper.timer` (every 2 min, idle
20 min from /etc/chromium-vm-reaper.conf) runs `chromium-vm-reaper.py`: stops a Pixel mirror (scrcpy + bar) nobody looks at,
then the container when no job/pixel7d use (mark `chromium-vm-phone touch`, the pixel7 lock) and no viewer; never any Claude process;
Never touched (also claude-desktop and claude sessions): transcriber, Xvnc, dock, vm-agent, Gemini worker, Chrome, sshd, tailscale.
Every stop is a line in ~/.cache/chromium-vm/reaper.log. `chromium-vm-phone start|ensure|stop|touch|status N` does the work;
the dock shows "Pixel N ▶" for a stopped phone (click = start, boots Android, mirror opens) and a load/cpu readout;
pixel7d and pixel7-jobs call `ensure 1` (docker start, wait for boot). The scrcpy services and the bar are no longer
enabled at boot. Verified: dock click via xdotool started Pixel 1 (boot ~40 s), reaper (idle 1 min) stopped mirror then
container, pixel7d /screenshot started it again in 28 s. Load 12 -> 0.35 after the stops.

**5.11.2026 (session mac-os-ses1-05-nov, closed):** later the same afternoon v23 ⌘W minimizes, v24 Rectangle's keys stay on the Mac (RectangleKeys.swift), v25 hover mouse baked in (Mac arrow hidden over the picture, BackgroundCursor). Installed in /Applications: **v25**. Not yet tried by Marko's hand: green/yellow, ⌘W, a Rectangle key, the hover.

**5.11.2026 (~15:00):** viewer **v22**: a normal Mac title bar again (close, minimize, green =
classic zoom to the screen's visible frame and back, never full screen; ⌃⌘F still full screen; Window menu ⌘M / Zoom).
The window is .resizable again only so the green button is not greyed out; windowWillResize blocks every edge drag, so
only the bottom-left grip and the zoom change its size. VM: `chromium-vm-snap` remembers each window's slot
(~/.cache/chromium-vm/slots.json) and the new service **chromium-vm-refit** (`chromium-vm-snap watch`) puts snapped
windows back into their slots when the screen size changes (bug: after maximizing, the triple view stayed in the old
corner). The Pixel bar reads the screen width from X (GTK kept the old width, REBOOT was cut). Verified: xrandr
1920×1080 → thirds of 1920; AX zoom 1280×858 → 2560×1415 → back; screenshots.

**5.11.2026 afternoon:** Xvnc runs without a login blacklist (`-BlacklistThreshold=1000000 -BlacklistTimeout=1`,
stage1/bin/start-xvnc; the door is the Tailscale address only): TigerVNC's default had locked the Pixel 7 out after a
few wrong redials. The VM's Pixel 7 (redroid, Android 15) got 40 apps from Marko's real Pixel 7 (all but the
Google-services, camera and launcher ones; no logins or data copied), installed with adb install-multiple.

**State 5.11.2026 (session closed):** Mac viewer VM Machine Remote (Mantra) **v20** (GitHub release, /Applications):
picture on its own aspect-fitted layer (v19, never stretched); gear → REMOTE SCREEN SIZE (FOLLOW WINDOW or the VM's
xrandr modes via vm-agent `screen_modes`); bottom-right grey line moves the window, bottom-left resizes it (v16–v18, the
window is not .resizable, full screen lends it); a lone ⌘ sends Super (v20). On the VM: four screens (Claude Code,
Claude, Chrome, Pixel 7 via scrcpy 5 in /opt/scrcpy, letterboxed, `chromium-vm-pixel7` + the Pixel bar
`chromium-vm-pixel7-bar`: PORTRAIT | LANDSCAPE, REBOOT); the dock: four app tiles + Claude Code | Chrome (40|60),
Claude | Chrome (40|60), Claude | Claude Code | Pixel 7 (⅓ each); Command alone opens it pinned (X RECORD); a screen or a
layout starts what has no window first (`chromium-vm-snap show|layout`, `ensure`). Deploy desktop pieces one by one:
desktop/install.sh restarts every screen service, the Claude Code one included.


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
- 2.11.2026 (~19:50 CT): **viewer v7**: the gear moved to the bottom-right corner, on the VM's status line right after
  its power button (the status bar keeps its last 26 px free: GEAR in chromium-vm-statusbar.py); the panel opens above
  it; per key a choice F1 Speechify MAC | VM, F2 Voice to Text MAC | VM; notes and PERMISSIONS in a pill above the gear.
  Accessibility granted by Marko 21:11. Not yet tried by hand: dictating with F1/F2 into the VM, the panel, reboot.
- 2.11.2026 (~20:20 CT): **viewer v10 + vm-agent v12**, Marko: "Text simply does not arrive. Please test it yourself."
  Three causes, all fixed and tested end to end by Claude (BlackHole input + say, scratch xfce4-terminal on the VM):
  (1) the picture was no text field, so Voice to Text's Accessibility insert landed nowhere → ScreenView is an AXTextArea
  whose AXSelectedText/AXValue writes go to the VM; (2) F1: Speechify also has an event tap and got the real press, so
  re-pressing toggled it off → only F2 (Voice to Text, Carbon hotkey) is pressed again (App.pressAgain); (3) a program's
  ⌘V comes without a ⌘ flagsChanged and arrived as a bare "v"; the terminal pastes on Ctrl+Shift+V → ⌘V with text takes
  the Mac clipboard at once and calls vm-agent `paste_text` (clipboard, then Ctrl+Shift+V into a terminal, Ctrl+V else).
  Results: F2 "Voice to text writes into the terminal." and Chrome's address bar; F1 pasted what Speechify heard on its
  own microphone. Speechify ignores the system input (it records its own chosen mic).

## v11 (5.11.2026)
The login is under the gear: USERNAME (ubuntu) and PASSWORD, SAVE AND CONNECT writes ~/Downloads/API/chromium-vm-vnc-password.txt (the old name chromium-vm-vnc.txt is still read). A missing or refused password opens the login instead of a note. The gear sits 12 pt in from the bottom-right corner: in the corner macOS took the click for resizing the window.

## v12 (5.11.2026)
An Edit menu (Cut, Copy, Paste, Select All): without it ⌘V did nothing in the gear's PASSWORD field. The VM picture still takes ⌘V first.

## v13 (5.11.2026)
The picture is aspect-fitted (never stretched), the mouse mapped through the same rectangle. The VNC password lives only in the Keychain (service community.auroville.chromiumvm.vnc), typed under the gear; no text file is read for it.

## v14 (5.11.2026)
Renamed VM Machine Remote (Mantra) (bundle id community.auroville.chromiumvm kept, so the Keychain password stays). Icon: VMM / REM over the ORACLE logotype (icons6 wordmark: background).

## v15 (5.11.2026)
Icon: VM / REMOTE on a black terminal tile with a green block cursor (icons6 terminal background).

## 5.11.2026: viewer v26, ⌘Tab stays on the Mac
HotKeys.capture no longer suspends the Mac's global hotkeys (always mode 0), so ⌘Tab, Spotlight, Rectangle and Speechify
keys stay with macOS while the viewer is in front. ScreenView.keyDown: ⌥Tab → Super+Tab (the dock's program switch);
⌘Tab that reaches the view is dropped. Marko tested by hand 5.11.2026: both work.
Also 5.11.2026: the VM's Claude Code speaks through the Mac with `macsay` (~/.local/bin/macsay, /usr/local/bin/macsay,
token ~/.config/mantra-door.token, rule in ~/.claude/CLAUDE.md). MANTRA_MANIFEST modules/talk-through-the-mac.md.

## 7.11.2026: session VM_SES1_06-NOV closed (Claude app on the VM)

- New skills, linked into ~/.claude/skills: **this-machine** ("this machine" = this VM, never the Mac unless Marko
  says so) and **update-this-machine** (how to change the VM from here). ~/.claude/CLAUDE.md: replies text only.
- Dock: "Claude app" instead of "Claude"; five tiles (Claude Code, Claude app, Chrome, Pixel 1, Pixel 2); layouts
  Claude Code | Chrome, Claude app | Chrome, **Claude app | Pixel 1 | Pixel 2** (phones at their exact shape, no bars).
- Two phones: pixel7 (:5555, Pixel 1, signed in) and pixel7b (:5556, Pixel 2, fresh, not signed in; its GSF id still
  to register at google.com/android/uncertified). Services chromium-vm-pixel7 / chromium-vm-pixel7b.
- Japri stu barcuni images (Suno, square): Drive My Drive / Mantra References / JAPRI STU BARCUNI (Gemini - Nano
  Banana in Chrome) / results; references incl. marko_face_portrait.jpg.
- Left on screen: the Claude app alone, full screen. Nothing running in the background from this session.

- 9.11.2026 (viewer **v28**, renamed **VM Machine Remote Viewer (Mantra)**, bundle id unchanged): the mouse is the VM's only where the point under the arrow is the viewer's own pixels. ScreenView checks CGWindowListCopyWindowInfo(.optionOnScreenAboveWindow) (cache 50 ms; skips own windows, alpha 0, layer < 0, see-through full-display overlays) on every move/click, and a global mouse monitor gives the arrow back when the pointer is over another app's window (Speechify, Firefox, menu bar). Door actions: `hit_test {x,y}` (CG screen coords, never moves the pointer) and `pointer_sent` in `status`. Built locally (repo is private, compile-only-on-github 8.11.2026). Verified with a floating test panel via hit_test (covered by panel / Firefox / menu bar, ours on a free strip). Marko's hand test: Speechify over the viewer, click it.

## 14.11.2026: the viewer updates itself (v31, v32)
viewer/app/Updater.swift: at start `gh release view` on this repo; a Latest vN newer than VERSION is downloaded to
~/Library/Caches/community.auroville.chromiumvm/update/vN, then the question "Mantra Remote Viewing vN is ready · Do you want
to update?" (Update / Later). Update: a detached script waits for the quit, signs "Mantra Apps", swaps the .app, reopens.
Tested v31 → v32 the same morning. From now on a push to main (viewer/**) reaches the Mac by the question; no manual install.
The same file is the kit MANTRA_MANIFEST/kits/mac-updater for every Mac app.

## 15.11.2026: santoshi-relay (core service SRELAY)
MediaMTX v1.21.3 (pinned, sha256 checked) for the Santoshi live stream: Manual Camera sends ONE stream by WHIP, viewers read WHEP/LL-HLS
at https://relay.ples-duse.org (:8889 WHIP/WHEP, :8888 HLS, :8443 API with key, 8189 udp+tcp media on 10.0.0.86 only, 8890/udp SRT).
Install: `printf 'sha256:…' | sudo santoshi-relay/install.sh` (first time; then plain sudo). Publish key: /etc/santoshi-relay/key (root:ubuntu 640),
its hash in /etc/mediamtx/publish.hash; the Pages secret RELAY_KEY of santoshi-band holds the same key. Oracle security list rules added
by oci CLI (8888-8889, 8189, 8443 tcp; 8189, 8890 udp; 80 was already open). TLS: certbot standalone, renewal hook copies to /etc/mediamtx/tls.
Recording: /srv/santoshi-rec/santoshi (1 min fmp4, 72 h) → santoshi-rec-upload (user ubuntu, rclone drive.file) → Drive
"Santoshi Band live (relay)/Santoshi live <date time>/Video" + Docs "Chat" and "Stream statistics" from the site's /api/relay.
Proven 15.11.2026 with the Sony on the Pixel: 1 publisher, 8 viewers, MediaMTX 13 % of one core. YouTube/RTMP forward: santoshi-forward, off.

## 15.11.2026: Exit node for VPN (Mantra) (repo MANTRA_VPN)
chromium-vm is a **Tailscale exit node**: Marko's Mac and phones can send all their internet through Frankfurt
(public 130.61.181.83, Oracle DE) with the app VPN (Mantra), FRANKFURT | DIRECT. No secret anywhere: only devices in his
tailnet see the exit node. Done on the VM: `/etc/sysctl.d/99-tailscale.conf` (net.ipv4.ip_forward=1,
net.ipv6.conf.all.forwarding=1; before, ip_forward was only set at run time by Docker), `sudo tailscale set
--advertise-exit-node` (AdvertiseRoutes 0.0.0.0/0 + ::/0). Forwarding/NAT are Tailscale's own chains (ts-forward from
FORWARD, ts-postrouting MASQUERADE); FORWARD policy DROP (Docker) and every other service untouched (MediaMTX ports,
ckbond :443, session-ack :8899, SSH). Oracle security list: udp 41641 ingress added by oci CLI (Tailscale direct path;
the Mac went from DERP "fra" to direct 130.61.181.83:41641, 37 ms). The exit node must be **approved once** in the
Tailscale admin console (Machines → chromium-vm → Edit route settings → Use as exit node). Off again:
`sudo tailscale set --advertise-exit-node=false`. Manifest: MANTRA_MANIFEST modules/vpn-exit-node.md.

## 15.11.2026: CLOUD MIXER (vmctl CMIXER, repo CLOUD_MIXER)
The programmatic vision mixer ("vMix in the cloud"): clone ~/cloud-mixer, daemon `cloud-mixer.service` (API 127.0.0.1 and
100.102.86.30 port 8841, not enabled at boot), show runner `cloud-mixer-show.service` + `.timer` (settings
/etc/cloud-mixer/show.env). Its program is published by SRT to the relay (127.0.0.1:8890, path santoshi) with the relay
publish key read from /etc/santoshi-relay/key. Media in /srv/cloud-mixer/media/<show>/. Site switch token (paired camera
"Cloud Mixer (VM)") in ~/.config/cloud-mixer/site-camera-token (600). Armed 15.11.2026 for 11:00:00 UTC (the Šubić
concert of 17.10.2026, 1:42:46). The relay has only the path santoshi: dry runs go to a private MediaMTX on 127.0.0.1
(CLOUD_MIXER/tools/test-mediamtx.sh, SRT :8990). Installed for it: python3-numpy, python3-pil, rsync. Note: the box has
2 cores; another worker's studio-ladder (HLS ladder) took ~110 % at 04:52 UTC the same day.

## 15.11.2026: studio-stream (core service STUDIO)
The Mac (SOUND_LINK/studio/studio.py) sends ONE master by RTMP over Tailscale to `studio-ladder` (ffmpeg listening on
100.102.86.30:1935, `rtmp://100.102.86.30:1935/studio/master`); it writes the HLS ladder to /dev/shm/studio-hls (1080 copied,
720/480/360 libx264 superfast; audio Q:160/80/40 S and M as EXT-X-MEDIA renditions). `studio-web` serves it at
https://relay.ples-duse.org:2053/studio/master.m3u8 and /studio/health (live, age, viewers). User `studio`, certificate copy in
/etc/studio-stream/tls (certbot deploy hook studio-stream). Install: `sudo studio-stream/install.sh` (never touches MediaMTX).
CPU: ~100 % of one of the two cores while a master runs (CPUQuota 150 %). **Open:** the Oracle security list has no tcp 2053
ingress yet (the session's permission check refused the oci update): until it is added, the door answers only on the VM and over
Tailscale. The rule: tcp 2053 from 0.0.0.0/0, description "Studio stream HLS ladder".

**15.11.2026, santoshi-relay as a measuring point.** The relay's own recordings are the cleanest phone→relay probe:
`/srv/santoshi-rec/santoshi/<UTC>.mp4` pieces, concat with `-vn -c:a copy`, decode with ffmpeg (no numpy on the VM: copy the
small .mka to the Mac). Each piece's audio starts 0.14–0.24 s in (aligned to the first video frame), not a hole. The API on the VM
itself: `curl -sk https://127.0.0.1:8443/v3/paths/get/santoshi` and `/v3/webrtcsessions/list` (no key from localhost). Measured
15.11.2026: 716 s of a 1 kHz test tone through the phone with 0 drops; MediaMTX counted 318 lost RTP packets in 50 min (video included).
15.11.2026 ~05:25 UTC: relay path **pixel** added (live /etc/mediamtx/mediamtx.yml edited in place, hot reload, the santoshi
muxer kept running; backup mediamtx.yml.bak-20261115-cloudmixer; template santoshi-relay/mediamtx.yml.in updated). The phone
publishes there when the site's KV `relay:campath` = pixel (expires 15.11.2026 13:00 UTC); CLOUD MIXER reads it by SRT
(`streamid=read:pixel`, 127.0.0.1 allowed) and publishes the program with text on santoshi.

**15.11.2026: santoshi-hls tunnel (prepared, waiting for Marko's Cloudflare authorization).** Kit santoshi-relay/hls-tunnel/
(setup.sh install|login|tunnel, santoshi-hls.yml, santoshi-hls-tunnel.service, cache_rule.py). cloudflared 2026.11.0 is installed
(apt pkg.cloudflare.com, user cloudflared); no tunnel and no service yet. Why: MediaMTX binds an HLS session to the client IP, so a
Cloudflare Worker cannot proxy it (changing egress addresses → 401 on segments); through cloudflared every request comes from 127.0.0.1.
Ingress only ^/santoshi/[A-Za-z0-9_.-]+\.(m3u8|mp4)$ → https://127.0.0.1:8888 (MediaMTX HLS is TLS; originServerName
relay.ples-duse.org), everything else 404. Next: `santoshi-relay/hls-tunnel/setup.sh login` (as ubuntu; open the printed URL in
Chrome Profile 15, Marko clicks santoshiband.org → Authorize; the URL expires after about 10 minutes), then `sudo -E … tunnel`, then
`python3 …/cache_rule.py`. Hostname live.santoshiband.org (15.11.2026 plan change: his new zone santoshiband.org, not ples-duse.org); one authorization = one zone.

**15.11.2026 14:20: santoshi-hls tunnel is up.** Tunnel santoshi-hls (id 20858b82-57fa-4b0f-96c5-2736af65529b), units
santoshi-hls-tunnel (cloudflared, /etc/cloudflared/santoshi-hls.{yml,json}, 640 root:cloudflared) and santoshi-hls-proxy
(127.0.0.1:18888, /opt/santoshi-hls/hls_cache_proxy.py, DynamicUser). Proxied CNAME live.santoshiband.org (zone santoshiband.org;
apex and www belong to the Pages project, untouched). cert.pem in ~/.cloudflared (600) covers ONLY santoshiband.org.
Why the proxy: the cert's token may not write Cache Rules (403), and MediaMTX's ?session=<viewer> makes every segment URL different.
The proxy holds one session, strips ?session= and answers segments public max-age=60, so Cloudflare's default cache (.mp4) keeps
each piece once per location; playlists no-cache, LL-HLS blocking reloads pass through. Only /santoshi/*.m3u8|mp4; all else 404
(checked: /v3/…, /pixel/…, /santoshi/whep → 404). Port 8896 is vmctl serve on the Tailscale address: not free.

## Relay load test 15.11.2026 (result)
HLS viewers from GitHub runners against relay.ples-duse.org:8888 (test path loadtest, removed): clean to 12 viewers (0 % stalls, 44 Mbit/s), 16 viewers 17 % stalls, 50 viewers 82 %; VM CPU stayed ~20 %. The VM's public egress is only ~50-55 Mbit/s (confirmed by a direct upload test), so direct capacity is 12-13 viewers at 3.65 Mbit/s. Needs: everyone through Cloudflare (live.santoshiband.org), a lower rendition, a YouTube copy, and a look at the OCI VNIC (shape says 2 Gbit/s). Full table and method: MANTRA_MANIFEST modules/studio-stream.md. The VM was left clean (config back to the backup, no loadtest files).
**15.11.2026, santoshi-relay: mixer only** (Marko: "Yes, mixer only"). Cameras (user santoshi, the RELAY_KEY) may publish only on
`~^cam-[a-z0-9]{4,16}$` (+ the old `pixel`); user **mixer** (key /etc/santoshi-relay/mixer-key, root:ubuntu 640, sha256 in
/etc/mediamtx/mixer.hash) from 127.0.0.1 is the only publisher on santoshi; anonymous localhost reads cam-*. Reading santoshi stays
open to everyone (the hls proxy reads anonymously). Config only, in place: `sudo santoshi-relay/apply-config.sh` (masked diff + backup,
MediaMTX reloads by itself; applied 15:22 UTC, backup mediamtx.yml.20261115-152235). install.sh fills @MIXER_HASH@ too. Proven: the
camera key on santoshi gets "failed to authenticate", on cam-vmtest it publishes. The program on santoshi: CLOUD_MIXER cloud-mixer-live.

**15.11.2026 ~16:45: santoshi-hls under load.** 45 GitHub-runner readers held the VM at its ~54 Mbit/s egress cap. The URLs are NOT
per viewer: two "players" fetching the playlist get the same session-free names, and client C got `cf-cache-status: HIT` on A's URL
(FRA). The MISS of "client C" in tun.sh came from the test script itself (it adds a different ?session= on purpose). Most likely cause:
no Tiered Cache, so EVERY Cloudflare location (GitHub runners sit in many) fetches each segment from the VM once (~15 locations × 3.7
Mbit/s ≈ the cap). Fix: Smart Tiered Cache on the zone santoshiband.org. It is free, but the tunnel cert's token gets 403, so it is
Marko's click: dash → santoshiband.org → Caching → Tiered Cache → Smart Tiered Caching → Enable. The proxy logs counts only, every
30 s (`journalctl -u santoshi-hls-proxy`: segment=N distinct_segment=M colos=…); N ≈ M × locations shows what reaches the VM.

**15.11.2026 ~17:10: santoshi-hls playlists.** With Smart Tiered Cache on, segments leave the VM once each (segment = distinct_segment).
At 102 readers the limit was ~80 playlist requests a second (no blocking reloads: playlist_q never appeared, the kit polls like plain
hls.js), each fetched from MediaMTX over a NEW TLS connection and rewritten: the proxy at 77 % of a core. Now (c9d3556): one fetch per
playlist per 0.5 s (index 5 s), shared by all, rewritten once; plain HLS (LL lines removed, _HLS_ ignored); kept-alive TLS to MediaMTX.
Playlists stay `no-cache`: Cloudflare does not cache .m3u8 without a Cache Rule, and the zone's Browser Cache TTL (4 h) rewrites a short
max-age (segments arrive with max-age=14400), which would freeze a live playlist in the browser. Counter `playlist_shared` = served
from the shared copy.

**17.11.2026: santoshi-hls tunnel stopped (Marko gave up santoshiband.org).** `systemctl disable --now santoshi-hls-tunnel santoshi-hls-proxy`
(both inactive and disabled). Its only hostname, live.santoshiband.org, had its DNS record deleted by santoshi_band_site's
tools/release_domain.py; the site's /api/live hands viewers the relay's own HLS door again (relay hostname under ples-duse.org, :8888),
so the direct capacity limit of the load test applies (~12 viewers). The tunnel object santoshi-hls (credentials /etc/cloudflared/santoshi-hls.json)
and the kit in santoshi-relay/hls-tunnel/ are kept: to bring the cached door back, put a hostname of a zone this account still has
(e.g. hls.ples-duse.org, the original plan) in santoshi-hls.yml, `setup.sh login` for that zone (Marko's authorization), route DNS, enable both units.
~/.cloudflared/cert.pem covers only the santoshiband.org zone and is useless for any other zone.
