#!/usr/bin/env python3
"""vmctl: chromium-vm's services, started and stopped by hand or by any program (Marko, 14.11.2026).

"Only thing which is running is connection keeper. And all other services are optional ... I enable each service as I
need it which can also be enabled remotely by any cloud application if it needs some kind of service and then it can
also close it ... you need to build better API, Python API for virtual machine control."

The registry is /etc/chromium-vm/services.json (source: tools/vmctl/services.json). Core services are on at boot and
locked; every other one is off at boot.

    vmctl list                         every service: state, core, short name
    vmctl status [NAME]                one service (or all) as JSON
    vmctl start NAME [--gui] [--auto]  start it (its deps first); --gui = the gear's start (e.g. the phone's mirror);
                                       --auto = as a dependency of something else (gc stops it when nobody needs it)
    vmctl stop NAME                    stop it; deps nobody needs any more are stopped too
    vmctl restart NAME
    vmctl lease NAME MINUTES [WHO]     start it and hold it; it stops when the last lease ends (if a lease started it)
    vmctl release LEASE_ID | vmctl renew LEASE_ID MINUTES | vmctl leases
    vmctl gc                           stop dependencies nobody needs (chromium-vm-phone calls it after a stop)
    vmctl log [N]                      the last N lines of the start/stop log
    vmctl serve                        the HTTP API on the Tailscale address (service chromium-vm-vmctl)

HTTP (X-Mantra-Token: ~/.config/chromium-vm/vmctl-token, or Authorization: Bearer ...), port 8896, Tailscale only:
    GET  /health                                 no token
    GET  /services                               [{name, short, title, kind, core, running, manual, leases}]
    GET  /services/NAME
    POST /services/NAME/start|stop|restart       body {"who": "...", "gui": false}
    POST /services/NAME/lease                    body {"minutes": 30, "who": "..."}  -> {"lease": {id, until, ...}}
    GET  /leases    POST /leases/ID/release    POST /leases/ID/renew {"minutes": N}
Every start/stop is a line in ~/.cache/chromium-vm/vmctl.log. The token is never logged.
"""
import fcntl, json, os, secrets, shlex, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REGISTRY = os.environ.get('VMCTL_REGISTRY', '/etc/chromium-vm/services.json')
HOME = os.path.expanduser('~')
STATE_DIR = os.path.join(HOME, '.local/state/vmctl'); os.makedirs(STATE_DIR, exist_ok=True)
STATE = os.path.join(STATE_DIR, 'state.json')            # manual / auto marks and the leases: survive a restart
CACHE = os.path.join(HOME, '.cache/chromium-vm'); os.makedirs(CACHE, exist_ok=True)
LOG = os.path.join(CACHE, 'vmctl.log')
SNAPSHOT = os.path.join(CACHE, 'vmctl-status.json')      # written every few seconds by the server: the status bar reads it
TOKEN_FILE = os.path.join(HOME, '.config/chromium-vm/vmctl-token')
PORT = int(os.environ.get('VMCTL_PORT', '8896'))
UID = os.getuid()
ENV = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{UID}', DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{UID}/bus',
           DISPLAY=os.environ.get('DISPLAY', ':1'))
_op_lock = threading.RLock()                             # one start/stop at a time inside this process


def conf():
    c = {}
    try:
        for l in open('/etc/chromium-vm.conf'):
            if '=' in l and not l.lstrip().startswith('#'):
                k, v = l.strip().split('=', 1); c[k] = v
    except OSError:
        pass
    return c


def registry():
    return {s['name']: s for s in json.load(open(REGISTRY))['services']}


def log(who, action, name, result):
    with open(LOG, 'a') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {who or '?'} {action} {name}: {result}\n")


def run(cmd, t=300):
    if isinstance(cmd, str): cmd = ['bash', '-c', cmd]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t, env=ENV)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, 'timeout'


