#!/usr/bin/env python3
"""chromium-vm status bar: one line at the bottom of the VM's screen, see-through, letters with a hard shadow.

Marko, 2.11.2026: "one line running from the beginning to the end of the screen ... CPU and memory ... network ...
what's currently going on ... Transferring to Google Drive ... available drive space", "at the bottom of the virtual
machine ... transparent at the bottom with a hard shadow so I can see the letters", "make it colorful. Let the colors
speak".

See-through by alpha through xcompmgr (started by the session); clicks between the letters reach Chrome
(input shape). A cut-out window alone left a black strip: Chrome does not repaint what it gives back. A click on the letters opens the settings. Settings: ~/.config/chromium-vm/statusbar.json.
"""
import json, math, os, threading, time, urllib.request
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
# The star (Marko, 5.11.2026): "Star control apps should be one more addition to our status monitor ... It starts with
# this: David Star through triangles ... I click, and it opens up from the bottom up, listing all the applications of
# the Star menu." The menu and its rows live in STAR_SWIFT/linux/star.py; the bar draws the star first and pops it up.
STAR_PY = os.path.expanduser('~/STAR_SWIFT/linux/star.py')

def star_menu():
    import importlib.util
    spec = importlib.util.spec_from_file_location('mantra_star', STAR_PY)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)   # read fresh: rows change, no restart
    return mod.build_menu()

GEAR = 26   # the Mac viewer's settings gear sits on the line's right end, after the power button (Marko, 2.11.2026)

PARTS = [  # key, label in the settings
    ('cpu', 'CPU'), ('ram', 'Memory'), ('disk', 'Free SSD space'), ('net', 'Internet speed ↓ ↑'),
    ('tail', 'Tailscale speed ↓ ↑'), ('moving', 'What is moving (downloads, Google Drive)'),
    ('uptime', 'Up since'), ('clock', 'Croatian time'),
]
DEFAULT = {'show': {k: True for k, _ in PARTS} | {'tail': False, 'clock': False}, 'size': 13, 'height': 22}

# Two colours (Marko, 2.11.2026: "white is the variable name, and orange is the variable itself").
COL = {'power': (1.0, 1.0, 1.0), 'name': (1.0, 1.0, 1.0), 'value': (1.0, 0.58, 0.10), 'now': (0.35, 0.95, 0.45),
       'down': (0.35, 0.95, 0.45), 'up': (1.0, 0.30, 0.30), 'pipe': (0.0, 0.0, 0.0), 'star': (0.93, 0.93, 0.90)}   # a black pipe between parts (Marko)   # NET: download green, upload red (Marko)   # green: what is moving now

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

def bits(n):
    """Bytes per second as bits, no arrow, no '/s' (Marko: "the colours make the difference"); a fixed width so the
    neighbours never move: '12.3Mb', ' 950Kb'."""
    n *= 8
    for unit in ('b', 'Kb', 'Mb', 'Gb'):
        if n < 1000 or unit == 'Gb': break
        n /= 1000
    v = f'{n:.0f}' if n >= 100 or unit == 'b' else f'{n:.1f}'
    return f'{v}{unit}'.rjust(6)

SPEEDTEST = {}

