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