# ---- state file (flock: the CLI and the server share it) ----
class State:
    def __enter__(self):
        self.f = open(STATE + '.lock', 'a'); fcntl.flock(self.f, fcntl.LOCK_EX)
        try: self.d = json.load(open(STATE))
        except Exception: self.d = {}
        self.d.setdefault('manual', {}); self.d.setdefault('auto', {}); self.d.setdefault('leases', [])
        return self.d

    def __exit__(self, *a):
        tmp = STATE + '.tmp'; json.dump(self.d, open(tmp, 'w'), indent=1); os.replace(tmp, STATE)
        fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()


def read_state():
    try: return json.load(open(STATE))
    except Exception: return {'manual': {}, 'auto': {}, 'leases': []}


# ---- what is running: three calls for everything ----
def _active(units, user):
    if not units: return {}
    rc, out = run(['systemctl'] + (['--user'] if user else []) + ['is-active'] + list(units), t=20)
    return dict(zip(units, out.splitlines()))


def states(reg=None):
    reg = reg or registry()
    sysu = sorted({u for s in reg.values() if s['kind'] in ('systemd', 'docker') for u in s.get('units', [])} | {'docker.service'})
    usru = sorted({u for s in reg.values() if s['kind'] == 'user' for u in s.get('units', [])})
    sa, ua = _active(sysu, False), _active(usru, True)
    cont = {}
    if sa.get('docker.service') == 'active':           # never ask docker while it is off: docker.socket would start it
        rc, out = run(['docker', 'ps', '--format', '{{.Names}}'], t=20)
        cont = set(out.split()) if rc == 0 else set()
    out = {}
    for n, s in reg.items():
        if s['kind'] == 'docker':
            r = all(c in cont for c in s.get('containers', []))
        else:
            act = ua if s['kind'] == 'user' else sa
            r = act.get(s['units'][0]) in ('active', 'activating', 'reloading')
            if s.get('probe'):
                r = r and run(s['probe'], t=10)[0] == 0
        out[n] = r
    return out


def describe(reg=None, st=None):
    reg = reg or registry(); st = st if st is not None else states(reg); d = read_state(); now = time.time()
    return [dict(name=n, short=s['short'], title=s.get('title', n), kind=s['kind'], core=bool(s.get('core')),
                 running=st[n], manual=bool(d['manual'].get(n)), deps=s.get('deps', []),
                 leases=[l for l in d['leases'] if l['service'] == n and l['until'] > now]) for n, s in reg.items()]


# ---- start / stop ----
def _units_cmd(s, verb):
    units = s.get('units', [])
    if verb == 'stop': units = list(reversed(units))
    if s['kind'] == 'user':
        return ['systemctl', '--user', verb] + units
    return ['sudo', '-n', 'systemctl', verb] + units


def start(name, who='cli', gui=False, manual=True, _seen=None):
    reg = registry(); s = reg.get(name)
    if not s: raise KeyError(f'no service {name}')
    _seen = _seen or set(); _seen.add(name)
    with _op_lock:
        for dep in s.get('deps', []):
            if dep not in _seen and not states(reg)[dep]:
                start(dep, who=f'{who} (for {name})', manual=False, _seen=_seen)
                with State() as d: d['auto'][dep] = True
        if states(reg)[name]:
            res = (0, 'already running')
        elif s['kind'] == 'docker' or s.get('start'):
            res = run(s.get('gui_start') if gui and s.get('gui_start') else s['start'])
        else:
            # unit active but its program gone (a probe fails: Firefox closed by hand): restart, start would be a no-op
            act = _active(s['units'][:1], s['kind'] == 'user').get(s['units'][0]) == 'active'
            res = run(_units_cmd(s, 'restart' if act and s.get('probe') else 'start'))
        ok = res[0] == 0
        with State() as d:
            if manual: d['manual'][name] = True; d['auto'].pop(name, None)
        log(who, 'start' + (' gui' if gui else ''), name, 'ok' if ok else f'FAILED {res[1][-300:]}')
        if not ok: raise RuntimeError(res[1][-500:] or 'start failed')
        return {'name': name, 'running': states(reg)[name], 'note': res[1][-200:]}


