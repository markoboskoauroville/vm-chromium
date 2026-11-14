# LESSONS

1. (2.11.2026) Oracle Always Free has 200 GB of block storage in all: replace a boot volume at the same size, then grow it.

- 2.11.2026: Ubuntu 24.04 sets kernel.apparmor_restrict_unprivileged_userns=1, so the xtradeb Chromium (.deb) dies
  with "No usable sandbox!" in a loop. Fix: an AppArmor profile for /usr/lib/chromium/chromium with `userns,`
  (stage1/apparmor/chromium-vm, loaded by setup.sh). Never --no-sandbox.
- 2.11.2026: the repo is private and the VM has no GitHub login: copy stage1 over with `tar | ssh`, don't clone.
- 2.11.2026: plain Chromium (xtradeb, Debian keys in /etc/chromium.d/apikeys) signs into Google websites but never
  into the browser profile or Sync: Google limited that to Google Chrome in March 2021. Google Chrome for Linux
  arm64 exists (stable 156.0.8078.79, dl.google.com repo), so chromium-vm runs Google Chrome
  (`setup.sh --chromium chrome`, the default now). Ubuntu's /etc/apparmor.d/chrome already allows its sandbox.
  The profile was copied ~/.config/chromium → ~/.config/google-chrome once; tabs and cookies came along
  (both use --password-store=basic).
- 2.11.2026: Chrome 136+ ignores --remote-debugging-port on the default profile folder; give it --user-data-dir.
- 2.11.2026: `xclip` setting the clipboard forks and keeps the SSH channel open: redirect its stdout/stderr.
- 2.11.2026: claude.ai DOM: composer `div[contenteditable].ProseMirror` (tiptap), answers
  `[data-testid=assistant-message]` with the text in `.prose`, streaming flag `[data-is-streaming=true]`,
  send `button[aria-label="Send message"]`. insertText through execCommand works on the composer.
  A new chat's url changes after the first send: follow the tab by its DevTools id, not its url.
- 2.11.2026: Stream.getStreamsToHost streams that are not scheduled on a run loop open in the background: writing
  before `.open` fails silently and Xvnc logs "reading version failed: not an RFB client". Wait for `.open`.
- 2.11.2026: `pkill -f "<words>"` inside `ssh host '…'` kills the ssh shell itself (its command line holds the
  words): use `pkill -x rclone`.
- 2.11.2026: rclone 1.60 can stay after an upload is done; vm-agent gives it a deadline by size and then checks
  Drive with lsjson (same size = done). The /json/new DevTools endpoint needs the whole url percent-encoded.
- 2.11.2026: the Claude extension's side panel is a DevTools target (chrome-extension://fcoeoabgfenejglbffodgkkbkcdhcgfn/
  sidepanel.html): it can be driven like a claude.ai tab.
- 2.11.2026: the Claude extension's chat is the frame `claude.ai/cic/new?surface=cic_sidepanel` (DevTools type
  iframe) inside sidepanel.html: composer `[contenteditable]` ("Write your prompt to Claude"), button "Start task".
  Driven from the Mac it answered in ~20 s. It cannot touch Chrome's own UI (bookmarks bar, saved tab groups):
  only web pages. Its tools also failed once with "anchor tab group not established".
