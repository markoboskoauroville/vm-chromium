#!/usr/bin/env python3
"""vm-agent: chromium-vm's remote door. Direct, cheap, two-way: clipboard, keys, files, Chrome (DevTools), claude.ai.

Listens on the Tailscale address only; X-Mantra-Token on every request except /health.
GET /health · GET /api · POST /api/<action> (JSON body) · PUT /files/<name> (raw body) · GET /files/<name>
"""
import base64, http.server, json, os, socketserver, subprocess, time, urllib.request, urllib.parse
import websocket  # python3-websocket

CONF = {}
for line in open('/etc/chromium-vm.conf'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); CONF[k] = v
HOST = CONF.get('VNC_IP', '100.102.86.30'); PORT = int(CONF.get('AGENT_PORT', '8890'))
TOKEN = open(os.path.expanduser('~/.config/chromium-vm/agent-token')).read().strip()
DISPLAY = ':' + CONF.get('DISPLAY_NUM', '1'); CDP = 'http://127.0.0.1:9222'
DOWNLOADS = os.path.expanduser('~/Downloads'); os.makedirs(DOWNLOADS, exist_ok=True)
VERSION = 9
ENV = dict(os.environ, DISPLAY=DISPLAY)

def run(cmd, data=None, timeout=15):
    return subprocess.run(cmd, input=data, capture_output=True, env=ENV, timeout=timeout).stdout

# ---- Chrome DevTools ---------------------------------------------------------------------------------------------
def tabs(frames=False):
    kinds = ('page', 'iframe') if frames else ('page',)
    return [t for t in json.load(urllib.request.urlopen(CDP + '/json', timeout=5)) if t.get('type') in kinds]

def tab(match=None):
    ts = tabs(frames=bool(match))     # a match may name a frame too (the Claude extension's panel is a claude.ai/cic frame)
    if match:
        ts = [t for t in ts if t['id'] == match or match in t['url'] or match.lower() in t['title'].lower()]
    if not ts: raise ValueError('no tab' + (f' matching {match!r}' if match else ''))
    return ts[0]