def stop(name, who='cli', force=False, collect=True):
    reg = registry(); s = reg.get(name)
    if not s: raise KeyError(f'no service {name}')
    if s.get('core') and not force: raise PermissionError(f'{name} is core: locked (on at boot, never stopped by vmctl)')
    with _op_lock:
        if s['kind'] == 'docker' or s.get('stop'):
            res = run(s['stop'])
        else:
            res = run(_units_cmd(s, 'stop'))
        with State() as d:
            d['manual'].pop(name, None); d['auto'].pop(name, None)
            d['leases'] = [l for l in d['leases'] if l['service'] != name]
        log(who, 'stop', name, 'ok' if res[0] == 0 else f'FAILED {res[1][-300:]}')
        if collect: gc(who)
        return {'name': name, 'running': states(reg)[name]}


def restart(name, who='cli', gui=False):
    s = registry()[name]
    if s.get('core'): raise PermissionError(f'{name} is core: locked')
    stop(name, who, collect=False); return start(name, who, gui)


def gc(who='gc'):
    """Stop what a dependency or a lease started and nobody needs now (never what was started by hand or from outside)."""
    with _op_lock:
        return _gc(who)


def _gc(who):
    reg = registry(); stopped = []
    for _ in range(3):                                    # a stopped service may free its own deps
        st = states(reg); d = read_state(); now = time.time()
        needed = {dep for n, s in reg.items() if st[n] for dep in s.get('deps', [])}
        leased = {l['service'] for l in d['leases'] if l['until'] > now}
        victims = [n for n in d['auto'] if st.get(n) and n not in needed and n not in leased
                   and not d['manual'].get(n) and not reg.get(n, {}).get('core')]
        gone = [n for n in d['auto'] if not st.get(n)]
        if gone:
            with State() as dd:
                for n in gone: dd['auto'].pop(n, None)
        if not victims: break
        for n in victims:
            stop(n, who=f'{who} (not needed)', collect=False); stopped.append(n)
    return stopped


# ---- leases ----
def lease(name, minutes, who='cli', gui=False):
    reg = registry()
    if name not in reg: raise KeyError(f'no service {name}')
    was = states(reg)[name]
    if not was:
        start(name, who=who, gui=gui, manual=False)
        with State() as d: d['auto'][name] = True
    l = dict(id=uuid.uuid4().hex[:12], service=name, who=who, since=time.time(), until=time.time() + 60 * float(minutes))
    with State() as d: d['leases'].append(l)
    log(who, f'lease {float(minutes):g} min', name, l['id'])
    return l


def release(lid, who='cli'):
    with State() as d:
        ls = [l for l in d['leases'] if l['id'] == lid]
        d['leases'] = [l for l in d['leases'] if l['id'] != lid]
    if not ls: raise KeyError(f'no lease {lid}')
    log(who, 'release', ls[0]['service'], lid)
    return {'released': lid, 'stopped': gc(who)}


def renew(lid, minutes, who='cli'):
    with State() as d:
        for l in d['leases']:
            if l['id'] == lid:
                l['until'] = time.time() + 60 * float(minutes); return dict(l)
    raise KeyError(f'no lease {lid}')


def expire():
    now = time.time()
    with State() as d:
        old = [l for l in d['leases'] if l['until'] <= now]
        d['leases'] = [l for l in d['leases'] if l['until'] > now]
    for l in old: log('lease-timer', 'expired', l['service'], l['id'])
    return gc('lease-timer') if old else []


