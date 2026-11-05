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
import os, subprocess, time
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0'); gi.require_version('GdkX11', '3.0')
gi.require_version('Keybinder', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib, GdkPixbuf, Keybinder
import cairo
from Xlib import display as xdisplay, X

GLib.set_prgname('vm-dock')          # its X class must not look like one of the three programs

FRONT = os.path.expanduser('~/.cache/chromium-vm/front'); os.makedirs(os.path.dirname(FRONT), exist_ok=True)
APPS = [   # (label, test on WM_CLASS (instance, class), how to bring it back when it has no window)
    ('Claude Code', lambda i, c: c == 'Xfce4-terminal', None),
    ('Claude',      lambda i, c: c.lower() == 'com.anthropic.claude', ['claude-desktop']),
    ('Chrome',      lambda i, c: c == 'Google-chrome' and 'chromium-vm-chrome' in i, None),
    # 5.11.2026: the fourth screen, the Pixel 7 through scrcpy (chromium-vm-pixel7, always running)
    ('Pixel 7',     lambda i, c: c.lower() == 'scrcpy', None),
]
NA = len(APPS)
BAR_H = 22            # the status bar's band; the dock sits above it
EDGE = 4              # the pointer within this many pixels of the bottom edge calls the dock
PAD, GAP, LABEL, SEP = 14, 16, 22, 18

# Layout displays (Marko, 2.11.2026: "three more displays with different layout ... using code from Rectangle"):
# a mini screen of the arrangement; a click runs chromium-vm-snap layout NAME. Slots in fractions of the work area.
LAYOUTS = [
    ('Halves', 'halves', [(0, 0, 0, .5, 1), (2, .5, 0, .5, 1)]),
    ('Claude | Chrome', 'cc-halves', [(1, 0, 0, .5, 1), (2, .5, 0, .5, 1)]),
    ('Claude 40 | Chrome 60', 'cc-40-60', [(1, 0, 0, .4, 1), (2, .4, 0, .6, 1)]),
    ('Chrome + 2', 'big', [(2, 0, 0, 2/3, 1), (0, 2/3, 0, 1/3, .5), (1, 2/3, .5, 1/3, .5)]),
]
NT = NA + len(LAYOUTS)      # tiles: the three programs, then the layouts
SNAP = '/usr/local/lib/chromium-vm/chromium-vm-snap'
COLOURS = [(0.85, 0.47, 0.34), (0.55, 0.45, 0.85), (0.30, 0.62, 0.90), (0.36, 0.75, 0.45)]   # Claude Code, Claude, Chrome, Pixel 7
REFRESH_MS = 330      # thumbnails while the dock is up

XD = xdisplay.Display()
ROOT = XD.screen().root
A_STACK = XD.intern_atom('_NET_CLIENT_LIST_STACKING')
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
            for n, (_, test, _) in enumerate(APPS):
                if test(cls[0] or '', cls[1] or ''):
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
        self.disp = GdkX11.X11Display.get_default()
        self.layout()
        Gdk.Screen.get_default().connect('size-changed', lambda *_: self.layout())
        Keybinder.init()
        Keybinder.bind('<Super>Tab', self.on_cmd_tab)
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
        elif APPS[n][2]:
            subprocess.Popen(APPS[n][2], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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
        self.shown = False; self.hover = -1; self.hide()

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
            if inside or now < self.peek_until:
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
                name = APPS[app][0]; cr.set_font_size(10); e = cr.text_extents(name)
                cr.set_source_rgba(0, 0, 0, 0.6); cr.rectangle(x + (w - e.x_advance) / 2 - 3, y + h / 2 - 9, e.x_advance + 6, 13); cr.fill()
                cr.set_source_rgb(1, 1, 1); cr.move_to(x + (w - e.x_advance) / 2, y + h / 2 + 1); cr.show_text(name)
            if n == self.hover:
                rounded(tx - 1, ty - 1, self.tw + 2, self.th + 2, 7)
                cr.set_source_rgba(1, 1, 1, 0.7); cr.set_line_width(2); cr.stroke()
            cr.set_font_size(12); ext = cr.text_extents(label); cr.set_source_rgba(1, 1, 1, 0.8)
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

    def on_cmd_tab(self, *_):
        self.track()
        n = 0 if self.front is None else (self.front + 1) % NA
        self.activate(n)
        self.peek_until = time.time() + 0.9
        if not self.shown: self.show_dock()


if __name__ == '__main__':
    Dock()
    Gtk.main()