def cdp_eval(expr, match=None, await_promise=True):
    ws = websocket.create_connection(tab(match)['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
    try:
        ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                            'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise}}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == 1: break
    finally:
        ws.close()
    r = m.get('result', {})
    if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'].get('text', 'script error'))
    return r.get('result', {}).get('value')

def cdp_call(method, params, match=None):
    ws = websocket.create_connection(tab(match)['webSocketDebuggerUrl'], timeout=60, suppress_origin=True)
    try:
        ws.send(json.dumps({'id': 1, 'method': method, 'params': params}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == 1: break
    finally:
        ws.close()
    if 'error' in m: raise ValueError(m['error'].get('message', 'DevTools error'))
    return m.get('result', {})

def browser_call(method, params):
    url = json.load(urllib.request.urlopen(CDP + '/json/version', timeout=5))['webSocketDebuggerUrl']
    ws = websocket.create_connection(url, timeout=60, suppress_origin=True)
    try:
        ws.send(json.dumps({'id': 1, 'method': method, 'params': params}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == 1: break
    finally:
        ws.close()
    if 'error' in m: raise ValueError(m['error'].get('message', 'DevTools error'))
    return m.get('result', {})

def capture(a):
    """A screenshot of a region of a tab (CSS px), lossless PNG, saved under ~/Downloads (so it goes to Drive)."""
    clip = {k: float(a[k]) for k in ('x', 'y', 'w', 'h')}
    r = cdp_call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True,
                 'clip': {'x': clip['x'], 'y': clip['y'], 'width': clip['w'], 'height': clip['h'], 'scale': float(a.get('scale', 1))}},
                 a.get('tab'))
    rel = os.path.normpath(a['save']).lstrip('/')
    if rel.startswith('..'): raise ValueError('save must stay inside ~/Downloads')
    p = os.path.join(DOWNLOADS, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    data = base64.b64decode(r['data'])
    with open(p + '.part', 'wb') as f: f.write(data)
    os.replace(p + '.part', p)
    return {'path': p, 'bytes': len(data)}

def vm_status():
    growing = []
    for root, dirs, files in os.walk(DOWNLOADS):
        for f in files:
            if f.endswith('.crdownload'):
                growing.append({'name': f[:-len('.crdownload')], 'bytes': os.path.getsize(os.path.join(root, f))})
    with jlock:
        j = jload() or {'files': {}}
    queue = sum(1 for f in j['files'].values() if f.get('gdrive') in ('waiting', 'failed', 'sending'))
    return {'moving': STATE.get('moving', ''), 'downloading': growing, 'drive_queue': queue}

# claude.ai (2.11.2026): the composer is a contenteditable tiptap/ProseMirror; answers are [data-testid=assistant-message],
# a streaming one sits in [data-is-streaming=true].
CLAUDE_JS = r'''
(async (msg, send) => {
  const box = document.querySelector('div[contenteditable="true"].ProseMirror, div[contenteditable="true"]');
  if (!box) return {error: 'no message box on this page'};
  box.focus();
  document.execCommand('selectAll'); document.execCommand('insertText', false, msg);
  if (!send) return {typed: msg.length};
  const before = document.querySelectorAll('[data-testid="assistant-message"]').length;
  await new Promise(r => setTimeout(r, 300));
  const btn = document.querySelector('button[aria-label="Send message"], button[aria-label="Send Message"]');
  if (btn) btn.click(); else box.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
  return {sent: true, before};
})
'''
CLAUDE_LAST = r'''(() => { const a = document.querySelectorAll('[data-testid="assistant-message"]');
  const busy = !!document.querySelector('[data-is-streaming="true"], button[aria-label="Stop response"], button[aria-label="Stop Response"]');
  const e = a.length ? a[a.length-1] : null;
  const body = e && (e.querySelector('.prose') || e);   // the answer only: no sr-only header, no "just now"
  return {n: a.length, text: body ? body.innerText.trim() : '', busy}; })()'''

def claude_ask(text, send=True, wait=180, match='claude.ai'):
    tid = tab(match)['id']   # one tab for the whole exchange (its url changes when a new chat starts)
    r = cdp_eval(f'{CLAUDE_JS}({json.dumps(text)}, {json.dumps(send)})', tid)
    if not send or 'error' in r: return r
    before, t0, last, stable = r['before'], time.time(), None, 0
    while time.time() - t0 < wait:
        time.sleep(1.5)
        s = cdp_eval(CLAUDE_LAST, tid)
        if s['n'] > before and not s['busy']:
            stable = stable + 1 if s['text'] == last else 0
            if stable >= 2: return {'answer': s['text']}
        last = s['text']
    return {'answer': last or '', 'timeout': True}

# ---- Chromium Downloads: every finished download, numbered, for the Mac and for Google Drive ----------------
# Marko, 2.11.2026: "In my Download folder ... a folder called Chromium Downloads ... everything Chromium does will
# just land automatically. At the same time, one copy will be held in my G Drive ... the folder has the same name".
import threading
JOURNAL = os.path.expanduser('~/.config/chromium-vm/downloads.json')
GDRIVE = 'gdrive:Chromium Downloads'          # rclone remote, scope drive.file, account of the Chrome profile
jlock = threading.Lock()
STATE = {'moving': ''}     # what is moving right now (the health line will read it)
PARTIAL = ('.crdownload', '.part', '.tmp', '.download')

def jload():
    try: return json.load(open(JOURNAL))
    except Exception: return None

def jsave(j):
    tmp = JOURNAL + '.tmp'; json.dump(j, open(tmp, 'w'), indent=1); os.replace(tmp, JOURNAL)

def from_mac(name, size):
    """A file dropped from the Mac (PUT /files): never sent back as a download."""
    with jlock:
        j = jload() or {'seq': 0, 'files': {}}
        j['files'][name] = {'size': size, 'mtime': os.path.getmtime(os.path.join(DOWNLOADS, name)), 'from_mac': True}
        jsave(j)

def watch_downloads():
    seen = {}                                   # name -> (size, mtime) at the last look: a file is done when stable
    with jlock:
        if jload() is None:                     # first start: what is already there is the past, not new downloads
            jsave({'seq': 0, 'files': {n: {'size': os.path.getsize(os.path.join(DOWNLOADS, n)), 'baseline': True}
                                       for n in os.listdir(DOWNLOADS) if os.path.isfile(os.path.join(DOWNLOADS, n))}})
    while True:
        time.sleep(2)
        try:
            names = []
            for root, dirs, files in os.walk(DOWNLOADS):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if not f.startswith('.') and not f.endswith(PARTIAL):
                        names.append(os.path.relpath(os.path.join(root, f), DOWNLOADS))
            with jlock:
                j = jload()
                for n in names:
                    st = os.stat(os.path.join(DOWNLOADS, n)); now = (st.st_size, st.st_mtime)
                    old = j['files'].get(n)
                    if old and old.get('size') == st.st_size and abs(old.get('mtime', st.st_mtime) - st.st_mtime) < 1:
                        continue                # known and unchanged
                    if seen.get(n) != now: seen[n] = now; continue      # still growing: look again
                    if old and old.get('from_mac') and old.get('size') == st.st_size: continue
                    j['seq'] += 1
                    j['files'][n] = {'size': st.st_size, 'mtime': st.st_mtime, 'seq': j['seq'], 'gdrive': 'waiting'}
                    jsave(j)
            gdrive_pending()
        except Exception as e:
            print('watch_downloads:', e, flush=True)

def gdrive_pending():
    if not os.path.exists(os.path.expanduser('~/.config/rclone/rclone.conf')): return
    with jlock:
        todo = [n for n, f in (jload() or {'files': {}})['files'].items() if f.get('gdrive') in ('waiting', 'failed', 'sending')]
    for n in todo:
        p = os.path.join(DOWNLOADS, n)
        if not os.path.exists(p):
            with jlock:
                j = jload(); j['files'][n]['gdrive'] = 'gone'; jsave(j)
            continue
        with jlock:
            j = jload(); j['files'][n]['gdrive'] = 'sending'; jsave(j)
        STATE['moving'] = f'→ Google Drive: {n}'
        # rclone 1.60 sometimes stays after the upload is done (2.11.2026): a deadline by size, then a check.
        limit = 120 + os.path.getsize(p) // 200_000
        try:
            ok = subprocess.run(['rclone', 'copyto', '--contimeout', '30s', '--timeout', '120s', '--retries', '3',
                                 p, f'{GDRIVE}/{n}'], capture_output=True, timeout=limit).returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        if not ok:   # it may have landed anyway: same size on Drive counts as done
            try:
                ls = json.loads(subprocess.run(['rclone', 'lsjson', f'{GDRIVE}/{n}'], capture_output=True, timeout=60).stdout or b'[]')
                ok = bool(ls) and ls[0].get('Size') == os.path.getsize(p)
            except Exception:
                ok = False
        with jlock:
            j = jload(); f = j['files'].get(n)
            STATE['moving'] = ''
            if f:
                f['gdrive'] = 'done' if ok else 'failed'
                if ok:   # Drive has it: gone from the VM (Marko, 2.11.2026: "transferred to the drive ... delete it")
                    try: os.remove(p); f['deleted'] = True
                    except OSError: pass
                    d = os.path.dirname(p)
                    while d != DOWNLOADS and not os.listdir(d): os.rmdir(d); d = os.path.dirname(d)
                jsave(j)

def downloads_since(seq):
    with jlock:
        j = jload() or {'seq': 0, 'files': {}}
    new = sorted(({'name': n, **f} for n, f in j['files'].items() if f.get('seq', 0) > seq), key=lambda f: f['seq'])
    return {'seq': j['seq'], 'files': new}

# ---- actions ---------------------------------------------------------------------------------------------------
ACTIONS = {
  'clip_get':  ('the VM clipboard as text', {}, lambda a: run(['xclip', '-selection', 'clipboard', '-o']).decode(errors='replace')),
  'clip_set':  ('puts text on the VM clipboard', {'text': 'str'},
                lambda a: (subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE, env=ENV,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).communicate(a['text'].encode()), 'ok')[1]),
  'type':      ('types text into the focused window', {'text': 'str'},
                lambda a: (run(['xdotool', 'type', '--delay', '12', '--file', '-'], a['text'].encode(), 120), len(a['text']))[1]),
  'key':       ('presses keys, xdotool names: Return, ctrl+v, ctrl+l', {'keys': 'str'},
                lambda a: (run(['xdotool', 'key'] + a['keys'].split()), 'ok')[1]),
  'ls':        ('files in ~/Downloads on the VM', {}, lambda a: sorted(os.listdir(DOWNLOADS))),
  'shot':      ('a JPEG of the screen (base64), scaled; the last resort', {'scale': 'int percent, default 50'},
                lambda a: base64.b64encode(run(['sh', '-c', f'xwd -root -silent | convert xwd:- -resize {int(a.get("scale", 50))}% -quality 70 jpg:-'], timeout=30)).decode()),
  'tabs':      ('Chrome tabs: title and url', {}, lambda a: [{'title': t['title'], 'url': t['url']} for t in tabs()]),
  'open':      ('opens a url in a new tab, returns its id', {'url': 'str'},
                lambda a: json.load(urllib.request.urlopen(urllib.request.Request(CDP + '/json/new?' + urllib.parse.quote(a['url'], safe=''), method='PUT'), timeout=10))['id']),
  'page_text': ('the visible text of a tab (first matching url/title, else the first tab)', {'tab': 'str', 'max': 'int'},
                lambda a: (cdp_eval('document.body.innerText', a.get('tab')) or '')[-int(a.get('max', 20000)):]),
  'eval':      ('runs JavaScript in a tab, returns the value', {'js': 'str', 'tab': 'str'}, lambda a: cdp_eval(a['js'], a.get('tab'))),
  'claude_ask':('writes a message into the claude.ai tab, sends it, waits, returns the answer text', {'text': 'str', 'send': 'bool, default true', 'tab': 'url/title/id part, default claude.ai'},
                lambda a: claude_ask(a['text'], a.get('send', True), int(a.get('wait', 180)), a.get('tab', 'claude.ai'))),
  'downloads': ('finished Chrome downloads after number `since` (0 = all), with their Drive state', {'since': 'int'},
                lambda a: downloads_since(int(a.get('since', 0)))),
  'cdp':       ('any DevTools method on a tab (or the browser when tab is "browser")', {'method': 'str', 'params': 'obj', 'tab': 'str'},
                lambda a: browser_call(a['method'], a.get('params', {})) if a.get('tab') == 'browser' else cdp_call(a['method'], a.get('params', {}), a.get('tab'))),
  'status':    ('what is moving now: Chrome downloads in progress, the Drive copy, the Drive queue', {},
                lambda a: vm_status()),
  'capture':   ('screenshot of a tab region (CSS px x,y,w,h, scale) saved as PNG under ~/Downloads/<save>; goes to Drive', 
                {'tab': 'str', 'x': 'num', 'y': 'num', 'w': 'num', 'h': 'num', 'scale': 'num', 'save': 'relative path'}, capture),
  'claude_last':('the last Claude answer on a claude.ai tab', {'tab': 'str'}, lambda a: cdp_eval(CLAUDE_LAST, a.get('tab', 'claude.ai'))),
}

class H(http.server.BaseHTTPRequestHandler):
    def reply(self, code, obj, raw=None, ctype='application/json'):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def authed(self):
        if self.headers.get('X-Mantra-Token') == TOKEN: return True
        self.reply(401, {'ok': False, 'error': 'wrong or missing token'}); return False
    def fname(self):
        n = os.path.basename(urllib.parse.unquote(self.path[len('/files/'):]))
        if not n or n.startswith('.'): raise ValueError('bad file name')
        return os.path.join(DOWNLOADS, n)
    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, {'app': 'chromium-vm-agent', 'name': 'chromium-vm agent', 'version': VERSION, 'pid': os.getpid()})
        if not self.authed(): return
        if self.path == '/api':
            return self.reply(200, {'app': 'chromium-vm-agent', 'version': VERSION,
                                    'actions': [{'name': k, 'does': v[0], 'args': v[1]} for k, v in ACTIONS.items()]})
        if self.path.startswith('/files/'):
            try:
                with open(self.fname(), 'rb') as f: return self.reply(200, None, f.read(), 'application/octet-stream')
            except Exception as e: return self.reply(404, {'ok': False, 'error': str(e)})
        self.reply(404, {'ok': False, 'error': 'no such path'})
    def do_PUT(self):
        if not self.authed(): return
        try:
            p, n, left = self.fname(), 0, int(self.headers.get('Content-Length', 0))
            with open(p + '.part', 'wb') as f:
                while left:
                    b = self.rfile.read(min(left, 1 << 20)); f.write(b); left -= len(b); n += len(b)
            os.replace(p + '.part', p); from_mac(os.path.basename(p), n); self.reply(200, {'ok': True, 'result': {'path': p, 'bytes': n}})
        except Exception as e: self.reply(400, {'ok': False, 'error': str(e)})
    def do_POST(self):
        if not self.authed(): return
        name = self.path[len('/api/'):] if self.path.startswith('/api/') else ''
        if name not in ACTIONS: return self.reply(404, {'ok': False, 'error': f'no action {name!r}; see /api'})
        try:
            a = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            self.reply(200, {'ok': True, 'result': ACTIONS[name][2](a)})
        except Exception as e: self.reply(500, {'ok': False, 'error': f'{type(e).__name__}: {e}'})
    def log_message(self, *a): pass

class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True

if __name__ == '__main__':
    threading.Thread(target=watch_downloads, daemon=True).start()
    for _ in range(180):   # wait for the Tailscale address at boot
        try: S((HOST, PORT), H).serve_forever()
        except OSError: time.sleep(1)