def idle_stop(reg, st):
    """Optional per service: idle_stop_minutes. Idle = no lease, not started by hand, X input idle that long."""
    cand = [n for n, s in reg.items() if s.get('idle_stop_minutes') and st.get(n) and not s.get('core')]
    if not cand: return
    try:
        from Xlib import display
        from Xlib.ext import screensaver  # noqa: F401
        dpy = display.Display(ENV['DISPLAY']); idle = dpy.screen().root.screensaver_query_info().idle / 1000.0; dpy.close()
    except Exception:
        return
    d = read_state(); leased = {l['service'] for l in d['leases']}
    for n in cand:
        if n not in leased and not d['manual'].get(n) and idle > 60 * reg[n]['idle_stop_minutes']:
            stop(n, who=f'idle {idle / 60:.0f} min')


# ---- HTTP ----
def token():
    if not os.path.exists(TOKEN_FILE):
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, secrets.token_urlsafe(32).encode()); os.close(fd)
    return open(TOKEN_FILE).read().strip()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass                     # no access log: the token travels in a header

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def authed(self):
        t = self.headers.get('X-Mantra-Token') or (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
        if t and secrets.compare_digest(t, TOKEN):
            return True
        self.reply(401, {'ok': False, 'error': 'wrong or missing token'}); return False

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        try: return json.loads(self.rfile.read(n) or b'{}') if n else {}
        except Exception: return {}

    def do_GET(self):
        p = self.path.split('?')[0].rstrip('/')
        if p == '/health':
            return self.reply(200, {'ok': True, 'service': 'vmctl', 'version': VERSION})
        if not self.authed(): return
        try:
            if p == '/services':
                return self.reply(200, {'ok': True, 'services': describe()})
            if p.startswith('/services/'):
                n = p.split('/')[2]; s = [x for x in describe() if x['name'] == n]
                return self.reply(200 if s else 404, {'ok': bool(s), 'service': s[0] if s else None})
            if p == '/leases':
                return self.reply(200, {'ok': True, 'leases': [l for l in read_state()['leases'] if l['until'] > time.time()]})
            if p == '/log':
                return self.reply(200, {'ok': True, 'log': open(LOG).read().splitlines()[-100:] if os.path.exists(LOG) else []})
        except Exception as e:
            return self.reply(500, {'ok': False, 'error': str(e)})
        self.reply(404, {'ok': False, 'error': 'unknown path'})

    def do_DELETE(self):
        if not self.authed(): return
        p = self.path.split('?')[0].rstrip('/').split('/')
        if len(p) == 3 and p[1] == 'leases':
            return self._do(lambda: release(p[2], who=self._who({})))
        self.reply(404, {'ok': False, 'error': 'unknown path'})

    def _who(self, b):
        return f"{(b.get('who') or 'api')[:40]}@{self.client_address[0]}"

    def _do(self, fn):
        try:
            return self.reply(200, {'ok': True, 'result': fn()})
        except KeyError as e:
            return self.reply(404, {'ok': False, 'error': str(e).strip("'")})
        except PermissionError as e:
            return self.reply(403, {'ok': False, 'error': str(e)})
        except Exception as e:
            return self.reply(500, {'ok': False, 'error': str(e)})

    def do_POST(self):
        if not self.authed(): return
        p = self.path.split('?')[0].rstrip('/').split('/'); b = self.body(); who = self._who(b)
        if len(p) == 4 and p[1] == 'services':
            n, verb = p[2], p[3]
            if verb == 'start': return self._do(lambda: start(n, who, gui=bool(b.get('gui'))))
            if verb == 'stop': return self._do(lambda: stop(n, who))
            if verb == 'restart': return self._do(lambda: restart(n, who, gui=bool(b.get('gui'))))
            if verb == 'lease': return self._do(lambda: lease(n, b.get('minutes', 30), who, gui=bool(b.get('gui'))))
        if len(p) == 4 and p[1] == 'leases':
            if p[3] == 'release': return self._do(lambda: release(p[2], who))
            if p[3] == 'renew': return self._do(lambda: renew(p[2], b.get('minutes', 30), who))
        if p == ['', 'gc']: return self._do(lambda: gc(who))
        self.reply(404, {'ok': False, 'error': 'unknown path'})


def snapshot_loop():
    n = 0
    while True:
        try:
            reg = registry(); st = states(reg)
            tmp = SNAPSHOT + '.tmp'
            json.dump({'at': time.time(), 'services': [dict(name=k, short=reg[k]['short'], core=bool(reg[k].get('core')), running=v,
                                                            bar=reg[k].get('bar', True))
                                                       for k, v in st.items()]}, open(tmp, 'w'))
            os.replace(tmp, SNAPSHOT)
            n += 1
            if n % 6 == 0:                                 # every ~30 s: leases that ended, idle services
                expire(); idle_stop(reg, st)
        except Exception as e:
            log('snapshot', 'error', '-', str(e)[:200])
        time.sleep(5)


VERSION = 1
TOKEN = None


def serve():
    global TOKEN
    TOKEN = token()
    host = os.environ.get('VMCTL_HOST') or conf().get('VNC_IP', '100.102.86.30')
    for _ in range(90):                                   # at boot the Tailscale address comes a little later
        try:
            srv = ThreadingHTTPServer((host, PORT), H); break
        except OSError:
            time.sleep(2)
    else:
        sys.exit(f'cannot bind {host}:{PORT}')
    threading.Thread(target=snapshot_loop, daemon=True).start()
    log('server', 'serve', '-', f'{host}:{PORT}')
    srv.serve_forever()


def main(a):
    if not a or a[0] in ('-h', '--help', 'help'): print(__doc__); return 0
    cmd, rest = a[0], a[1:]
    who = os.environ.get('VMCTL_WHO', 'cli')
    try:
        if cmd == 'serve': serve()
        elif cmd == 'list':
            for s in describe():
                ls = f"  leases {len(s['leases'])}" if s['leases'] else ''
                print(f"{'●' if s['running'] else '○'} {s['name']:<15} {s['short']:<8} {'CORE ' if s['core'] else '     '}"
                      f"{'running' if s['running'] else 'stopped'}{' (by hand)' if s['manual'] and s['running'] else ''}{ls}  {s['title']}")
        elif cmd == 'status':
            ds = describe(); print(json.dumps([s for s in ds if not rest or s['name'] == rest[0]], indent=1))
        elif cmd == 'start':
            auto = '--auto' in rest                       # as a dependency (chromium-vm-phone starting docker): gc may stop it
            if auto and states()[rest[0]]:                # already running: an --auto call changes nothing
                print(json.dumps({'name': rest[0], 'running': True, 'note': 'already running'})); return 0
            r = start(rest[0], who, gui='--gui' in rest, manual=not auto)
            if auto:
                with State() as d: d['auto'][rest[0]] = True
            print(json.dumps(r))
        elif cmd == 'stop': print(json.dumps(stop(rest[0], who, force='--force-core' in rest)))
        elif cmd == 'restart': print(json.dumps(restart(rest[0], who, gui='--gui' in rest)))
        elif cmd == 'lease': print(json.dumps(lease(rest[0], rest[1] if len(rest) > 1 else 30, rest[2] if len(rest) > 2 else who)))
        elif cmd == 'release': print(json.dumps(release(rest[0], who)))
        elif cmd == 'renew': print(json.dumps(renew(rest[0], rest[1] if len(rest) > 1 else 30, who)))
        elif cmd == 'leases': print(json.dumps([l for l in read_state()['leases'] if l['until'] > time.time()], indent=1))
        elif cmd == 'gc': print(json.dumps(gc(who)))
        elif cmd == 'log': print('\n'.join(open(LOG).read().splitlines()[-int(rest[0] if rest else 30):]))
        else: print(__doc__); return 2
    except (KeyError, PermissionError, RuntimeError) as e:
        print(f'vmctl: {e}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
