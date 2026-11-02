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
- Install on the VM: copy the repo over (`tar | ssh`, the repo is private), `sudo ./stage1/setup.sh && sudo ./agent/install.sh`.

## Many sessions at once (2.11.2026): vm-router + `vmr`

Sessions and jobs go through **vm-router** on the Mac (127.0.0.1:8891): each session its own tabs, Google account
(/u/N) and Downloads folder, clipboard / type / key one at a time, Gemini image requests paced per account, an event
log. `vmr -s NAME …`, or `VMR_NAME=NAME cvm …`; the app **VM Router (Mantra)** (Star, folder Mac) shows it.
Details: [router/README.md](router/README.md).
