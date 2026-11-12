#!/usr/bin/env python3
"""chromium-vm Pixel 7 bar: a small control strip (one PORTRAIT/LANDSCAPE toggle | POWER ▾ with a menu) over the Pixel 7 screen (screen 4), only while it is in front.

Marko, 5.11.2026: "I want to have some overlay on the screen just to control this emulator: change orientation and
reboot it." PORTRAIT | LANDSCAPE (wm user-rotation lock 0/1; apps turn, the Pixel's home screen stays upright like on
a real phone) and REBOOT -> REBOOT? YES | NO (docker restart pixel7; the Pixel 7 window comes back by itself).
12.11.2026 (Marko: "Portrait, landscape. Reboot, reboot, shutdown. This is missing."): the strip now has three power
actions, each asking YES | NO first: REBOOT (Android only: `stop` / `start` of the framework, the container keeps running,
about 20 s, like a phone restart), HARD REBOOT (docker restart of the container, as the old REBOOT did) and SHUTDOWN
(chromium-vm-phone stop N: the mirror and the container stop, the dock's "Pixel N ▶" starts it again). SHUTDOWN is started
detached with systemd-run --user, because stopping the phone also stops this bar's own service.
7.11.2026 (Marko: two emulators, Pixel 1 and Pixel 2): the bar works on the phone whose window is in front (told apart
by the window title) and sits at that window's top-right corner, since the phones can now share the screen.
"""
import os, subprocess, threading
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from Xlib import display as xdisplay

GLib.set_prgname('vm-pixel7-bar')
PHONES = {'Pixel 1': ('127.0.0.1:5555', 'pixel7'), 'Pixel 2': ('127.0.0.1:5556', 'pixel7b')}   # title: adb serial, container
XD = xdisplay.Display(); ROOT = XD.screen().root
A_ACTIVE = XD.intern_atom('_NET_ACTIVE_WINDOW')
A_NAME, A_UTF8 = XD.intern_atom('_NET_WM_NAME'), XD.intern_atom('UTF8_STRING')
CSS = b"""
window { background: rgba(20,20,22,0.82); border-radius: 10px; }
button { background: none; border: none; box-shadow: none; color: #9e9e9e; font: 600 11px sans-serif; padding: 2px 4px; }
button:hover { color: #ffffff; text-decoration: underline; }
button.lit { color: #5cbf73; }
button.warn { color: #ff9f0a; }
label { color: #555; font: 11px sans-serif; }
menu, .menu { background: rgba(28,28,30,0.96); border-radius: 8px; }
menuitem { color: #d0d0d0; font: 600 11px sans-serif; padding: 5px 10px; }
menuitem:hover { background: #3a3a3c; color: #ffffff; }
label.note { color: #ff9f0a; font: 600 11px sans-serif; }
"""

def pixel_in_front():
    """(title, window) of the phone window in front, or None"""
    try:
        wid = ROOT.get_full_property(A_ACTIVE, 0).value[0]
        w = XD.create_resource_object('window', wid)
        cls = w.get_wm_class()
        if not cls or cls[1].lower() != 'scrcpy': return None
        p = w.get_full_property(A_NAME, A_UTF8)
        t = (p.value.decode('utf-8', 'replace') if isinstance(p.value, bytes) else str(p.value)) if p else ''
        return (t if t in PHONES else 'Pixel 1'), w
    except Exception:
        return None

def run(cmd, timeout=15):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception: return ''

