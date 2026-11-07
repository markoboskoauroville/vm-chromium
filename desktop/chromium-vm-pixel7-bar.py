#!/usr/bin/env python3
"""chromium-vm Pixel 7 bar: a small control strip over the Pixel 7 screen (screen 4), only while it is in front.

Marko, 5.11.2026: "I want to have some overlay on the screen just to control this emulator: change orientation and
reboot it." PORTRAIT | LANDSCAPE (wm user-rotation lock 0/1; apps turn, the Pixel's home screen stays upright like on
a real phone) and REBOOT -> REBOOT? YES | NO (docker restart pixel7; the Pixel 7 window comes back by itself).
7.11.2026 (Marko: two emulators, Pixel 1 and Pixel 2): the bar works on the phone whose window is in front (told apart
by the window title) and sits at that window's top-right corner, since the phones can now share the screen.
"""
import subprocess, threading
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
button { background: none; border: none; box-shadow: none; color: #9e9e9e; font: 600 12px sans-serif; padding: 2px 6px; }
button:hover { color: #ffffff; text-decoration: underline; }
button.lit { color: #5cbf73; }
button.warn { color: #ff9f0a; }
label { color: #555; font: 12px sans-serif; }
label.note { color: #ff9f0a; font: 600 12px sans-serif; }
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
        self.box = Gtk.Box(spacing=2); self.box.set_margin_start(8); self.box.set_margin_end(8)
        self.box.set_margin_top(4); self.box.set_margin_bottom(4); self.add(self.box)
        self.portrait = self.button('PORTRAIT', lambda *_: self.rotate(0))
        self.box.pack_start(Gtk.Label(label='|'), False, False, 0)
        self.landscape = self.button('LANDSCAPE', lambda *_: self.rotate(1))
        self.box.pack_start(Gtk.Label(label='   '), False, False, 0)
        self.reboot = self.button('REBOOT', self.ask)
        self.yes = self.button('YES', self.do_reboot); self.yes.get_style_context().add_class('warn')
        self.sep = Gtk.Label(label='|'); self.box.pack_start(self.sep, False, False, 0)
        self.no = self.button('NO', self.cancel)
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
        for b, on in ((self.portrait, r == 0), (self.landscape, r == 1)):
            c = b.get_style_context(); c.add_class('lit') if on else c.remove_class('lit')

    def place(self):
        # 5.11.2026: GTK kept the old screen width after the Mac window was zoomed (the bar cut on the right): ask X itself
        try: sw = ROOT.get_geometry().width
        except Exception: sw = Gdk.Screen.get_default().get_width()
        w = max(self.get_size()[0], self.get_preferred_width()[1])
        try:   # the top-right corner of the phone's own window (7.11.2026: two phones can be side by side)
            g = self.win.get_geometry(); t = self.win.translate_coords(ROOT, 0, 0)
            x, y = -t.x + g.width - w - 14, -t.y + 12
            if g.width < w + 28: x = -t.x + 4          # a narrow window: from its left edge
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

    def ask(self, *_):
        self.reboot.hide(); self.yes.show(); self.sep.show(); self.no.show(); self.place()

    def cancel(self, *_):
        self.yes.hide(); self.sep.hide(); self.no.hide(); self.reboot.show()

    def do_reboot(self, *_):
        self.cancel(); self.busy = True; self.reboot.hide(); self.note.set_text(f'rebooting {self.phone}…'); self.note.show()
        serial, box = PHONES[self.phone]
        def work():
            run(['docker', 'restart', box], timeout=90)
            for _ in range(60):
                run(['adb', 'connect', serial], 5)
                if run(['adb', '-s', serial, 'shell', 'getprop', 'sys.boot_completed'], 5) == '1': break
                GLib.usleep(2_000_000)
            GLib.idle_add(self.rebooted)
        threading.Thread(target=work, daemon=True).start()

    def rebooted(self):
        self.busy = False; self.rot[self.phone] = 0; self.mark(); self.note.hide(); self.reboot.show(); return False

if __name__ == '__main__':
    Bar(); Gtk.main()
