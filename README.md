# vm-chromium

A Chromebook in Oracle Cloud: chromium-vm (Ubuntu 24.04 Minimal, ARM, 200 GB, Tailscale 100.102.86.30) runs only
Chromium, reached by VNC over Tailscale from the Mac app **Chromium Virtual Machine (Mantra)** and from Mantra Remote
VNC on the phone. The plan is [PLAN.md](PLAN.md); Marko's words are in [momentaryupdates.md](momentaryupdates.md).

## For a cloud session to work on the VM itself

A cloud session is not on the tailnet. To let it reach chromium-vm, Marko gives its environment:
1. **Network access** that allows outbound connections (the environment's network setting).
2. **A Tailscale auth key** as an environment secret (`TS_AUTHKEY`; Tailscale admin → Settings → Keys → Generate auth
   key, ephemeral, reusable, expiring), so the session's container joins the tailnet in userspace mode and uses
   Tailscale SSH to chromium-vm. Never pasted into a chat.
3. **This repository** in the environment's GitHub access.
Without these, the cloud session writes the files here and the local session on the Mac runs them.

## The fast channel (2.11.2026): vm-agent + `cvm`

Built by the principle in MANTRA_MANIFEST modules/build-the-tool.md: no screenshots, no typing by hand.

- **vm-agent** on the VM (`agent/`, systemd `chromium-vm-agent`): 100.102.86.30:8890, Tailscale only, token in
  `X-Mantra-Token` (VM: ~/.config/chromium-vm/agent-token; Mac: ~/Downloads/API/chromium-vm-agent.txt).
  `/health`, `/api`, `POST /api/<action>`, `PUT|GET /files/<name>` (the VM's ~/Downloads).
  Chrome runs with its profile in ~/.config/chromium-vm-chrome and DevTools on 127.0.0.1:9222 (VM only).
- **`cvm`** on the Mac (`mac/cvm` → ~/.local/bin/cvm): `cvm new` (fresh claude.ai chat, becomes cvm's tab),
  `cvm ask "..."` (answer as text, ~7 s), `cvm paste` / `cvm type` / `cvm key`, `cvm clip` / `cvm clip set`,
  `cvm put` / `cvm get` / `cvm ls`, `cvm tabs` / `cvm open` / `cvm text` / `cvm eval`, `cvm shot` (last resort).
- Install on the VM: copy the repo over (`tar | ssh`, the repo is private), `sudo ./stage1/setup.sh && sudo ./agent/install.sh && sudo ./desktop/install.sh`.

## Many sessions at once (2.11.2026): vm-router + `vmr`

Sessions and jobs go through **vm-router** on the Mac (127.0.0.1:8891): each session its own tabs, Google account
(/u/N) and Downloads folder, clipboard / type / key one at a time, Gemini image requests paced per account, an event
log. `vmr -s NAME …`, or `VMR_NAME=NAME cvm …`; the app **VM Router (Mantra)** (Star, folder Mac) shows it.
Details: [router/README.md](router/README.md).

## Also on the VM (2.11.2026)

- **Google Chrome 156 (arm64)**, not Chromium: profile sign-in and Sync. Profiles: "Your Chromium" (auroville.community)
  and "Marko" ([address removed]). Dark everywhere (`--force-dark-mode`, `WebContentsForceDark`, Mode Dark).
- **Downloads → Google Drive only**: every finished download (subfolders too) goes to Drive "Chromium Downloads/…"
  and is deleted from the VM (vm-agent). Nothing comes to the Mac by itself (SIM).
- **Status bar** (statusbar/, service chromium-vm-statusbar): one line at the bottom, 50% see-through band, mono,
  right-aligned: download (green) upload (red) | SSD free | CPU | RAM | UP; what is moving, in green, from the left.
  Click on the speeds: a speed test (5 s). Click elsewhere: settings.
- **Workers** (workers/): programs that run on their own. First: gemini-images (batch on Drive, RESULTS.txt beside
  the pictures, sleeps until Gemini's limit resets).
- **The Mac viewer**: Chromium Virtual Machine (Mantra) v10 (viewer/), Star folder Mac. No title bar; one gear at the
  bottom-right, after the status line's power button: F1 (Speechify) and F2 (Voice to Text) each MAC | VM (MAC = never
  sent to the VM; dictation lands on the VM through vm-agent `paste_text`), FULL SCREEN | RECONNECT, CLOSE WINDOW | QUIT.
  Needs Accessibility (amber PERMISSIONS above the gear while missing).
- **Power**: the status line's ⏻ (after UP) → REBOOT | CANCEL.

## The desktop (2.11.2026): three programs, the dock, Rectangle's keys

Marko: "three screens, and I'm switching between them" / "use the same principle as with jumping displays at the
bottom: give me three more displays with different layout" / windows side by side with Rectangle's keys. `desktop/`,
installed with `sudo ./desktop/install.sh`; services chromium-vm-claude-code, chromium-vm-claude-app, chromium-vm-dock.

- **Window manager: openbox** (desktop/config/openbox-rc.xml, started by chromium-vm-session; matchbox only as a
  fallback). No title bars, every window opens maximized, the bottom 22 px stay the status bar's.
- **Claude Code**: xfce4-terminal (JetBrains Mono 13, dark) with tmux session `claude` running ~/.local/bin/claude.
- **Claude**: Anthropic's official **Claude Desktop for Linux (beta, arm64)**, apt repo downloads.claude.ai, package
  claude-desktop 4.4212.0, software rendering. Its sign-in is kept in a plain gnome-keyring "login" keyring.
- **Chrome**: the session's Google Chrome (profile ~/.config/chromium-vm-chrome, DevTools for vm-agent). It is also
  the VM's default browser (chromium-vm-chrome.desktop), so sign-in links of the other programs open there.
- **The dock**: pointer at the bottom edge → it slides up above the status bar: three live screens (Claude Code |
  Claude | Chrome, 3 refreshes a second while shown; click = that program to the front) and, after a divider, three
  layout displays (click = all programs arranged that way): **Halves** (Claude Code | Chrome), **Thirds** (Claude
  Code | Claude | Chrome), **Chrome + 2** (Chrome two thirds, Claude Code top right, Claude bottom right).

| Mac key (through the viewer v5) | arrives on the VM as | does |
|---|---|---|
| ⌥Tab (since viewer v26, 5.11.2026; ⌘Tab stays on the Mac) | Super+Tab | next program (Claude Code → Claude → Chrome), the dock peeks; the ONLY switching key |
| ⌃⌥← / ⌃⌥→ | Ctrl+Alt+Left / Right | left / right half |
| ⌃⌥↑ / ⌃⌥↓ | Ctrl+Alt+Up / Down | top / bottom half |
| ⌃⌥Return | Ctrl+Alt+Return | maximize |
| ⌃⌥C | Ctrl+Alt+C | center |
| ⌃⌥U / I / J / K | Ctrl+Alt+U / I / J / K | top-left / top-right / bottom-left / bottom-right quarter |
| ⌃⌥D / F / G | Ctrl+Alt+D / F / G | first / center / last third |
| ⌃⌥E / T | Ctrl+Alt+E / T | first / last two thirds |
| ⌃⌥⌫ | Ctrl+Alt+BackSpace | restore the place before the first snap |

Not bound on purpose: Alt+Tab and Shift+Tab (Marko: only Command-Tab; Shift+Tab is needed inside the programs,
Claude Code uses it for its modes), and none of matchbox's/openbox's default keys. The snaps run
`/usr/local/lib/chromium-vm/chromium-vm-snap ACTION` (also `layout halves|thirds|big`), usable over ssh too.