class Bar(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_app_paintable(True)
        scr = self.get_screen(); vis = scr.get_rgba_visual()
        if vis: self.set_visual(vis)
        prov = Gtk.CssProvider(); prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(scr, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.box = Gtk.Box(spacing=0); self.box.set_margin_start(6); self.box.set_margin_end(6)
        self.box.set_margin_top(4); self.box.set_margin_bottom(4); self.add(self.box)
        # 12.11.2026 (Marko: "portrait and landscape can be toggled"): ONE button shows the current orientation, a click flips it
        self.turn = self.button('PORTRAIT', self.toggle_rotation)
        self.gap = Gtk.Label(label=' '); self.box.pack_start(self.gap, False, False, 0)
        self.orient = [self.turn, self.gap]
        # 12.11.2026 (Marko: "group items so the additional menu is opening up"): the three power actions sit under one POWER button
        self.power = self.button('POWER ▾', self.open_menu); self.acts = [self.power]
        self.menu = Gtk.Menu()
        for what, text in (('soft', 'REBOOT · Android'), ('hard', 'HARD REBOOT · phone'), ('off', 'SHUTDOWN · stop')):
            it = Gtk.MenuItem(label=text); it.connect('activate', lambda _w, w=what: self.ask(w)); self.menu.append(it)
        self.menu.show_all()
        self.q = Gtk.Label(label=''); self.q.get_style_context().add_class('note'); self.box.pack_start(self.q, False, False, 0)
        self.yes = self.button('YES', self.confirm); self.yes.get_style_context().add_class('warn')
        self.sep = Gtk.Label(label='|'); self.box.pack_start(self.sep, False, False, 0)
        self.no = self.button('NO', self.cancel)
        self.pending = None
        self.note = Gtk.Label(label=''); self.note.get_style_context().add_class('note'); self.box.pack_start(self.note, False, False, 0)
        self.rot = {}; self.busy = False; self.phone = 'Pixel 1'; self.win = None
        self.show_all(); self.cancel(); self.note.hide(); self.hide()
        self.mark()
        GLib.timeout_add(300, self.poll)

    def button(self, t, cb):
        b = Gtk.Button(label=t); b.connect('clicked', cb); b.set_relief(Gtk.ReliefStyle.NONE)
        self.box.pack_start(b, False, False, 0); return b

    def mark(self):
        r = self.rot.get(self.phone, 0)
        self.turn.set_label('LANDSCAPE' if r == 1 else 'PORTRAIT')
        c = self.turn.get_style_context(); c.add_class('lit') if r == 1 else c.remove_class('lit')

    def toggle_rotation(self, *_):
        self.rotate(1 - self.rot.get(self.phone, 0))

    def place(self):
        # 5.11.2026: GTK kept the old screen width after the Mac window was zoomed (the bar cut on the right): ask X itself
        try: sw = ROOT.get_geometry().width
        except Exception: sw = Gdk.Screen.get_default().get_width()
        w = max(self.get_size()[0], self.get_preferred_width()[1])
        try:   # the top-right corner of the phone's own window (7.11.2026: two phones can be side by side)
            g = self.win.get_geometry(); t = self.win.translate_coords(ROOT, 0, 0)
            x, y = -t.x + g.width - w - 14, -t.y + 12
            if g.width < w + 28: x = -t.x + (g.width - w) // 2   # a narrow window: centred over it, never off the screen
            self.move(max(0, min(x, sw - w)), max(0, y))
        except Exception:
            self.move(sw - w - 14, 12)

    def poll(self):
        front = pixel_in_front()
        if front and not self.busy:
            if front[0] != self.phone: self.phone = front[0]; self.mark(); self.cancel()
            self.win = front[1]
        show = bool(front) or self.busy
        if show and not self.get_visible(): self.show(); self.place()
        elif not show and self.get_visible(): self.hide(); self.cancel()
        if self.get_visible(): self.place(); self.get_window() and self.get_window().raise_()
        return True

    def rotate(self, r):
        self.rot[self.phone] = r; self.mark(); serial = PHONES[self.phone][0]
        threading.Thread(target=lambda: run(['adb', '-s', serial, 'shell', 'wm', 'user-rotation', 'lock', str(r)]), daemon=True).start()

    def open_menu(self, *_):
        self.menu.popup_at_widget(self.power, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)   # right edges level: the menu stays inside the phone window

    NAMES = {'soft': 'REBOOT', 'hard': 'HARD REBOOT', 'off': 'SHUTDOWN'}

    def ask(self, what):
        self.pending = what
        for b in self.acts + self.orient: b.hide()
        self.q.set_text(f'{self.NAMES[what]} {self.phone[-1]}?'); self.q.show(); self.yes.show(); self.sep.show(); self.no.show(); self.place()

    def cancel(self, *_):
        self.pending = None
        self.q.hide(); self.yes.hide(); self.sep.hide(); self.no.hide()
        for b in self.orient + self.acts: b.show()
        self.place()

    def confirm(self, *_):
        what = self.pending; self.cancel()
        self.busy = True
        for b in self.acts + self.orient: b.hide()
        self.note.set_text({'soft': f'rebooting {self.phone[-1]}…', 'hard': f'hard reboot {self.phone[-1]}…', 'off': f'shutdown {self.phone[-1]}…'}[what]); self.note.show()
        serial, box = PHONES[self.phone]; n = 1 if box == 'pixel7' else 2; phone = self.phone

        def wait_boot(min_s):
            GLib.usleep(min_s * 1_000_000)
            for _ in range(60):
                run(['adb', 'connect', serial], 5)
                if run(['adb', '-s', serial, 'shell', 'getprop', 'sys.boot_completed'], 5) == '1' and run(['adb', '-s', serial, 'shell', 'pidof', 'system_server'], 5): break
                GLib.usleep(2_000_000)

        def work():
            if what == 'soft':
                run(['adb', '-s', serial, 'shell', 'stop'], 20); GLib.usleep(3_000_000)
                run(['adb', '-s', serial, 'shell', 'start'], 20); wait_boot(8)
            elif what == 'hard':
                run(['docker', 'restart', box], timeout=90); wait_boot(0)
            else:   # outside this service's cgroup: `chromium-vm-phone stop` stops this very bar
                env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/%d' % os.getuid())
                subprocess.run(['systemd-run', '--user', '--no-block', '/usr/local/lib/chromium-vm/chromium-vm-phone', 'stop', str(n), 'shutdown from the bar'], env=env, capture_output=True, timeout=20)
                GLib.usleep(15_000_000)
            GLib.idle_add(self.done, what)
        threading.Thread(target=work, daemon=True).start()

    def done(self, what):
        self.busy = False
        if what == 'hard': self.rot[self.phone] = 0
        self.mark(); self.note.hide()
        for b in self.orient + self.acts: b.show()
        self.place(); return False

if __name__ == '__main__':
    Bar(); Gtk.main()
