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
