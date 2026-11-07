#!/usr/bin/env python3
"""chromium-vm dock: three full screens, one in front at a time, and a dock of live miniatures at the bottom edge.

Marko, 2.11.2026: "build me some dock, same as dock on the macOS ... when I hover down, it jumps as a dock on the
macOS ... They're not icons. They are screens" / "three screens, and I'm switching between them. It's just switching
the screen; they are not in the view at the same time." Then: only ONE key switches: Command-Tab.

- The three screens: Claude Code (xfce4-terminal + tmux), Claude (Claude Desktop), Chrome (the session's Chrome).
- Pointer at the bottom edge -> the dock slides up above the status bar, centred: three live thumbnails (refreshed
  3x a second while shown), labelled; click one -> it comes to the front; the dock hides when the pointer leaves.
- Command-Tab: the Mac viewer sends Command+Tab as Super_L+Tab; the dock binds <Super>Tab (nothing else): next
  screen, and the dock shows for a moment with the new one marked.
- Writes the front window id to ~/.cache/chromium-vm/front for the status bar (its see-through band copies it).
"""
import os, subprocess, time, threading
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0'); gi.require_version('GdkX11', '3.0')
gi.require_version('Keybinder', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib, GdkPixbuf, Keybinder
import cairo
from Xlib import display as xdisplay, X, XK
from Xlib.ext import record
from Xlib.protocol import rq

GLib.set_prgname('vm-dock')          # its X class must not look like one of the three programs

FRONT = os.path.expanduser('~/.cache/chromium-vm/front'); os.makedirs(os.path.dirname(FRONT), exist_ok=True)
APPS = [   # (label, test on WM_CLASS (instance, class) and the window title, how to bring it back when it has no window)
    ('Claude Code', lambda i, c, t: c == 'Xfce4-terminal', None),
    ('Claude app',  lambda i, c, t: c.lower() == 'com.anthropic.claude', ['claude-desktop']),   # 7.11.2026 Marko: "Claude app"
    ('Chrome',      lambda i, c, t: c == 'Google-chrome' and 'chromium-vm-chrome' in i, None),
    # 5.11.2026: the fourth screen, the Pixel 7 through scrcpy (chromium-vm-pixel7, always running); 7.11.2026 (Marko: two
    # emulators, "Pixel One, Pixel Two"): both are scrcpy windows, told apart by their titles "Pixel 1" / "Pixel 2"
    ('Pixel 1',     lambda i, c, t: c.lower() == 'scrcpy' and t != 'Pixel 2', None),
    ('Pixel 2',     lambda i, c, t: c.lower() == 'scrcpy' and t == 'Pixel 2', None),
]
NA = len(APPS)
BAR_H = 22            # the status bar's band; the dock sits above it
EDGE = 4              # the pointer within this many pixels of the bottom edge calls the dock
PAD, GAP, LABEL, SEP = 14, 16, 22, 18

# Layout displays (Marko, 2.11.2026: "three more displays with different layout ... using code from Rectangle"):
# a mini screen of the arrangement; a click runs chromium-vm-snap layout NAME. Slots in fractions of the work area.
LAYOUTS = [   # Marko, 5.11.2026: only these four, 40 | 60, Claude Code or Claude on the 40 side
    ('Claude Code | Chrome', 'code-chrome', [(0, 0, 0, .4, 1), (2, .4, 0, .6, 1)]),
    ('Claude app | Chrome', 'claude-chrome', [(1, 0, 0, .4, 1), (2, .4, 0, .6, 1)]),
    # 7.11.2026 (Marko): the triple view Claude app | Claude Code | Pixel 7 replaced by the two phones and the Claude app
    # Marko: "First stripe is Claude, then two stripes of androids"; the phones at their own shape (~0.27 of a 1512x916
    # screen each, see chromium-vm-snap before2/phone1/phone2), the rest of the width the Claude app
    ('Claude app | Pixel 1 | Pixel 2', 'claude-pixels', [(1, 0, 0, .46, 1), (3, .46, 0, .27, 1), (4, .73, 0, .27, 1)]),
    # 7.11.2026 (Marko): "I need copy of this but instead of Claude app it will be Claude Code"
    ('Claude Code | Pixel 1 | Pixel 2', 'code-pixels', [(0, 0, 0, .46, 1), (3, .46, 0, .27, 1), (4, .73, 0, .27, 1)]),
]
NT = NA + len(LAYOUTS)      # tiles: the three programs, then the layouts
SNAP = '/usr/local/lib/chromium-vm/chromium-vm-snap'
SNAP_NAMES = ['code', 'claude', 'chrome', 'pixel', 'pixel2']       # the snap tool's names of APPS, in the same order
COLOURS = [(0.85, 0.47, 0.34), (0.55, 0.45, 0.85), (0.30, 0.62, 0.90), (0.36, 0.75, 0.45), (0.90, 0.72, 0.25)]   # Claude Code, Claude app, Chrome, Pixel 1, Pixel 2
REFRESH_MS = 330      # thumbnails while the dock is up

XD = xdisplay.Display()
ROOT = XD.screen().root
A_STACK = XD.intern_atom('_NET_CLIENT_LIST_STACKING')
A_NAME, A_UTF8 = XD.intern_atom('_NET_WM_NAME'), XD.intern_atom('UTF8_STRING')
A_TYPE = XD.intern_atom('_NET_WM_WINDOW_TYPE'); A_NORMAL = XD.intern_atom('_NET_WM_WINDOW_TYPE_NORMAL')


def windows():
    """Per app the topmost viewable normal window (or None), and the app index in front."""
    try:
        stack = ROOT.get_full_property(A_STACK, X.AnyPropertyType).value     # bottom -> top
    except Exception:
        return [None] * len(APPS), None
    found = [None] * len(APPS); front = None
    for wid in stack:
        try:
            w = XD.create_resource_object('window', wid)
            if w.get_attributes().map_state != X.IsViewable: continue
            cls = w.get_wm_class()
            if not cls: continue
            t = w.get_full_property(A_TYPE, X.AnyPropertyType)
            if t and t.value and t.value[0] != A_NORMAL: continue          # dialogs, menus, popups
            title = ''
            if (cls[1] or '').lower() == 'scrcpy':                        # only the phones need their titles
                p = w.get_full_property(A_NAME, A_UTF8)
                title = (p.value.decode('utf-8', 'replace') if isinstance(p.value, bytes) else str(p.value)) if p else (w.get_wm_name() or '')
            for n, (_, test, _) in enumerate(APPS):
                if test(cls[0] or '', cls[1] or '', title):
                    found[n] = wid; front = n
        except Exception:
            continue
    return found, front


class Dock(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)       # override-redirect: matchbox leaves it alone
        self.set_app_paintable(True)
        self.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('draw', self.on_draw)
        self.connect('button-release-event', self.on_click)
        self.connect('motion-notify-event', self.on_motion)
        self.wins, self.front = [None] * NA, None
        self.thumbs = [None] * NA; self.under = None
        self.shown = False; self.edge_since = None; self.out_since = None; self.peek_until = 0
        self.hover = -1; self.slide = 0
        self.pinned = False     # opened by Command alone: stays up until a tile is clicked
        self.disp = GdkX11.X11Display.get_default()
        self.layout()
        Gdk.Screen.get_default().connect('size-changed', lambda *_: self.layout())
        Keybinder.init()
        Keybinder.bind('<Super>Tab', self.on_cmd_tab)
        threading.Thread(target=self.watch_super, daemon=True).start()
        GLib.timeout_add(70, self.poll)
        GLib.timeout_add(REFRESH_MS, self.refresh)
        GLib.timeout_add(1000, self.track)
        self.track()

    # ---- geometry ----------------------------------------------------------------------------------------------
    def layout(self):
        sc = Gdk.Screen.get_default(); self.sw, self.sh = sc.get_width(), sc.get_height()
        self.tw = int(max(110, min(240, (self.sw * 0.92 - 2 * PAD - (NT - 1) * GAP - SEP) / NT)))
        self.th = int(self.tw * self.sh / max(1, self.sw))
        self.w = PAD * 2 + NT * self.tw + (NT - 1) * GAP + SEP; self.h = PAD + self.th + LABEL + PAD // 2
        self.x = (self.sw - self.w) // 2; self.y = self.sh - BAR_H - 6 - self.h
        self.resize(self.w, self.h); self.move(self.x, self.y + (0 if self.shown else self.sh))

    def tile_x(self, n):        # 0-2: the three programs, 3-5: the layout displays, after a divider
        return PAD + n * (self.tw + GAP) + (SEP if n >= NA else 0)

    def tile_at(self, x, y):
        for n in range(NT):
            tx = self.tile_x(n)
            if tx - GAP / 2 <= x <= tx + self.tw + GAP / 2 and 0 <= y <= self.h: return n
        return -1

    # ---- who is where ------------------------------------------------------------------------------------------
    def track(self):
        self.wins, self.front = windows()
        fid = self.wins[self.front] if self.front is not None else None
        try:
            old = open(FRONT).read().strip()
        except Exception:
            old = ''
        if fid and old != str(fid):
            with open(FRONT + '.tmp', 'w') as f: f.write(str(fid))
            os.replace(FRONT + '.tmp', FRONT)
        return True

    def activate(self, n):
        self.track()
        wid = self.wins[n]
        if wid:
            subprocess.run(['xdotool', 'windowactivate', str(wid)], capture_output=True, timeout=3)
            # one program picked (a tile or ⌘Tab) = that program alone, full: out of any split layout (Marko, 2.11.2026:
            # "any individual app selected through this windows at the bottom ... should exit split screen mode")
            subprocess.run(['wmctrl', '-i', '-r', str(wid), '-b', 'add,maximized_vert,maximized_horz'],
                           capture_output=True, timeout=3)
        else:   # 5.11.2026: no window = not running: the snap tool starts it, waits for it, shows it full
            subprocess.Popen([SNAP, 'show', SNAP_NAMES[n]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        GLib.timeout_add(150, lambda: (self.track(), self.queue_draw(), False)[2])

    # ---- showing and hiding ------------------------------------------------------------------------------------
    def show_dock(self):
        if self.shown: return
        self.shown = True; self.track(); self.capture(); self.layout(); self.grab_under(); self.show_all()
        self.slide = 1.0
        def step():
            self.slide = max(0.0, self.slide - 0.25)
            self.move(self.x, self.y + int(self.slide * 40))
            if self.get_window(): self.get_window().raise_()
            return self.slide > 0
        self.move(self.x, self.y + 40); GLib.timeout_add(16, step)

    def hide_dock(self):
        if not self.shown: return
        self.shown = False; self.pinned = False; self.hover = -1; self.hide()

    def poll(self):
        try:
            _, px, py = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()[0:3]
        except Exception:
            return True
        now = time.time()
        if not self.shown:
            if py >= self.sh - EDGE:
                self.edge_since = self.edge_since or now
                if now - self.edge_since >= 0.08: self.show_dock()
            else:
                self.edge_since = None
        else:
            inside = (self.x <= px <= self.x + self.w and self.y - 8 <= py) or py >= self.sh - BAR_H
            if inside or self.pinned or now < self.peek_until:
                self.out_since = None
            else:
                self.out_since = self.out_since or now
                if now - self.out_since >= 0.35: self.hide_dock()
        return True

    # ---- the pictures ------------------------------------------------------------------------------------------
    def foreign(self, wid):
        try:
            return GdkX11.X11Window.foreign_new_for_display(self.disp, wid)
        except Exception:
            return None

    def capture(self):
        for n, wid in enumerate(self.wins):
            gw = self.foreign(wid) if wid else None
            pb = None
            if gw is not None:
                try:
                    ww, wh = gw.get_width(), gw.get_height()
                    full = Gdk.pixbuf_get_from_window(gw, 0, 0, ww, wh)
                    if full:   # keep the window's shape (side by side windows are narrow), centred in the tile
                        k = min(self.tw / ww, self.th / wh)
                        pb = full.scale_simple(max(1, int(ww * k)), max(1, int(wh * k)), GdkPixbuf.InterpType.BILINEAR)
                except Exception:
                    pb = None
            self.thumbs[n] = pb

    def grab_under(self):
        """What the screen shows where the dock will be, taken from the root window before the dock is mapped (the
        see-through band; true alpha is shown opaque on this Xvnc). Windows may be side by side, so the root."""
        try:
            self.under = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), self.x, self.y, self.w, self.h)
        except Exception:
            self.under = None

    def refresh(self):
        if self.shown:
            self.track(); self.capture(); self.queue_draw()
            if self.get_window(): self.get_window().raise_()
        return True

    def on_draw(self, _w, cr):
        if self.under is not None:
            Gdk.cairo_set_source_pixbuf(cr, self.under, 0, 0); cr.paint()
        else:
            cr.set_source_rgb(0.13, 0.13, 0.14); cr.paint()
        r = 16
        def rounded(x, y, w, h, r):
            cr.new_sub_path()
            cr.arc(x + w - r, y + r, r, -1.5708, 0); cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
            cr.arc(x + r, y + h - r, r, 1.5708, 3.1416); cr.arc(x + r, y + r, r, 3.1416, 4.7124); cr.close_path()
        rounded(0.5, 0.5, self.w - 1, self.h - 1, r)
        cr.set_source_rgba(0.08, 0.08, 0.09, 0.62); cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.18); cr.set_line_width(1); cr.stroke()
        cr.select_font_face('DejaVu Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD); cr.set_font_size(12)
        sx = self.tile_x(NA) - GAP / 2 - SEP / 2                     # the divider
        cr.set_source_rgba(1, 1, 1, 0.25); cr.set_line_width(1); cr.move_to(sx, PAD + 4); cr.line_to(sx, PAD + self.th - 4); cr.stroke()
        for k, (label, _, slots) in enumerate(LAYOUTS):
            n = NA + k; tx, ty = self.tile_x(n), PAD
            rounded(tx, ty, self.tw, self.th, 6); cr.set_source_rgb(0.1, 0.1, 0.11); cr.fill()
            for app, fx, fy, fw, fh in slots:
                x, y, w, h = tx + fx * self.tw + 2, ty + fy * self.th + 2, fw * self.tw - 4, fh * self.th - 4
                pb = self.thumbs[app]
                if pb is not None:
                    cr.save(); cr.rectangle(x, y, w, h); cr.clip()
                    cr.translate(x, y); cr.scale(w / pb.get_width(), h / pb.get_height())
                    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0); cr.paint(); cr.restore()
                    cr.set_source_rgba(*COLOURS[app], 0.30); cr.rectangle(x, y, w, h); cr.fill()
                else:
                    cr.set_source_rgba(*COLOURS[app], 0.55); cr.rectangle(x, y, w, h); cr.fill()
                cr.set_source_rgb(*COLOURS[app]); cr.set_line_width(1.5); cr.rectangle(x, y, w, h); cr.stroke()
                name = APPS[app][0]; fs = 10                               # shrink a name that does not fit its slot
                while True:
                    cr.set_font_size(fs); e = cr.text_extents(name)
                    if e.x_advance <= w - 8 or fs <= 7: break
                    fs -= 0.5
                cr.set_source_rgba(0, 0, 0, 0.6); cr.rectangle(x + (w - e.x_advance) / 2 - 3, y + h / 2 - 9, e.x_advance + 6, 13); cr.fill()
                cr.set_source_rgb(1, 1, 1); cr.move_to(x + (w - e.x_advance) / 2, y + h / 2 + 1); cr.show_text(name)
            if n == self.hover:
                rounded(tx - 1, ty - 1, self.tw + 2, self.th + 2, 7)
                cr.set_source_rgba(1, 1, 1, 0.7); cr.set_line_width(2); cr.stroke()
            fs = 12                                                         # and a layout name wider than its tile
            while True:
                cr.set_font_size(fs); ext = cr.text_extents(label)
                if ext.x_advance <= self.tw or fs <= 8: break
                fs -= 0.5
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.move_to(tx + (self.tw - ext.x_advance) / 2, ty + self.th + 16); cr.show_text(label)
        cr.set_font_size(12)
        for n, (label, _, _) in enumerate(APPS):
            tx, ty = self.tile_x(n), PAD
            pb = self.thumbs[n]
            if pb is not None:
                rounded(tx, ty, self.tw, self.th, 6); cr.set_source_rgb(0.1, 0.1, 0.11); cr.fill()
                cr.save(); rounded(tx, ty, self.tw, self.th, 6); cr.clip()
                Gdk.cairo_set_source_pixbuf(cr, pb, tx + (self.tw - pb.get_width()) / 2, ty + (self.th - pb.get_height()) / 2)
                cr.paint(); cr.restore()
            else:
                rounded(tx, ty, self.tw, self.th, 6); cr.set_source_rgb(0.2, 0.2, 0.22); cr.fill()
                cr.set_source_rgba(1, 1, 1, 0.5); cr.move_to(tx + 10, ty + self.th / 2); cr.show_text('starting …')
            if n == self.front:
                rounded(tx - 1.5, ty - 1.5, self.tw + 3, self.th + 3, 7)
                cr.set_source_rgb(0.85, 0.47, 0.34); cr.set_line_width(3); cr.stroke()      # Claude's orange
            elif n == self.hover:
                rounded(tx - 1, ty - 1, self.tw + 2, self.th + 2, 7)
                cr.set_source_rgba(1, 1, 1, 0.7); cr.set_line_width(2); cr.stroke()
            ext = cr.text_extents(label)
            cr.set_source_rgb(1, 1, 1) if n == self.front else cr.set_source_rgba(1, 1, 1, 0.8)
            cr.move_to(tx + (self.tw - ext.x_advance) / 2, ty + self.th + 16); cr.show_text(label)
        return False

    # ---- input ---------------------------------------------------------------------------------------------------
    def on_motion(self, _w, ev):
        h = self.tile_at(ev.x, ev.y)
        if h != self.hover: self.hover = h; self.queue_draw()

    def on_click(self, _w, ev):
        n = self.tile_at(ev.x, ev.y)
        if n >= NA:
            subprocess.Popen([SNAP, 'layout', LAYOUTS[n - NA][1]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            GLib.timeout_add(250, lambda: (self.hide_dock(), False)[1])
        elif n >= 0:
            self.activate(n)
            GLib.timeout_add(250, lambda: (self.hide_dock(), False)[1])

    # Marko, 5.11.2026: "when user press apple or command or win key do open bottom pop up with app switcher and keep it
    # open until user clicks one option then auto close". The Mac viewer sends Command as Super_L. Command pressed and
    # let go with no other key or click in between opens the dock pinned (a click on a tile picks and closes it);
    # Command alone again closes it. Seen through the X RECORD extension, so the key still reaches the programs.
    def watch_super(self):
        rd = xdisplay.Display()
        supers = {rd.keysym_to_keycode(XK.string_to_keysym(k)) for k in ('Super_L', 'Super_R')} - {0}
        ctx = rd.record_create_context(0, [record.AllClients], [{
            'core_requests': (0, 0), 'core_replies': (0, 0), 'ext_requests': (0, 0, 0, 0), 'ext_replies': (0, 0, 0, 0),
            'delivered_events': (0, 0), 'device_events': (X.KeyPress, X.ButtonPress), 'errors': (0, 0),
            'client_started': False, 'client_died': False}])
        state = {'alone': False}
        def got(reply):
            if reply.category != record.FromServer or reply.client_swapped or not len(reply.data): return
            data = reply.data
            while len(data):
                ev, data = rq.EventField(None).parse_binary_value(data, rd.display, None, None)
                if ev.type == X.KeyPress:
                    state['alone'] = ev.detail in supers
                elif ev.type == X.KeyRelease:
                    if ev.detail in supers and state['alone']: GLib.idle_add(self.on_cmd_alone)
                    state['alone'] = False
                elif ev.type == X.ButtonPress:
                    state['alone'] = False
        try:
            rd.record_enable_context(ctx, got)
        except Exception as e:
            print('watch_super:', e, flush=True)

    def on_cmd_alone(self):
        if self.shown and self.pinned:
            self.hide_dock(); return False
        self.track(); self.show_dock(); self.pinned = True; self.queue_draw()
        return False

    def on_cmd_tab(self, *_):
        self.track()
        n = 0 if self.front is None else (self.front + 1) % NA
        self.activate(n)
        self.peek_until = time.time() + 0.9
        if not self.shown: self.show_dock()


if __name__ == '__main__':
    Dock()
    Gtk.main()