def run_speedtest():
    """speedtest-cli on the VM (Oracle's line, not the SIM): download and upload in bits/s, ping in ms."""
    SPEEDTEST.clear(); SPEEDTEST['state'] = 'running'
    try:
        out = subprocess.run(['speedtest-cli', '--json', '--secure'], capture_output=True, text=True, timeout=120).stdout
        j = json.loads(out)
        SPEEDTEST.update(state='done', down=j['download'], up=j['upload'], ping=j['ping'], at=time.time())
    except Exception:
        SPEEDTEST.update(state='failed', at=time.time())

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
        if seg: seg.append(('|', 'pipe'))                       # a black pipe, no spaces (Marko, 2.11.2026)
        seg.extend(([(name, 'name')] if name else []) + (value if isinstance(value, list) else [(value, 'value')]))
    if os.path.exists(STAR_PY):
        part('', [('  ', 'star')])                             # the David star first (Marko, 5.11.2026)
    # The order is importance (Marko, 2.11.2026): the network first (no label), free SSD second, then the rest.
    for key, dev, name in (('net', NET, ''), ('tail', 'tailscale0', 'TS')):
        if show.get(key):
            d, u = r['speeds'].get(dev, (0, 0))
            st = SPEEDTEST if key == 'net' else None
            if st and st.get('state') == 'running':
                part(name, [('speed test…', 'value')])
            elif st and st.get('state') == 'done' and time.time() - st['at'] < 5:
                part(name, [(bits(st['down'] / 8), 'down'), (bits(st['up'] / 8), 'up'), (f"{st['ping']:.0f}ms", 'value')])
            elif st and st.get('state') == 'failed' and time.time() - st['at'] < 5:
                part(name, [('speed test failed', 'up')])
            else:
                part(name, [(bits(d), 'down'), (bits(u), 'up')])
    if show.get('disk'):
        part('SSD', f"{r['free'] / 2**30:5.1f}GB")
    if show.get('cpu'):
        part('CPU', f"{r['cpu']:3.0f}%")
    if show.get('ram'):
        part('RAM', f"{r['ram_used'] / 2**30:4.1f}/{r['ram_total'] / 2**30:4.1f}")
    if show.get('uptime'):
        h = int(r['up'] // 3600)
        part('UP', (f'{h // 24:2d}d{h % 24:02d}h' if h >= 24 else f'{h:2d}h{int(r["up"] % 3600 // 60):02d}m'))
    if show.get('clock'):
        os.environ['TZ'] = 'Europe/Zagreb'; time.tzset()
        part('CT', time.strftime('%H:%M'))
    # Marko, 2.11.2026: "After the app and its hours make a power button ... Only one option, just I need to confirm
    # and that's the reboot": the last thing on the line, drawn (not a font glyph), a click asks REBOOT | CANCEL
    part('', [('  ', 'power')])
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
        self.net_x = (0, 0); self.power_x = (-1, -1); self.star_x = (-1, -1); self.menu = None
        self.connect('button-press-event', self.on_click)
        self.place()
        Gdk.Screen.get_default().connect('size-changed', lambda *_: self.place())
        # Cut the shape BEFORE the window appears: mapped whole even once, it covers Chrome as a black block, and
        # Chrome does not repaint what the shape gives back (2.11.2026).
        self.realize()
        self.seg = [('…', 'name')]; self.reshape()
        self.show_all()
        GLib.timeout_add(1000, self.tick); self.tick()
        GLib.timeout_add(400, lambda: (self.queue_draw(), True)[1])   # follow the page under the band

    def on_click(self, _w, ev):
        a, b = self.net_x
        pa, pb = self.power_x
        sa, sb = self.star_x
        if sa - 6 <= ev.x <= sb + 4:
            try:
                self.menu = star_menu()                         # kept on self: a dropped menu closes at once
                rect = Gdk.Rectangle(); rect.x, rect.y, rect.width, rect.height = int(sa), 0, int(sb - sa), 1
                self.menu.popup_at_rect(self.get_window(), rect, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, ev)
            except Exception as e:
                print('star:', e, flush=True)
        elif pa - 4 <= ev.x <= pb + 6:
            Reboot().show_all()
        elif a <= ev.x <= b:
            if SPEEDTEST.get('state') != 'running':
                threading.Thread(target=run_speedtest, daemon=True).start()
        else:
            Settings(self).show_all()

    # Marko, 2.11.2026: "limit the background and clicking area ... exactly how long the text is, not more": the bar is
    # only as wide as its text, in the bottom-right corner; the rest of the bottom edge belongs to the windows
    def text_width(self):
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
        cr.select_font_face('DejaVu Sans Mono', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.conf['size'])
        now = sum(cr.text_extents(t).x_advance for t, c in self.seg if c == 'now')
        status = sum(cr.text_extents(t).x_advance for t, c in self.seg if c != 'now')
        return int(10 + now + (24 if now else 0) + status + 10 + GEAR)

    def place(self):
        sc = Gdk.Screen.get_default(); sw, sh = sc.get_width(), sc.get_height()
        w = min(sw, max(40, self.text_width())); self.bx = sw - w
        self.move(self.bx, sh - self.conf['height']); self.resize(w, self.conf['height'])

    def tick(self):
        sc = Gdk.Screen.get_default()
        try:
            self.seg = segments(self.readings.read(), self.conf['show'])
        except Exception as e:
            self.seg = [(f'status bar: {e}', 'value')]
        if self.get_size() != (min(sc.get_width(), max(40, self.text_width())), self.conf['height']): self.place()
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
        x = w - 10 - GEAR - sum(cr.text_extents(t).x_advance for t, _ in status)   # the status: on the right (Marko)
        # the speeds are the part a click runs the speed test on: after the star's pipe when there is a star
        net_start, net_end, pipes = x, None, 0
        skip = 1 if any(c == 'star' for _, c in status) else 0
        for text, col in status:
            if col == 'pipe':
                pipes += 1
                if pipes == skip:
                    net_start = x + cr.text_extents(text).x_advance
                elif pipes == skip + 1 and net_end is None:
                    net_end = x
            adv = cr.text_extents(text).x_advance
            if col == 'star':                                   # the David star: two equal triangles, never five points
                self.star_x = (x, x + adv)
                s = self.conf['size']; r = s * 0.55; cx, cy = x + adv / 2, y - s * 0.36
                cr.set_source_rgb(*COL['star']); cr.set_line_width(max(1.2, s / 10)); cr.new_path()
                for rot in (-90, 90):
                    for k in range(3):
                        a = math.radians(rot + k * 120)
                        (cr.move_to if k == 0 else cr.line_to)(cx + r * math.cos(a), cy + r * math.sin(a))
                    cr.close_path(); cr.stroke()
            elif col == 'power':                                  # ⏻: an open circle and a stroke through its gap
                self.power_x = (x, x + adv)
                s = self.conf['size']; r = s * 0.42; cx, cy = x + adv / 2, y - s * 0.36
                cr.set_source_rgb(*COL['power']); cr.set_line_width(max(1.5, s / 8)); cr.new_path()
                cr.arc(cx, cy, r, -1.15, 4.29); cr.stroke()
                cr.move_to(cx, cy - r * 1.25); cr.line_to(cx, cy + r * 0.05); cr.stroke()
            elif text.strip():
                cr.set_source_rgb(*COL[col]); cr.move_to(x, y); cr.show_text(text)   # no outline (Marko, 2.11.2026)
            x += adv
        self.net_x = (net_start, net_end if net_end is not None else x)     # the speeds come first

    def reshape(self):
        w, h = self.get_size()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        self.paint(cairo.Context(surf), w, h)
        region = Gdk.cairo_region_create_from_surface(surf)
        # the band is visible now: the whole line takes the click (settings)

    def chrome_window(self):
        if time.time() - self.under_at > 1 or self.under is None:
            self.under_at = time.time()
            try:
                # the screen in front (the dock writes it: Claude Code, Claude or Chrome, 2.11.2026), else Chrome
                try:
                    ids = [open(os.path.expanduser('~/.cache/chromium-vm/front')).read().strip()]
                except Exception:
                    ids = subprocess.run(['xdotool', 'search', '--onlyvisible', '--class', 'google-chrome'],
                                         capture_output=True, text=True, timeout=2).stdout.split()
                disp = GdkX11.X11Display.get_default()
                wid = int(ids[-1]) if ids and ids[-1] else 0
                if self.under is None or self.under.get_xid() != wid:
                    self.under = GdkX11.X11Window.foreign_new_for_display(disp, wid) if wid else None
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
                pb = Gdk.pixbuf_get_from_window(under, getattr(self, 'bx', 0), sh - h, w, h)
            except Exception:
                pb = None
        if pb is not None:
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0); cr.paint()
        else:   # nothing under the bar (openbox keeps maximized windows above it since 2.11.2026): the desktop colour
            cr.set_source_rgb(0.125, 0.129, 0.141); cr.paint()
        cr.set_source_rgba(0, 0, 0, 0.5); cr.paint()                 # the 50% band, like subtitles
        w, h = self.get_size(); self.paint(cr, w, h); return False

class Reboot(Gtk.Window):
    """The power button's one choice: REBOOT, confirmed. The Mac viewer reconnects by itself when the VM is back."""
    def __init__(self):
        super().__init__(title='Power (chromium-vm)')
        self.set_keep_above(True); self.set_border_width(16); self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); self.add(box)
        t = Gtk.Label(); t.set_markup('<b>REBOOT chromium-vm?</b>\nEverything open on the VM closes; it is back in about a minute.')
        box.pack_start(t, False, False, 0)
        row = Gtk.Box(spacing=10)
        go = Gtk.Button(label='REBOOT'); go.connect('clicked', self.reboot)
        no = Gtk.Button(label='CANCEL'); no.connect('clicked', lambda *_: self.destroy())
        row.pack_start(go, False, False, 0); row.pack_start(no, False, False, 0); box.pack_start(row, False, False, 0)
        self.set_position(Gtk.WindowPosition.CENTER)

    def reboot(self, *_):
        self.destroy()
        subprocess.Popen(['sudo', '-n', 'systemctl', 'reboot'], start_new_session=True)

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
