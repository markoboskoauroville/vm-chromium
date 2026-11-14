---
name: update-this-machine
description: How to change, fix, install, upgrade or check the Linux VM chromium-vm itself, from a session running on it - its desktop (dock, status bar, windows), services, vm-agent, Chrome, the Claude app, packages, Tailscale. Use whenever Marko asks to modify, rename, fix, update or set up something on "this machine". Edit in the repo, deploy only the changed piece, verify on the screen, commit and push. Read the skill this-machine first.
---

# Updating this machine from here

Marko, 7.11.2026: *"From now on, we are updating this machine from here. So in the same repository, please add skills
to update this machine. Whatever is needed."* Work happens on this VM (skill `this-machine`); this skill is how the
VM itself gets changed.

## 0. Where things are

| What | Where |
|---|---|
| The source of truth | `~/vm-chromium-git` = github.com/markoboskoauroville/vm-chromium (private). Edit only here. |
| Old copies, no git | `~/vm-chromium`, `~/vmc-deploy`: do not edit, do not deploy from them. |
| Installed programs | `/usr/local/lib/chromium-vm/` (copied by the install scripts, not linked) |
| Services | `/etc/systemd/system/chromium-vm-*.service`, `pixel7d`, `pixel7-jobs` (from `~/vm-android`) |
| The screen | Xvnc display `:1` (1512×916 on 7.11.2026, it follows the Mac window), openbox |
| Chrome profile | `~/.config/chromium-vm-chrome`, DevTools 127.0.0.1:9222 |
| Marko's words | `momentaryupdates.md` (each request saved first, then a Status line) |
| History / handover | `TAKEOVER.md`, `LESSONS.md`, `README.md` |

`sudo -n` works for user `ubuntu` (no password).

## 0b. Services (14.11.2026)

The VM boots with the core only. Every program is a vmctl service: `vmctl list`, `vmctl start|stop NAME` (registry
/etc/chromium-vm/services.json, source tools/vmctl). Chrome is its own unit `chromium-vm-chrome` (no longer inside
chromium-vm-session, which is openbox only). Never enable an optional unit at boot; add a new program to services.json.

## 1. The order of work

1. **Save the request first** in `momentaryupdates.md`: Marko's words as a `>` quote, then `**Status:** saved first.`
2. `cd ~/vm-chromium-git && git pull --rebase origin main` (other sessions push too; a push without it is rejected).
3. Check that the installed file is the repo's file before editing (`cmp repo-file /usr/local/lib/chromium-vm/...`).
   If they differ, someone changed the VM by hand: stop and show Marko the diff.
4. Edit in the repo. Check it: `python3 -m py_compile file.py`, `bash -n script`.
5. **Deploy only the changed piece** (table in §2), not a whole install script.
6. **Verify on the real machine**: `systemctl is-active <service>`, `journalctl -u <service> --since "1 min ago"`
   for errors, and a screenshot for anything visible (§4). Look at the screenshot before saying it is done.
