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
