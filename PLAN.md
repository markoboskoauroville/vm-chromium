# CHROMIUM_VM: a Chromebook in Oracle Cloud

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

## Stage 2: the Mac client in the Star

- **Chromium Virtual Machine (Mantra)**, a Swift app (MANTRA_MANIFEST: Swift only, signed "Mantra Apps", name first,
  controls as AX buttons, never cut text, numbered workflow only where there are steps).
- v1: one window that is the VM's screen (a VNC client in Swift; Mantra Remote's Kotlin RFB code in
  MANTRA_REMOTE is the model) with full screen (⌘F) and ✕; Tailscale must be on (say so if not).
  If a first working step is wanted the same day: v1 may open macOS Screen Sharing at vnc://100.102.86.30:5901 while
  the own viewer is built, said plainly.
- A row in the Star, folder **Mac** (STAR_SWIFT rows.json, key `chromiumvm`), registry entries, README/TAKEOVER/LESSONS.

## Stage 3: the phone

- MANTRA_REMOTE v21: CHROMIUM-VM's button says **ENTER ▶** and opens the VM at 100.102.86.30:5901 with the same
  picture and keys (the Mac-only keys — MON, DOCK, LOGIN, ☰ menu — hidden for a Linux machine). Tested on the
  Nothing Phone 2a and the Pixel 7 emulator, portrait.

## Who does what

- **The local session on the Mac** ("chromium vm machine at oracle cloud", iTerm): everything that needs the Mac or
  the tailnet: SSH to the VM, the VNC checks, the Swift app, the Star row, the phone over adb, screenshots.
- **The cloud session** ("CHROMIUM IN VIRTUAL MACHINE"): the scripts and files in this repository (the VM setup
  script, the systemd units, the session script, the Swift sources, the Kotlin change), reviewed and run by the local
  session. It reaches the VM itself only when Marko has given its environment the access (see README).

## Rules that apply

Requests word for word into momentaryupdates.md first; whole-number versions; no key in the open; every reply ends
spoken (`langsay`); Marko is the tester and is asked one thing at a time by voice; close-the-session.md at the end.
