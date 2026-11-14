# vmctl: chromium-vm's services

Marko, 14.11.2026: *"reboot machine and only thing which is running is connection keeper. And all other services are
optional ... on the gear icon I will have each program and we now call the program services ... which can also be enabled
remotely by any cloud application if it needs some kind of service and then it can also close it ... build better API,
Python API for virtual machine control."*

## The idea

- **Core** runs from boot and is locked: ckbond (Connection Keeper relay :443), Tailscale, SSH, Xvnc :1, the desktop
  (openbox only), the status bar, vm-agent :8890 (the viewer's clipboard and paste), vmctl itself, Queen, the Oracle agents.
- **Every other program is a service**: off at boot, started by hand (the gear in Mantra Remote Viewing, `vmctl`) or by a
  program (the API, with a lease), and stopped the same way.
- One registry: `/etc/chromium-vm/services.json` (source `services.json` here). Fields: `name`, `short` (≤ 8 characters,
  the name on the status bar and in the gear), `title`, `kind` (`systemd` | `user` | `docker`), `units` / `containers`,
  `deps`, `core`, `probe` (a shell test that the program is really up), `start` / `gui_start` / `stop` (commands for a
  docker service), `bar: false` (a core service the status bar names only when it is down), `idle_stop_minutes` (optional).

## On the VM

```
vmctl list                      ● running  ○ stopped, CORE marked
vmctl start chrome              (deps first; --gui = the gear's start, e.g. a phone with its mirror)
vmctl stop chrome               (deps nobody needs any more stop too; core refuses)
vmctl lease pixel1 30 my-job    start + hold 30 min; stops when the last lease ends, if a lease started it
vmctl leases | release ID | renew ID MIN | gc | log
```

Log of every start/stop: `~/.cache/chromium-vm/vmctl.log`. Leases and the by-hand marks: `~/.local/state/vmctl/state.json`
(survive a restart of the API). Snapshot every 5 s for the status bar: `~/.cache/chromium-vm/vmctl-status.json`.

## The API

`http://100.102.86.30:8896` (the Tailscale address only), service `chromium-vm-vmctl`. Token: header `X-Mantra-Token`
(or `Authorization: Bearer`), file `~/.config/chromium-vm/vmctl-token` on the VM, copy on the Mac in
`~/Downloads/API/chromium-vm-vmctl.txt`. Never logged, never printed.

| Call | |
|---|---|
| `GET /health` | no token |
| `GET /services` | `{services: [{name, short, title, kind, core, running, manual, deps, leases}]}` |
| `GET /services/NAME` | one |
| `POST /services/NAME/start` · `/stop` · `/restart` | body `{"who": "my-app", "gui": false}`; core stop = 403 |
| `POST /services/NAME/lease` | body `{"minutes": 30, "who": "my-app"}` → `{lease: {id, service, until}}` |
| `GET /leases` · `POST /leases/ID/release` · `POST /leases/ID/renew {"minutes": N}` · `DELETE /leases/ID` | |
| `GET /log` | the last 100 lines |

A start returns when the service is up (a Pixel ~30-40 s, Firefox ~15-35 s, Chrome < 1 s): use a long timeout.

## The client library

`vmctl_client.py`, one file, standard library only. On the Mac it is also the command `vmctl` (link in ~/.local/bin).

```python
import sys; sys.path.insert(0, '/path/to/vm-chromium/tools/vmctl')
from vmctl_client import VM
vm = VM(who='my-app')                # VMCTL_URL / VMCTL_TOKEN / VMCTL_TOKEN_FILE override the defaults
with vm.using('pixel1', minutes=30): # started if needed, released at the end (and stopped if the lease started it)
    ...
vm.start('chrome'); vm.running('chrome'); vm.stop('chrome')
```

A cloud session without Tailscale cannot reach the API; the Pixel job mailbox (vm-android-jobs) needs `pixel-door`
running (off at boot: start it, or ask Marko to keep it on).

## Priority: Connection Keeper first

Marko, 14.11.2026: *"since machine is very weak, we always need to find solutions and tactics and ways so connection
keeper and my VPN protection is at the maximum, the process has maximum priority"*.

- `vmcore.slice` (top level, CPUWeight 10000, IOWeight 10000, MemoryMin 256M): ckbond and tailscaled. Under contention
  the relay gets the CPU first; the rest of the machine shares what is left.
- ckbond drop-in: Nice -15, IO realtime 2, OOMScoreAdjust -1000 (never killed for memory), MemoryMin 128M,
  LimitNOFILE 1048576, Restart always after 1 s. tailscaled: CPUWeight 5000, Nice -10, OOM -900.
- `vmsvc.slice` (CPUWeight 50, IOWeight 50, MemoryHigh 9.5G): every optional system service, docker's containers
  (`/etc/docker/daemon.json` cgroup-parent) and, in the user manager, Firefox, Brave, Macro, the YouTube jobs.
  Optional units also get OOMScoreAdjust 500: the kernel kills them first.
- Containers: restart policy `no`, cpu-shares 128.
- Slice names have no dash: `vm-core.slice` would be a child of `vm.slice` (systemd reads a dash as a level).

## Install

`sudo tools/vmctl/install.sh` from a checkout (it installs vmctl, the registry, the slices and drop-ins, the Chrome unit,
the user units, enables the core and disables the rest at boot; it stops nothing). Changes to ckbond's drop-in take
effect at the next start of ckbond, i.e. a reboot: ckbond is never restarted for it.