7. Commit (a message saying what and Marko's date), push. Add a Status line under his request in
   `momentaryupdates.md`; README / TAKEOVER / LESSONS when the change matters to the next session.
8. A new lesson about working here goes into the skill `this-machine` or this skill, in the same push.

## 2. What to run for each part

| Changed file (repo) | Deploy | Restart |
|---|---|---|
| `desktop/chromium-vm-dock.py` (dock, Super+Tab) | `sudo install -m 755 desktop/chromium-vm-dock.py /usr/local/lib/chromium-vm/` | `sudo systemctl restart chromium-vm-dock` |
| `desktop/chromium-vm-pixel7-bar.py` | same, that file | `chromium-vm-pixel7-bar` |
| `desktop/chromium-vm-pixel7` (a phone's window; arg 1 = Pixel 1, 2 = Pixel 2) | `sudo install -m 755 desktop/chromium-vm-pixel7 /usr/local/lib/chromium-vm/` | `chromium-vm-pixel7`, `chromium-vm-pixel7b` |
| the phones themselves (vm-android `pixel7/run.sh`, clone `~/vm-android-git`, copy used on the VM `~/vm-android`) | copy run.sh to `~/vm-android/pixel7/`, **read it before running it** | `sudo ~/vm-android/pixel7/run.sh` (Pixel 1) or `sudo NAME=pixel7b PORT=5556 ~/vm-android/pixel7/run.sh` (Pixel 2): this recreates that phone's container (its /data stays) |
| `desktop/chromium-vm-snap` (layouts, refit) | `sudo install -m 755 desktop/chromium-vm-snap /usr/local/lib/chromium-vm/` | `chromium-vm-refit` |
| `statusbar/chromium-vm-statusbar.py` | `sudo install -m 755 statusbar/chromium-vm-statusbar.py /usr/local/lib/chromium-vm/` | `chromium-vm-statusbar` |
| `agent/vm-agent.py` | `sudo install -m 755 agent/vm-agent.py /usr/local/lib/chromium-vm/vm-agent.py` | `chromium-vm-agent` (stops running Gemini scripts that use :8890: check first) |
| `desktop/config/openbox-rc.xml` | `sudo install -m 644 desktop/config/openbox-rc.xml /usr/local/lib/chromium-vm/` | `DISPLAY=:1 openbox --reconfigure` (no restart) |
| `workers/gemini-images/*` | see `workers/README.md` | `chromium-vm-worker-gemini` (only if Marko wants it running) |
| a `*.service` file | `sudo install -m 644 X.service /etc/systemd/system/ && sudo systemctl daemon-reload` | that service |
| `desktop/chromium-vm-claude-app`, `desktop/chromium-vm-claude-code`, `stage1/bin/*` | install the file only | **not by yourself, see §3** |

Use `install`, not `cp`, so the mode is right. Before a restart that a running job depends on, say so.

## 3. Restarts that end sessions or work: ask Marko first

- **`chromium-vm-claude-app`**: this session (Claude app → Code tab) runs inside it. Restarting it, killing
  `claude-desktop`, or upgrading the `claude-desktop` package ends this conversation in the middle. Checked
  7.11.2026: the session's process tree goes `claude` → `claude-desktop` → `chromium-vm-claude-app` (PID 1003).
- **`chromium-vm-claude-code`**: ends the Claude Code session in tmux `claude` on screen 1.
- **`chromium-vm-session`**: restarts Chrome (open Gemini tabs, Claude in Chrome's tab group) and openbox.
- **`chromium-vm-xvnc`**: kills every program on the screen, this session's app included.
- **Whole install scripts** (`stage1/setup.sh`, `desktop/install.sh`, `agent/install.sh`): they restart several of
  the above. Do not run them for a small change.
- **Reboot**, `apt upgrade` of google-chrome-stable / claude-desktop / the kernel: ask, say what will close, and
  write the TAKEOVER line first, so the next session can continue.

To apply a change to one of these, install the file, then tell Marko what must restart and let him say when (or he
restarts it himself from the dock or the status bar's power button).

## 4. Checking the screen

```bash
export DISPLAY=:1
eval $(xdotool getmouselocation --shell)          # remember where Marko's pointer was
xdotool mousemove 756 915; sleep 1.5              # pointer to the bottom edge: the dock slides up
import -window root /path/in/scratchpad/screen.png
xdotool mousemove $X $Y                           # give the pointer back
```

Crop the part that changed (`convert ... -gravity South -crop 100%x30%+0+0`) and look at it. Marko may be watching
the screen through the viewer: keep pointer moves short and put the pointer back.

## 5. System upkeep

- Disk / memory / load: `df -h /`, `free -h`, `uptime` (the status bar shows them too).
- Packages: `sudo apt-get update -q && apt list --upgradable` first; tell Marko what would change. Upgrades of
  google-chrome-stable or claude-desktop follow §3.
- Tailscale: `tailscale status`; the VM is 100.102.86.30. Never change Tailscale settings (`tailscale up`, ACLs)
  without Marko: it is the only way in.
- Failing services: `systemctl --failed --no-pager`, then `journalctl -u <unit> -n 50`.

## 5b. Lessons

- 7.11.2026: a `Write` was refused (file not read first) and the next command copied the OLD run.sh onto the VM
  and ran it with sudo: Pixel 1 came back on the image without Play Store, fixed minutes later. Before running a
  script with sudo, check its content (`grep` the line you changed) in the same command.
- 7.11.2026: with two phones and two scrcpy windows the 2 CPU cores run near 100%; the dock then needs a few seconds
  to slide up. Not a bug.

## 6. Done here (keep adding)

- 7.11.2026: dock label **"Claude" → "Claude app"** (Marko: when the app is meant, it is called "Claude app"),
  also in the layout names; names that are too wide for their slot or tile now shrink to fit. Deployed: dock only.
- 7.11.2026: **two Pixel 7 emulators**: Pixel 1 (pixel7, :5555) and Pixel 2 (pixel7b, :5556, fresh), windows "Pixel 1" /
  "Pixel 2" (told apart by title), dock tiles, Pixel bar on the phone in front. Layout **Claude app | Pixel 1 | Pixel 2**
  (claude-pixels) replaced Claude app | Claude Code | Pixel 7; phone windows have the phone's exact shape, no bars.
- 7.11.2026: layout **Claude Code | Pixel 1 | Pixel 2** (code-pixels), the copy of claude-pixels with Claude Code. Deployed: dock + snap.