- 2.11.2026: saved tab groups deleted with the VM's own pointer (xdotool on :1): right-click chip → Delete group →
  dialog button checked by its colour (#035F6A at 783,273 in a 1280×798 screen) before the click. Deleting one
  deletes it on every device of the account. 11 "Claude" groups were removed; BRAIN BRAKE kept.
- 2.11.2026: Chrome prefs set through chrome.settingsPrivate on a chrome://settings tab (DevTools):
  auto_pin_new_tab_groups=false, bookmark_bar.show_tab_groups=false, so the extension's task groups no longer pile
  up on the bookmarks bar.
- 2.11.2026: dark everywhere = Chrome flags `--force-dark-mode --enable-features=WebContentsForceDark` (session
  script) + Preferences browser.theme.color_scheme2=2 (Mode Dark; not in settingsPrivate). Checked: Google Search,
  Gmail, Drive, Docs, Sheets all dark. The session script holds its flags in memory: restart the service, not Chrome.
- 2.11.2026: rewriting Preferences with json.dump adds spaces, so the crash-flag sed missed and Chrome showed
  "Restore pages?" with the old tabs gone; Ctrl+Shift+T brought them back. The sed now allows the space.
- 2.11.2026 status bar: on this Xvnc screen a depth-32 (RGBA) GTK window is shown opaque even with xcompmgr running
  (-n or -c), and a SHAPE cut-out leaves black because Chrome does not repaint what the shape gives back. What works:
  pseudo-transparency: with xcompmgr on, Gdk.pixbuf_get_from_window on Chrome's (redirected) window returns the strip
  under the bar; paint it, then black at 50%, then the text. Redraw every 400 ms.
- 2.11.2026 router: vm-agent's `tabs` gives no ids; the router reads `Target.getTargets` through `cdp` on `browser`.
  `Target.createTarget {background: true}` opens a tab without taking the front from another session's tab, and
  `Page.captureScreenshot` works on a background tab.
- 2.11.2026 router: a tab argument must be checked before "this session has no tab": the first self-test answered a
  stranger's call on another session's tab with 409 instead of 403.
- 2.11.2026 Gemini: a result is an `<img>` inside `<generated-image>` and its src is blob:, exactly like a pasted
  reference preview (inside user-query-file-preview): tell them apart with closest('generated-image'), never by blob:.
- 2.11.2026 router app: OFF quits only the window's app, not the router: relaunch after a build presses OFF, and a
  build must never cut the sessions' running jobs.
- 2.11.2026: Gemini on the VM: the pasted references are 1024×1024 `img` in `user-query`; take the result only from
  `generated-image img` / `model-response img`. A background tab never finishes the picture: bring the tab to front.
  "Your limit resets at H:MM PM" (Chrome's clock = UTC on the VM) is the limit; ~37 images per window, free account.
- 2.11.2026: never `pkill -f`/`pgrep -f` with words that are in your own command line (ssh shell, zsh -c): it hits
  itself; and zsh does not split `$(pgrep …)` into several pids. Use `ps ax -o pid,args | grep -E "python3? …[x]"`.
- 2.11.2026: the session's resize watcher matched every window whose class contained "chromium" and stretched the
  status bar over the screen: match Chrome's class exactly, give helpers their own prgname.
- 2.11.2026: Chrome 156 (headful) ignores --remote-debugging-address and binds DevTools to "localhost", which came up
  as [::1]:9222 after a restart; Ubuntu's /etc/hosts gives Python only 127.0.0.1 for localhost (curl tries both, so
  curl worked and the agent did not). Ask 127.0.0.1 and [::1].
- 2.11.2026: matchbox's default kbdconfig binds Alt+Tab, Alt+n, F11 …; openbox with an own rc.xml binds only what is
  in it. openbox `<margins><bottom>22</bottom>` keeps maximized windows above an override-redirect status bar.
- 2.11.2026: a Mac app never sees ⌘Tab (the Dock takes it) nor another app's global hotkeys (Rectangle's ⌃⌥←):
  CGSSetGlobalHotKeyOperatingMode(CGSMainConnectionID(), 1) while the app is active, 0 when it resigns; the mode
  belongs to the app's connection, so a crash gives the hotkeys back. ⌃⌥ + letter composes nothing on the Mac: send
  it as Ctrl+Alt+letter.
- 2.11.2026: Claude Desktop for Linux (Electron) on a desktop-less VM: "session will not persist" unless a keyring
  answers; gnome-keyring will not create an empty-password keyring by itself (`--unlock` with empty stdin does
  nothing), but a plain keyring file ([keyring] display-name=login …, ~/.local/share/keyrings/login.keyring + default)
  is always unlocked; launch with --password-store=gnome-libsecret. First start takes ~30 s on 2 cores (white window).
- 2.11.2026: xdg-open on the VM sent sign-in links to the old plain Chromium (chromium.desktop was the default
  browser): a .desktop file with the session's --user-data-dir makes the session's Chrome the default.
- 2.11.2026: with xcompmgr (composite) running, XGetImage of an obscured window returns its full content, so live
  thumbnails of the windows behind work; the dock reads the root window under itself BEFORE it maps (static band).
- 2.11.2026: testing switching keys while Marko works on the same screen takes his focus away mid-typing: look first
  (passive screenshot + getactivewindow), test when the screen is idle, give the focus back at once.

- 2.11.2026 (viewer v10): with the Mac's global hotkeys suspended (CGSSetGlobalHotKeyOperatingMode, for ⌘Tab on the
  VM) Carbon hotkeys like Voice to Text's F2 never fire; the viewer re-presses the key with the hotkeys given back for
  0.25 s. Speechify also has its own event tap and gets the real press, so re-pressing F1 turns it straight off: only
  swallow F1. Dictation apps write by Accessibility into the focused text field: a remote-screen view must be an
  AXTextArea (settable AXSelectedText, readable AXValue) or the text lands nowhere. A program's ⌘V has no ⌘
  flagsChanged before it: read the Mac clipboard at once and paste on the VM via vm-agent `paste_text`;
  xfce4-terminal pastes on Ctrl+Shift+V (Claude Code takes Ctrl+V as image paste).
