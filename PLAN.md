# vm-chromium: a Chromebook in Oracle Cloud

**The experience (Marko, 2.11.2026):** like a Chromebook: you open the screen and you are on the internet. On
chromium-vm nothing but Chromium: when he connects, Chromium is already there, full screen, his tabs where he left
them. Clients: a Mac app in the Star (folder Mac) called **Chromium Virtual Machine**, and Mantra Remote VNC on the
phone (its ENTER on CHROMIUM-VM).

## The machine (done 2.11.2026)

- Oracle Cloud Frankfurt, VM.Standard.A1.Flex (ARM, 2 OCPU, 12 GB; Always Free allows up to 4 OCPU / 24 GB),
  **Ubuntu 24.04 Minimal aarch64, 200 GB** (fresh, nothing on it), hostname **chromium-vm**.
- Tailscale: **100.102.86.30**, name chromium-vm, Tailscale SSH on (`tailscale ssh ubuntu@chromium-vm`). Public IP
  130.61.181.83, SSH 22 open there (key ~/.ssh/oracle_vm on the Mac; `ssh chromium-vm`).
- OCI CLI on the Mac (~/.oci): instance ocid in ~/.oci/teacher-vm.json, display name chromium-vm.

## Stage 1: the VM shows Chromium and nothing else

1. A graphical session with no desktop: **TigerVNC (Xvnc)** on display :1, a one-window session that starts
   **Chromium** maximised (`--start-maximized --no-first-run --disable-session-crashed-bubble`, restore last
   session), and starts it again if it is closed (a loop in the session script). No panel, no desktop, no icons.
   A tiny window manager only if Chromium needs one for dialogs (e.g. none or `matchbox-window-manager`).
2. **Chromium for arm64 as a .deb**, not the snap if the snap is slow in Xvnc (Ubuntu's `chromium` is a snap; the
   xtradeb PPA or Debian's build are the usual debs). Measure the start time both ways, keep the faster.
3. **Persistent**: a systemd service per user keeps Xvnc + Chromium running across disconnects and reboots; the
   profile in ~/.config/chromium survives everything. Connecting = Chromium as it was.
4. **Only over Tailscale**: Xvnc listens on 100.102.86.30:5901 (not 0.0.0.0), with a VNC password (kept on the VM,
   never in the repo or a chat). Oracle's public ports stay as they are (22 only).
5. **Resize**: the Xvnc session follows the client's size (ExtendedDesktopSize / `-geometry` + RandR), so the Mac
   window and the phone in portrait both fill.
6. Sound later (PulseAudio over the VNC is not standard; note it, do not block on it).
7. The checks: from the Mac, `vncviewer`-style connect shows only Chromium; a reboot of the VM brings it back by
   itself; closing Chromium brings it back; the tabs survive.

## Stage 2: the tool: an agent on the VM + the Mac viewer (Marko, 2.11.2026)

Principle (MANTRA_MANIFEST modules/build-the-tool.md): build the tool once, then every use is fast and cheap.
Two-way, direct, text over pictures, as few credits as possible.

### 2a. `vm-agent` on chromium-vm (first: it gives the fast channel at once)

A small Python server (stdlib only), systemd user service, listening on **100.102.86.30:8890** (Tailscale only),
`X-Mantra-Token` on every request (the token lives on the VM and in ~/Downloads/API/chromium-vm-agent.txt, never in
the repo). Remote door shape: `/health`, `/api` (self-described actions), `POST /api/<action>`.

| action | does | cost |
|---|---|---|
| `clip_get` / `clip_set` | the VM clipboard as text (xclip) | a few bytes |
| `type` / `key` | text or keys into the focused window (xdotool) | a few bytes |
| `put` (multipart / raw) / `get` / `ls` | files into ~/Downloads on the VM (Chrome's download folder) and back | the file only |
| `shot` | a JPEG of the screen, scaled, only when asked | the last resort |
| `tabs` / `open` / `page_text` / `eval` | Chrome through the DevTools protocol (127.0.0.1:9222 on the VM, never exposed) | text |
| `claude_ask` | puts a message into the claude.ai tab (or the Claude extension), sends it, waits until the answer stops growing, returns the answer text | the answer only |

Chrome 136+ refuses `--remote-debugging-port` on the default profile folder, so the session starts Chrome with
`--user-data-dir=$HOME/.config/chromium-vm-chrome` (the profile moved there once) and
`--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222`. Only vm-agent talks to it.

On the Mac: `cvm` (one command for Claude Code and for Marko): `cvm ask "..."`, `cvm text`, `cvm put <file>`,
`cvm clip`, `cvm shot`. Replaces `vmpaste` / `vmcopy` / scp / xwd.

### 2b. The Mac viewer: **Chromium Virtual Machine (Mantra)**

- A Swift app (MANTRA_MANIFEST: Swift only, signed "Mantra Apps", name first, controls as AX buttons, never cut
  text). One window that is the VM's screen: an RFB client in Swift (Mantra Remote's Kotlin RFB is the model),
  ExtendedDesktopSize so the VM follows the window, full screen (⌘F).
- **Free copy and paste both ways** (feature request, Marko, 2.11.2026): Mac → VM on every NSPasteboard change
  (changeCount) as RFB ClientCutText; VM → Mac on ServerCutText. Xvnc 1.13 syncs CLIPBOARD and PRIMARY by itself.
  UTF-8 through the Extended Clipboard pseudo-encoding (0xC0A1E5CE), Latin-1 fallback. Apple's Screen Sharing greys
  its clipboard out against a Linux server; that is why the own viewer exists.
- **Drag and drop**: Mac files dropped on the window go to the VM's ~/Downloads through vm-agent `put`, with a
  progress line; dropped on a page's upload box they are then chosen there.
- **Its own remote door** on 127.0.0.1 (MANTRA_PORTS id `chromium-vm`): the same actions as vm-agent, so the Star,
  Mantra Door and the phone drive it too.
- Tailscale must be on (say so plainly if not).
- A row in the Star, folder **Mac** (STAR_SWIFT rows.json, key `chromiumvm`), registry entries, README/TAKEOVER/LESSONS.

## Stage 3: the phone

- MANTRA_REMOTE v21: CHROMIUM-VM's button says **ENTER ▶** and opens the VM at 100.102.86.30:5901 with the same
  picture and keys (the Mac-only keys — MON, DOCK, LOGIN, ☰ menu — hidden for a Linux machine). Tested on the
  Nothing Phone 2a and the Pixel 7 emulator, portrait.

## Who does what

- **The cloud session "CHROMIUM IN VIRTUAL MACHINE" owns this plan** (Marko, 2.11.2026: "only send it to the cloud.
  The plan"). It writes everything in this repository and, once its environment has the access in README, works on
  the VM itself. What only the Mac can do (the Swift build, the Star row, the phone over adb) it asks of a Mac session
  through the hub (session-link.md), never by itself.

## Rules that apply

Requests word for word into momentaryupdates.md first; whole-number versions; no key in the open; every reply ends
spoken (`langsay`); Marko is the tester and is asked one thing at a time by voice; close-the-session.md at the end.
