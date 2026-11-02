#!/usr/bin/env python3
"""chromium-vm status bar: one line at the bottom of the VM's screen, see-through, letters with a hard shadow.

Marko, 2.11.2026: "one line running from the beginning to the end of the screen ... CPU and memory ... network ...
what's currently going on ... Transferring to Google Drive ... available drive space", "at the bottom of the virtual
machine ... transparent at the bottom with a hard shadow so I can see the letters", "make it colorful. Let the colors
speak".

See-through by alpha through xcompmgr (started by the session); clicks between the letters reach Chrome
(input shape). A cut-out window alone left a black strip: Chrome does not repaint what it gives back. A click on the letters opens the settings. Settings: ~/.config/chromium-vm/statusbar.json.
"""
import json, os, time, urllib.request
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkX11
import subprocess
import cairo
GLib.set_prgname('vm-statusbar')   # its X class must not contain "chromium": the session's resize watcher looks for that

CONF = os.path.expanduser('~/.config/chromium-vm/statusbar.json')
TOKEN_FILE = os.path.expanduser('~/.config/chromium-vm/agent-token')
AGENT = 'http://100.102.86.30:8890/api/status'
NET = 'enp0s6'

PARTS = [  # key, label in the settings
    ('cpu', 'CPU'), ('ram', 'Memory'), ('disk', 'Free SSD space'), ('net', 'Internet speed ↓ ↑'),
    ('tail', 'Tailscale speed ↓ ↑'), ('moving', 'What is moving (downloads, Google Drive)'),
    ('uptime', 'Up since'), ('clock', 'Croatian time'),
]
DEFAULT = {'show': {k: True for k, _ in PARTS} | {'tail': False, 'clock': False}, 'size': 13, 'height': 22}

# Two colours (Marko, 2.11.2026: "white is the variable name, and orange is the variable itself").
COL = {'name': (1.0, 1.0, 1.0), 'value': (1.0, 0.58, 0.10), 'now': (0.35, 0.95, 0.45)}   # green: what is moving now

def load_conf():
    c = json.loads(json.dumps(DEFAULT))
    try:
        u = json.load(open(CONF)); c['show'].update(u.get('show', {})); c['size'] = u.get('size', c['size'])
    except Exception:
        pass
    c['height'] = int(c['size'] * 1.7)
    return c

def human(n, width=6):
    """A size in a fixed width, so the numbers never push their neighbours (Marko, 2.11.2026)."""
    for unit in ('B ', 'KB', 'MB', 'GB', 'TB'):
        if n < 1000 or unit == 'TB':
            return (f'{n:.0f}' if unit in ('B ', 'KB') else f'{n:.1f}').rjust(width) + ' ' + unit
        n /= 1024

