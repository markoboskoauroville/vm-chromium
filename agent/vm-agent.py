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
VERSION = 4
ENV = dict(os.environ, DISPLAY=DISPLAY)

def run(cmd, data=None, timeout=15):
    return subprocess.run(cmd, input=data, capture_output=True, env=ENV, timeout=timeout).stdout

# ---- Chrome DevTools ---------------------------------------------------------------------------------------------
def tabs():
    return [t for t in json.load(urllib.request.urlopen(CDP + '/json', timeout=5)) if t.get('type') == 'page']

def tab(match=None):
    ts = tabs()
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
                lambda a: json.load(urllib.request.urlopen(urllib.request.Request(CDP + '/json/new?' + urllib.parse.quote(a['url'], safe=':/?&=#'), method='PUT'), timeout=10))['id']),
  'page_text': ('the visible text of a tab (first matching url/title, else the first tab)', {'tab': 'str', 'max': 'int'},
                lambda a: (cdp_eval('document.body.innerText', a.get('tab')) or '')[-int(a.get('max', 20000)):]),
  'eval':      ('runs JavaScript in a tab, returns the value', {'js': 'str', 'tab': 'str'}, lambda a: cdp_eval(a['js'], a.get('tab'))),
  'claude_ask':('writes a message into the claude.ai tab, sends it, waits, returns the answer text', {'text': 'str', 'send': 'bool, default true', 'tab': 'url/title/id part, default claude.ai'},
                lambda a: claude_ask(a['text'], a.get('send', True), int(a.get('wait', 180)), a.get('tab', 'claude.ai'))),
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
            os.replace(p + '.part', p); self.reply(200, {'ok': True, 'result': {'path': p, 'bytes': n}})
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
    for _ in range(180):   # wait for the Tailscale address at boot
        try: S((HOST, PORT), H).serve_forever()
        except OSError: time.sleep(1)
