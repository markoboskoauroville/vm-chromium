#!/usr/bin/env python3
"""chromium-vm-reaper: stops what is idle and heavy; the dock shows it as a button to start it again.

Marko, 9.11.2026: "Close anything that doesn't run now, and make this automatic in the machine: it just closes it and
puts that application down there in the dock at the bottom of the display, and I can start it again. For now just
close what is idle." Run by chromium-vm-reaper.timer every 2 minutes; every stop is logged with its reason in
~/.cache/chromium-vm/reaper.log (and the journal). Idle time: CVM_REAPER_IDLE_MIN (default 20) from /etc/chromium-vm-reaper.conf.

Reaped (only these; everything else is untouchable by design: YouTube transcriber and its monitor, Xvnc, the dock,
vm-agent, the Gemini worker, Chrome, sshd, tailscale, Claude Code are never in this file):
 * Pixel N container: idle = no use mark (chromium-vm-phone touch, set by pixel7d / pixel7-jobs / the dock / start), no
   job holding the pixel7 lock, and nobody looking at its mirror, for IDLE minutes.
 * Pixel N mirror (scrcpy, 30 fps): looked at = a VNC client is connected AND its window is the front window or the
   keyboard/mouse was used within IDLE minutes while it is mapped. Not looked at for IDLE minutes: mirror stopped.
 * NEVER: claude-desktop, claude (a session works without human input; stopping it could kill a task mid-run).
"""
import fcntl, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.machinery, importlib.util
_l = importlib.machinery.SourceFileLoader('phone', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromium-vm-phone'))
_s = importlib.util.spec_from_loader('phone', _l); phone = importlib.util.module_from_spec(_s); _l.exec_module(phone)

IDLE = float(os.environ.get('CVM_REAPER_IDLE_MIN', '20')) * 60
CACHE = phone.CACHE
STATE = os.path.join(CACHE, 'reaper-state.json')
os.environ.setdefault('DISPLAY', ':1')
NOW = time.time()


def run(*a, t=15):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=t).stdout
    except Exception:
        return ''


def x_idle():
    try:
        from Xlib import display
        from Xlib.ext import screensaver  # noqa: F401
        d = display.Display()
        return d.screen().root.screensaver_query_info().idle / 1000.0
    except Exception:
        return 0.0          # cannot tell: counts as "somebody is there", nothing is stopped because of it


def vnc_client():
    return 'ESTAB' in run('ss', '-tn', 'state', 'established', '( sport = :5901 )')


def front_title():
    try:
        wid = open(os.path.join(CACHE, 'front')).read().strip()
        return run('xdotool', 'getwindowname', wid).strip(), run('xdotool', 'getwindowclassname', wid).strip()
    except Exception:
        return '', ''


def win_mapped(title):
    for wid in run('xdotool', 'search', '--onlyvisible', '--class', 'scrcpy').split():
        if run('xdotool', 'getwindowname', wid).strip() == title:
            return True
    return False


def pixel_lock_held():
    try:
        f = open(os.path.expanduser('~/.cache/pixel7/device.lock'), 'a')
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(f, fcntl.LOCK_UN); return False
        except OSError:
            return True
    except Exception:
        return False


def touch_age(n):
    try:
        return NOW - os.stat(os.path.join(CACHE, f'phone-{n}.touch')).st_mtime
    except OSError:
        return 1e9


def main():
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    idle_x = x_idle(); client = vnc_client(); ftitle, fclass = front_title()
    for n in (1, 2):
        title = f'Pixel {n}'; mirror = phone.unit_active(phone.PH[n]['units'][0]); up = phone.running(n)
        key = f'mirror{n}'
        viewed = mirror and client and win_mapped(title) and (ftitle == title or idle_x < IDLE)
        if viewed or not mirror:
            st[key] = NOW
        st.setdefault(key, NOW)
        if mirror and NOW - st[key] >= IDLE:
            phone.log(f'reaper: Pixel {n} mirror: nobody looking for {int((NOW - st[key]) / 60)} min '
                      f'(vnc client {client}, window mapped {win_mapped(title)}, input idle {int(idle_x / 60)} min)')
            for u in phone.PH[n]['units']:
                if phone.unit_active(u):
                    subprocess.run(['sudo', '-n', 'systemctl', 'stop', u]); phone.log(f'STOP {u}: idle mirror')
            mirror = False
        busy = (n == 1 and pixel_lock_held())
        if busy or viewed or mirror:                  # a mirror still up (looked at) or a job running = in use
            phone.touch(n)
        if up and not mirror and not busy and touch_age(n) >= IDLE:
            phone.stop(n, f'idle: no job/adb use, no viewer for {int(touch_age(n) / 60)} min')
    # Claude app / Claude Code (claude-desktop, claude): NEVER stopped (Marko/main 9.11.2026): a Claude session works with no input by design.
    json.dump(st, open(STATE, 'w'))


if __name__ == '__main__':
    main()