def speed(arrow, n):
    """'↓6.0KB/s' right-aligned in a fixed width: the arrow stays with its number, nothing else moves."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1000 or unit == 'GB': break
        n /= 1024
    v = f'{n:.0f}' if unit in ('B', 'KB') and n >= 100 or unit == 'B' else f'{n:.1f}'
    return f'{arrow}{v}{unit}/s'.rjust(9)

class Readings:
    def __init__(self):
        self.cpu_prev = self.cpu_times(); self.net_prev = self.net_bytes(); self.t_prev = time.time()
        self.agent = {}; self.agent_at = 0

    @staticmethod
    def cpu_times():
        v = list(map(int, open('/proc/stat').readline().split()[1:]))
        return sum(v), v[3] + v[4]

    @staticmethod
    def net_bytes():
        out = {}
        for line in open('/proc/net/dev').readlines()[2:]:
            name, rest = line.split(':', 1); f = rest.split()
            out[name.strip()] = (int(f[0]), int(f[8]))
        return out

    def read(self):
        now = time.time(); dt = max(0.5, now - self.t_prev); self.t_prev = now
        tot, idle = self.cpu_times(); pt, pi = self.cpu_prev; self.cpu_prev = (tot, idle)
        cpu = 100.0 * (1 - (idle - pi) / max(1, tot - pt))
        mem = {l.split(':')[0]: int(l.split()[1]) * 1024 for l in open('/proc/meminfo')}
        ram_used, ram_total = mem['MemTotal'] - mem['MemAvailable'], mem['MemTotal']
        st = os.statvfs('/'); free, size = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
        nb = self.net_bytes(); speeds = {}
        for k in (NET, 'tailscale0'):
            if k in nb and k in self.net_prev:
                speeds[k] = ((nb[k][0] - self.net_prev[k][0]) / dt, (nb[k][1] - self.net_prev[k][1]) / dt)
        self.net_prev = nb
        if now - self.agent_at > 2:
            self.agent_at = now
            try:
                r = urllib.request.Request(AGENT, data=b'{}', method='POST',
                                           headers={'X-Mantra-Token': open(TOKEN_FILE).read().strip()})
                self.agent = json.load(urllib.request.urlopen(r, timeout=2)).get('result', {})
            except Exception:
                self.agent = {}
        up = float(open('/proc/uptime').read().split()[0])
        return dict(cpu=cpu, load=os.getloadavg()[0], ncpu=os.cpu_count(), ram_used=ram_used, ram_total=ram_total,
                    free=free, size=size, speeds=speeds, agent=self.agent, up=up)

def segments(r, show):
    """[(text, 'name'|'value')]. Every field has a fixed width; what changes in length (what is moving) comes last."""
    seg = []
    def part(name, value):
        if seg: seg.append((' ', 'name'))
        seg.extend([(name, 'name'), (value, 'value')])          # the colours separate them: no space (Marko)
    if show.get('cpu'):
        part('CPU', f"{r['cpu']:3.0f}%")
    if show.get('ram'):
        part('RAM', f"{r['ram_used'] / 2**30:4.1f}/{r['ram_total'] / 2**30:4.1f}GB")
    if show.get('disk'):
        part('SSD', f"{r['free'] / 2**30:5.1f}GB")
    for key, dev, name in (('net', NET, 'NET'), ('tail', 'tailscale0', 'TAILSCALE')):
        if show.get(key):
            d, u = r['speeds'].get(dev, (0, 0))
            part(name, speed('↓', d) + speed('↑', u))
    if show.get('uptime'):
        h = int(r['up'] // 3600)
        part('UP', (f'{h // 24:2d}d{h % 24:02d}h' if h >= 24 else f'{h:2d}h{int(r["up"] % 3600 // 60):02d}m'))
    if show.get('clock'):
        os.environ['TZ'] = 'Europe/Zagreb'; time.tzset()
        part('CT', time.strftime('%H:%M'))
    if show.get('moving'):
        a, items = r['agent'], []
        for g in a.get('downloading', [])[:2]:
            items.append(f"↓Chrome {g['name'][:36]} {human(g['bytes']).strip().replace(' ', '')}")
        if a.get('moving'):
            items.append(a['moving'][:70])
        elif a.get('drive_queue'):
            items.append(f"Drive queue {a['drive_queue']}")
        if not r['agent']:
            items = ['agent not answering']
        if items:   # drawn from the left edge (Marko): the status stays on the right
            seg.append(('  '.join(items), 'now'))
    return seg

class Bar(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)       # override-redirect: no frame, the WM leaves it alone
        self.conf = load_conf(); self.readings = Readings(); self.seg = []
        self.set_app_paintable(True)
        # See-through by copying what is under the bar from Chrome's own window (the compositor keeps it whole even
        # where the bar covers it) and darkening it 50%: true alpha was ignored on this Xvnc screen (2.11.2026).
        self.under = None; self.under_at = 0
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('draw', self.on_draw)
        self.connect('button-press-event', lambda *_: Settings(self).show_all())
        self.place()
        Gdk.Screen.get_default().connect('size-changed', lambda *_: self.place())
        # Cut the shape BEFORE the window appears: mapped whole even once, it covers Chrome as a black block, and
        # Chrome does not repaint what the shape gives back (2.11.2026).
        self.realize()
        self.seg = [('…', 'name')]; self.reshape()
        self.show_all()
        GLib.timeout_add(1000, self.tick); self.tick()
        GLib.timeout_add(400, lambda: (self.queue_draw(), True)[1])   # follow the page under the band

    def place(self):
        sc = Gdk.Screen.get_default(); w, h = sc.get_width(), sc.get_height()
        self.move(0, h - self.conf['height']); self.resize(w, self.conf['height'])

    def tick(self):
        sc = Gdk.Screen.get_default()
        if self.get_size() != (sc.get_width(), self.conf['height']): self.place()
        try:
            self.seg = segments(self.readings.read(), self.conf['show'])
        except Exception as e:
            self.seg = [(f'status bar: {e}', 'value')]
        self.reshape(); self.queue_draw()
        if self.get_window(): self.get_window().raise_()      # stay above Chrome
        return True

    def paint(self, cr, w, h):
        cr.select_font_face('DejaVu Sans Mono', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)   # a terminal font
        cr.set_font_size(self.conf['size'])
        y = h - (h - self.conf['size']) / 2 - 3
        now = [t for t in self.seg if t[1] == 'now']
        status = [t for t in self.seg if t[1] != 'now']
        for text, col in now:                                   # what is happening: from the left edge
            cr.set_source_rgb(*COL[col]); cr.move_to(10, y); cr.show_text(text)
        x = w - 10 - sum(cr.text_extents(t).x_advance for t, _ in status)   # the status: on the right (Marko)
        for text, col in status:
            if text.strip():
                cr.set_source_rgb(*COL[col]); cr.move_to(x, y); cr.show_text(text)   # no outline (Marko, 2.11.2026)
            x += cr.text_extents(text).x_advance

    def reshape(self):
        w, h = self.get_size()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        self.paint(cairo.Context(surf), w, h)
        region = Gdk.cairo_region_create_from_surface(surf)
        # the band is visible now: the whole line takes the click (settings)

    def chrome_window(self):
        if time.time() - self.under_at > 5 or self.under is None:
            self.under_at = time.time()
            try:
                ids = subprocess.run(['xdotool', 'search', '--onlyvisible', '--class', 'google-chrome'],
                                     capture_output=True, text=True, timeout=2).stdout.split()
                disp = GdkX11.X11Display.get_default()
                self.under = GdkX11.X11Window.foreign_new_for_display(disp, int(ids[-1])) if ids else None
            except Exception:
                self.under = None
        return self.under

    def on_draw(self, _w, cr):
        w, h = self.get_size()
        under = self.chrome_window()
        pb = None
        if under is not None:
            try:
                sh = Gdk.Screen.get_default().get_height()
                pb = Gdk.pixbuf_get_from_window(under, 0, sh - h, w, h)
            except Exception:
                pb = None
        if pb is not None:
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0); cr.paint()
        cr.set_source_rgba(0, 0, 0, 0.5); cr.paint()                 # the 50% band, like subtitles
        w, h = self.get_size(); self.paint(cr, w, h); return False

class Settings(Gtk.Window):
    def __init__(self, bar):
        super().__init__(title='Status bar (chromium-vm)')
        self.bar = bar; self.set_keep_above(True); self.set_border_width(14)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)     # matchbox floats dialogs; a normal window would fill the screen
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); self.add(box)
        head = Gtk.Box(spacing=8)
        t = Gtk.Label(); t.set_markup('<b>STATUS BAR</b>  what it shows'); head.pack_start(t, False, False, 0)
        x = Gtk.Button(label='✕'); x.set_relief(Gtk.ReliefStyle.NONE); x.connect('clicked', lambda *_: self.destroy())
        head.pack_end(x, False, False, 0); box.pack_start(head, False, False, 0)
        for key, label in PARTS:
            c = Gtk.CheckButton(label=label); c.set_active(bar.conf['show'].get(key, True))
            c.connect('toggled', self.toggle, key); box.pack_start(c, False, False, 0)
        row = Gtk.Box(spacing=8); row.pack_start(Gtk.Label(label='Letter size'), False, False, 0)
        sp = Gtk.SpinButton.new_with_range(9, 24, 1); sp.set_value(bar.conf['size'])
        sp.connect('value-changed', self.size); row.pack_start(sp, False, False, 0); box.pack_start(row, False, False, 0)
        self.set_position(Gtk.WindowPosition.CENTER)

    def save(self):
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        json.dump({'show': self.bar.conf['show'], 'size': self.bar.conf['size']}, open(CONF, 'w'), indent=1)
        self.bar.conf = load_conf(); self.bar.place(); self.bar.tick()

    def toggle(self, c, key): self.bar.conf['show'][key] = c.get_active(); self.save()
    def size(self, sp): self.bar.conf['size'] = int(sp.get_value()); self.save()

if __name__ == '__main__':
    Bar(); Gtk.main()