- 2.11.2026: test dictation without his mic: input → BlackHole 2ch, `say -a 125 "..."` (by device number; `say -a
  "BlackHole 2ch"` crashes), key presses by CGEvent, paste into a scratch `xfce4-terminal -x sh -c "cat > /tmp/f"`
  on the VM; input back to External Microphone. Speechify ignores the system input and records its own microphone.

- 5.11.2026: a button in the very corner of a resizable window never gets the click; macOS uses it for resizing. Keep controls 12 pt in.
- 5.11.2026: a Swift app with its own main menu needs an Edit menu, or ⌘C/⌘V/⌘A do nothing in its text fields.

## 5.11.2026
- The Mac's own corner resize took the bottom-right grip: a borderless window that should move from that corner must not
  be `.resizable`; lend `.resizable` only for full screen (toggleFullScreen needs it) and take it back on exit.
- "Stretched" was not the viewer: scrcpy 5 locks its window to the phone's shape, so in a wide slot it grew 3413 px tall
  on a 1440 px screen. `--no-window-aspect-ratio-lock --render-fit=letterbox` keeps it inside its slot.
- The viewer sends ⌘ as Ctrl (copy/paste on the VM), so a lone ⌘ never reached the VM as Super: the dock's Super watcher
  needs the viewer to tap Super for a lone ⌘.
- A layer-backed NSView that also implements draw(_:) gets its layer contents scaled on both axes during live resize:
  put the picture on its own sublayer with contentsGravity resizeAspect.
- xdotool clicks at fixed rows in an Electron list drift as soon as a group folds: read the screen before each click,
  and never send a menu's shortcut letter blind (three "a" landed in a chat box, cleared before sending).
- 5.11.2026: a snapped (not maximized) window does not follow a new Xvnc size; chromium-vm-refit re-places them by slot.
- 5.11.2026: the green button is greyed on a window without .resizable; keep it and refuse live resizes in windowWillResize.
- 5.11.2026: the hotkey suspension for ⌘Tab also silenced Rectangle; Rectangle's own keys are re-posted to the Mac (v24).
- 5.11.2026: GTK's screen width goes stale after xrandr; the Pixel bar asks X for it.

## 5.11.2026
- `cvm type` types into whatever window has focus: it landed in the Pixel 7 window and opened SwiftKey settings. Focus
  the target first (`xdotool windowactivate --sync <id>` over Tailscale SSH, ids from `xdotool search --name`), then
  look at a `cvm shot` before pressing Return.
- A push GitHub rejected ("fatal error in commit_refs_rules") and then accepted started no workflow run: check
  `gh run list` after every push and dispatch it by hand when missing.

## 9.11.2026
- Never test a mouse fix with synthetic CGEvent moves: they merge with Marko's real pointer and take it. Ask the app (door `hit_test`) instead; the debug entry is cheaper and safe.
- A hidden Mac arrow (CGDisplayHideCursor + SetsCursorInBackground) survives a window covering the viewer: decide per event whether the point is the viewer's own pixels, and add a global monitor for moves the viewer never receives.

## 9.11.2026 (idle reaper)
- Stop the scrcpy mirror before the container: with Restart=always it loops on `adb wait-for-device` and burns CPU. 30 fps software mirrors of idle phones put the 2-core VM at load 12.
- "Is anyone looking" = VNC client on :5901 + its window mapped + (it is the front window or X input within the idle time); X idle comes from python-xlib screensaver_query_info (no xprintidle on the VM).
- redroid takes ~40 s to boot_completed: on-demand callers (pixel7d, jobs) must wait; a request to a stopped phone takes ~30 s the first time.
- Disabled units (scrcpy x2, bar) stay disabled; docker restart policy unless-stopped keeps a stopped container stopped across reboot.

## 14.11.2026: the updater (update at start)
- The app asks gh / GitHub for the Latest release; tag vN must equal the app's version number or it never sees itself as current.
- Test it with two releases: vN with the updater installed by hand once, then vN+1 as a bump only; the question must come.
- Emulator taps only by text (uiautomator dump): blind coordinates answered Play Protect wrong once and opened the Pixel 7 row
  (connected to the real phone) once.
- Android asks "Allow from this source" once; without the onResume hook the install waited for the next start (fixed in v50).
- Mac: sign the new copy "Mantra Apps" before swapping, or Accessibility is lost; failures reopen the old copy.
- From now on: MANTRA_MANIFEST modules/update-at-start.md, kits mac-updater / android-updater, skill update-at-start.
