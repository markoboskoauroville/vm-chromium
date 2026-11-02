#!/usr/bin/env python3
"""vm-router: one door to chromium-vm for many sessions at once, so nobody gets another session's picture.

Marko, 2.11.2026: "please build the router for using virtual machines. If multiple sessions are using it, it should be
seamless, not getting one image from the other session and so on. VM router for this machine."

Every Claude Code session or job talks to this router on the Mac (127.0.0.1:8891, MANTRA_PORTS name `vm-router`)
instead of vm-agent (100.102.86.30:8890) directly. The router forwards to vm-agent and adds:

  sessions (leases)   POST /session {name, account, folder}: the same name gets the same session back. A session owns
                      its tabs; a call without a tab goes to the session's own first tab, never "the first matching
                      tab"; another session's tab (or a tab nobody owns) is refused with 403.
  accounts            the Google account (gemini /u/N) is stored with the session; a gemini url without /u/ is opened
                      on the session's account, a navigation to another /u/M is refused.
  one at a time       clipboard, type, key, shot (whatever depends on focus or a shared buffer) take the global lock:
                      the session's tab is brought to the front, the action runs, the lock is released. Several steps
                      that belong together (clip_set + key ctrl+v) go as one POST /s/<sid>/global {steps}.
  namespaced output   capture saves are forced under the session's folder (default Router/<name>/), files put from the
                      Mac get the session's prefix, downloads are attributed by folder, and a Chrome download that
                      lands in ~/Downloads is attributed by POST /s/<sid>/expect_download (one claim at a time).
  pacing              image requests on one Google account keep a minimum gap (config image_gap_s, default 40 s)
                      whichever session makes them: paste_files on a gemini tab and POST /s/<sid>/pace both wait.
  log and status      GET /status, GET /events?since=N; ~/.config/vm-router/events.jsonl.

    python3 vm-router.py [--port N]        (vmr start runs it detached; the app VM Router (Mantra) shows it)
"""
import collections, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
import http.server, socketserver

VERSION = 1
AGENT = 'http://100.102.86.30:8890'
TOKEN_FILE = os.path.expanduser('~/Downloads/API/chromium-vm-agent.txt')
HOME = os.path.expanduser('~/.config/vm-router'); os.makedirs(HOME, exist_ok=True)
STATE_FILE, CONF_FILE = os.path.join(HOME, 'state.json'), os.path.join(HOME, 'config.json')
EVENTS_FILE, PID_FILE = os.path.join(HOME, 'events.jsonl'), os.path.join(HOME, 'router.pid')
DEFAULT_CONF = {'image_gap_s': 40, 'account_gap_s': {}, 'lease_idle_h': 12, 'lock_timeout_s': 120,
                'activate_settle_s': 0.35, 'expect_download_s': 120}

TAB_ACTIONS = {'eval', 'page_text', 'paste_files', 'capture', 'claude_ask', 'claude_last', 'cdp'}
GLOBAL_ACTIONS = {'clip_get', 'clip_set', 'type', 'key', 'shot'}
FOCUS_ACTIONS = {'type', 'key'}                      # these go to whatever has focus: the session's tab first
FREE_ACTIONS = {'ls', 'status', 'downloads'}
BROWSER_CDP_OK = {'Browser.getVersion', 'SystemInfo.getInfo'}
TAB_CDP_REFUSED = ('Target.', 'Browser.')            # a page session must not reach other targets


def token():
    return open(TOKEN_FILE).read().strip()


def agent(action, timeout=300, **a):
    r = urllib.request.Request(f'{AGENT}/api/{action}', data=json.dumps(a).encode(), method='POST',
                               headers={'X-Mantra-Token': token(), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f: j = json.load(f)
    except urllib.error.HTTPError as e:
        try: j = json.load(e)
        except Exception: raise RouterError(502, f'vm-agent HTTP {e.code}')
    except urllib.error.URLError as e:
        raise RouterError(502, f'chromium-vm not reachable ({e.reason}); is Tailscale on?')
    if not j.get('ok'): raise RouterError(502, 'vm-agent: ' + str(j.get('error')))
    return j['result']


def agent_raw(method, path, raw=None, timeout=3600):
    r = urllib.request.Request(AGENT + path, data=raw, method=method, headers={'X-Mantra-Token': token()})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f: return f.status, f.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
    except urllib.error.URLError as e: raise RouterError(502, f'chromium-vm not reachable ({e.reason})')


class RouterError(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code = code


def slug(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', s).strip('-')[:60] or 'session'


# ---- state ----------------------------------------------------------------------------------------------------------
LOCK = threading.RLock()                 # guards S (the sessions) and the files
S = {'sessions': {}, 'last_image': {}, 'seq': 0}
EVENTS = collections.deque(maxlen=500); EV_SEQ = [0]
CONF = dict(DEFAULT_CONF)


def load():
    global CONF
    try: S.update(json.load(open(STATE_FILE)))
    except Exception: pass
    try: CONF = {**DEFAULT_CONF, **json.load(open(CONF_FILE))}
    except Exception:
        json.dump(DEFAULT_CONF, open(CONF_FILE, 'w'), indent=1)
    try:
        for line in open(EVENTS_FILE).readlines()[-300:]:
            e = json.loads(line); EVENTS.append(e); EV_SEQ[0] = max(EV_SEQ[0], e['n'])
    except Exception: pass


def save():
    with LOCK:
        tmp = STATE_FILE + '.tmp'; json.dump(S, open(tmp, 'w'), indent=1); os.replace(tmp, STATE_FILE)


def event(sid, what, **kw):
    with LOCK:
        EV_SEQ[0] += 1
        name = S['sessions'].get(sid, {}).get('name', sid or 'router')
        e = {'n': EV_SEQ[0], 't': time.time(), 'session': name, 'what': what, **kw}
        EVENTS.append(e)
        with open(EVENTS_FILE, 'a') as f: f.write(json.dumps(e, ensure_ascii=False) + '\n')
        if sid in S['sessions']:
            s = S['sessions'][sid]; s['last'] = what; s['last_t'] = e['t']; s['actions'] = s.get('actions', 0) + 1
    return e


# ---- the global lock: one focus/clipboard action at a time, in order ----------------------------------------------
class Queue:
    def __init__(self):
        self.cv = threading.Condition(); self.holder = None; self.since = 0; self.waiting = []

    def acquire(self, who, what, timeout):
        me = (who, what, time.time())
        with self.cv:
            self.waiting.append(me)
            ok = self.cv.wait_for(lambda: self.holder is None and self.waiting[0] is me, timeout)
            self.waiting.remove(me)
            if not ok:
                self.cv.notify_all(); raise RouterError(503, f'the global lock stayed busy ({self.holder}) for {timeout} s')
            self.holder, self.since = (who, what), time.time()

    def release(self):
        with self.cv: self.holder = None; self.cv.notify_all()

    def view(self):
        with self.cv:
            return {'holder': self.holder and {'session': self.holder[0], 'what': self.holder[1],
                                                'for_s': round(time.time() - self.since, 1)},
                    'waiting': [{'session': w[0], 'what': w[1], 'for_s': round(time.time() - w[2], 1)} for w in self.waiting]}


FOCUS = Queue()        # clipboard, type, key, shot
DOWNLOAD = Queue()     # one "the next download is mine" claim at a time
PACE = threading.Lock()


# ---- tabs ------------------------------------------------------------------------------------------------------------
def targets():
    r = agent('cdp', method='Target.getTargets', params={}, tab='browser', timeout=30)
    return [t for t in r.get('targetInfos', []) if t.get('type') == 'page']


def owner_of(tid):
    for sid, s in S['sessions'].items():
        if tid in s.get('tabs', []): return sid
    return None


def own_tab(sid, want=None):
    """The exact DevTools id of one of this session's tabs: `want` may be an id, a url or a title part of an own tab;
    none = the session's first tab. Anything else is refused."""
    s = S['sessions'][sid]; mine = s.get('tabs', [])
    if want and want in mine: return want
    if want:
        o = owner_of(want)
        if o: raise RouterError(403, f'tab {want[:8]}… belongs to session {S["sessions"][o]["name"]!r}')
        if re.fullmatch(r'[0-9A-F]{32}', want): raise RouterError(403, f'tab {want[:8]}… is not this session\'s')
    if not mine: raise RouterError(409, 'this session has no tab yet: POST /s/<sid>/open {url} (or adopt one)')
    if not want: return mine[0]
    for t in targets():
        if t['targetId'] in mine and (want in t['url'] or want.lower() in t['title'].lower()): return t['targetId']
    raise RouterError(404, f'no tab of this session matches {want!r}')


def account_url(sid, url):
    """gemini.google.com/app -> gemini.google.com/u/N/app for the session's account; another /u/M is refused."""
    acc = S['sessions'][sid].get('account')
    if acc is None or not url: return url
    p = urllib.parse.urlsplit(url)
    if not p.netloc.endswith('google.com'): return url
    m = re.match(r'^/u/(\d+)(/.*)?$', p.path)
    if m:
        if int(m.group(1)) != int(acc):
            raise RouterError(403, f'this session works on account /u/{acc}, not /u/{m.group(1)}')
        return url
    if p.netloc in ('gemini.google.com', 'mail.google.com', 'drive.google.com', 'photos.google.com'):
        path = p.path if p.path.startswith('/') else '/' + p.path
        if p.netloc == 'mail.google.com' and path.startswith('/mail'): path = path[5:] or '/'
        base = '/mail/u/' if p.netloc == 'mail.google.com' else '/u/'
        return urllib.parse.urlunsplit((p.scheme, p.netloc, f'{base}{acc}{path}', p.query, p.fragment))
    return url


def activate(tid):
    agent('cdp', method='Target.activateTarget', params={'targetId': tid}, tab='browser', timeout=30)
    time.sleep(CONF['activate_settle_s'])


# ---- pacing per Google account ---------------------------------------------------------------------------------------
def pace(sid, why='image'):
    s = S['sessions'][sid]; acc = 'none' if s.get('account') is None else str(s['account'])
    gap = float(CONF['account_gap_s'].get(acc, CONF['image_gap_s']))
    waited = 0.0
    while True:
        with PACE:
            last = S['last_image'].get(acc, 0); now = time.time(); left = last + gap - now
            if left <= 0:
                S['last_image'][acc] = now; s['next_ok'] = now + gap; save(); break
        s['pacing'] = round(left, 1); time.sleep(min(left, 2)); waited += min(left, 2)
    s['pacing'] = 0
    event(sid, f'pace {why}', account=acc, waited_s=round(waited, 1))
    return {'account': acc, 'waited_s': round(waited, 1), 'gap_s': gap}


# ---- the actions -----------------------------------------------------------------------------------------------------
def session_new(a):
    name = (a.get('name') or '').strip()
    if not name: raise RouterError(400, 'name is required (the Claude session name or the project)')
    with LOCK:
        sid = next((k for k, s in S['sessions'].items() if s['name'] == name), None)
        if sid is None:
            S['seq'] += 1; sid = f's{S["seq"]}-{slug(name)}'
            S['sessions'][sid] = {'name': name, 'tabs': [], 'created': time.time(), 'actions': 0,
                                  'folder': 'Router/' + slug(name), 'account': None, 'claims': []}
            fresh = True
        else: fresh = False
        s = S['sessions'][sid]
        if 'account' in a and a['account'] is not None: s['account'] = int(a['account'])
        if a.get('email'): s['email'] = a['email']
        if a.get('folder'):
            f = os.path.normpath(a['folder']).strip('/')
            if f.startswith('..'): raise RouterError(400, 'folder must stay inside ~/Downloads')
            s['folder'] = f
        s['last_t'] = time.time(); save()
    event(sid, 'session ' + ('new' if fresh else 'again'), account=s['account'], folder=s['folder'])
    if a.get('tab'): adopt(sid, {'tab': a['tab']})
    return {'session': sid, **S['sessions'][sid]}


def adopt(sid, a):
    tid = a['tab']
    if not any(t['targetId'] == tid for t in targets()): raise RouterError(404, f'no tab {tid}')
    with LOCK:
        o = owner_of(tid)
        if o and o != sid: raise RouterError(403, f'tab {tid[:8]}… belongs to session {S["sessions"][o]["name"]!r}')
        if tid not in S['sessions'][sid]['tabs']: S['sessions'][sid]['tabs'].append(tid)
        save()
    event(sid, 'adopt tab', tab=tid[:8]); return {'tab': tid}


def open_tab(sid, a):
    url = account_url(sid, a.get('url') or 'about:blank')
    # background: true never takes the front from another session's tab (Marko's VNC picture stays where it was)
    r = agent('cdp', method='Target.createTarget', params={'url': url, 'background': not a.get('front', False)},
              tab='browser', timeout=30)
    tid = r['targetId']
    with LOCK: S['sessions'][sid]['tabs'].append(tid); save()
    event(sid, 'open tab', tab=tid[:8], url=url[:120]); return {'tab': tid, 'url': url}


def close_tab(sid, a):
    tid = own_tab(sid, a.get('tab'))
    try: agent('cdp', method='Target.closeTarget', params={'targetId': tid}, tab='browser', timeout=30)
    except RouterError: pass
    with LOCK: S['sessions'][sid]['tabs'].remove(tid); save()
    event(sid, 'close tab', tab=tid[:8]); return {'closed': tid}


def release(sid, a):
    if a.get('close_tabs'):
        for t in list(S['sessions'][sid]['tabs']): close_tab(sid, {'tab': t})
    event(sid, 'release', tabs=len(S['sessions'][sid]['tabs']))
    with LOCK:
        s = S['sessions'].pop(sid); own = S.setdefault('owners', {})
        own[s['folder']] = s['name']; own[slug(s['name'])] = s['name']
        for c in s.get('claims', []): own[c] = s['name']
        save()
    return {'released': sid}


def forced_save(sid, save_path):
    folder = S['sessions'][sid]['folder']
    rel = os.path.normpath(save_path or f'capture-{int(time.time())}.png').lstrip('/')
    if rel.startswith('..'): raise RouterError(400, 'save must stay inside the session folder')
    return rel if rel.startswith(folder + '/') else f'{folder}/{rel}'


def run_global(sid, steps, label):
    """Steps that depend on focus or the shared clipboard, under the global lock, the session's tab in front."""
    name = S['sessions'][sid]['name']
    FOCUS.acquire(name, label, CONF['lock_timeout_s'])
    try:
        out, activated = [], False
        for st in steps:
            act, args = st['action'], {k: v for k, v in st.items() if k != 'action'}
            if act not in GLOBAL_ACTIONS | {'sleep', 'activate'}: raise RouterError(400, f'{act} is not a global action')
            if args.pop('dry', False): time.sleep(float(args.get('hold_s', 0.5))); out.append('dry'); continue
            if act == 'sleep': time.sleep(min(float(args.get('s', 0.3)), 10)); out.append('slept'); continue
            if act == 'activate': tid = own_tab(sid, args.get('tab')); activate(tid); activated = True; out.append(tid); continue
            if act in FOCUS_ACTIONS and not activated:
                activate(own_tab(sid, args.pop('tab', None))); activated = True
            args.pop('tab', None)
            out.append(agent(act, **args))
        event(sid, 'global ' + label)
        return out
    finally:
        FOCUS.release()


def expect_download(sid, a):
    """The next Chrome download that lands in ~/Downloads (root) belongs to this session. One claim at a time, so the
    attribution is never a guess: the lock is held until the file arrives or the time is up."""
    name = S['sessions'][sid]['name']; wait = float(a.get('seconds', CONF['expect_download_s']))
    DOWNLOAD.acquire(name, 'expect download', wait + 60)
    try:
        start = agent('downloads', since=0)['seq']
        event(sid, 'expect download', seconds=wait)
        t0 = time.time()
        while time.time() - t0 < wait:
            time.sleep(2)
            new = agent('downloads', since=start)['files']
            if new:
                f = new[0]
                with LOCK: S['sessions'][sid].setdefault('claims', []).append(f['name']); save()
                event(sid, 'download is mine', file=f['name']); return f
        event(sid, 'expect download: nothing came'); return {'timeout': True}
    finally:
        DOWNLOAD.release()


def owner_by_name(name):
    for sid, s in S['sessions'].items():
        if name.startswith(s['folder'] + '/') or name in s.get('claims', []) or name.startswith(slug(s['name']) + '__'):
            return s['name']
    for key, who in S.get('owners', {}).items():       # sessions already released keep their files
        if name == key or name.startswith(key + '/') or name.startswith(key + '__'): return who
    return None


# Gemini (2.11.2026): a result is an <img> inside <generated-image>; its src is blob: exactly like a pasted reference
# preview (inside user-query-file-preview), so results are told apart by closest('generated-image'), never by blob:.
GEMINI_STATE = '''(() => { const im = [...document.querySelectorAll('generated-image img')].filter(i => i.complete
  && i.naturalWidth >= 300 && !i.closest('[data-chromium-vm-overlay]'));
  const last = im.length ? im[im.length - 1] : null;
  return {n: im.length, w: last ? last.naturalWidth : 0, h: last ? last.naturalHeight : 0,
          busy: !!document.querySelector('[aria-label="Stop response"]'),
          tail: document.body.innerText.toLowerCase().slice(-600)}; })()'''


def gemini_wait(sid, a):
    """Waits on the session's Gemini tab until there are more results than `before` and Gemini is idle (default
    300 s: generation took over 3 minutes at times on 2.11.2026). Without `before`: the state now."""
    tid = own_tab(sid, a.get('tab'))
    st = agent('eval', js=GEMINI_STATE, tab=tid)
    if 'before' not in a: return st
    t0, wait = time.time(), float(a.get('wait', 300))
    while time.time() - t0 < wait:
        if st['n'] > int(a['before']) and not st['busy']:
            event(sid, 'gemini image', tab=tid[:8], waited_s=round(time.time() - t0)); return st
        time.sleep(4); st = agent('eval', js=GEMINI_STATE, tab=tid)
    return {**st, 'timeout': True}


def forward(sid, action, a):
    s = S['sessions'][sid]
    if action in ('gemini_state', 'gemini_wait'): return gemini_wait(sid, a if action == 'gemini_wait' else {k: v for k, v in a.items() if k != 'before'})
    if action == 'open': return open_tab(sid, a)
    if action == 'tabs':
        mine = set(s['tabs'])
        return [{'tab': t['targetId'], 'title': t['title'], 'url': t['url']} for t in targets() if t['targetId'] in mine]
    if action in FREE_ACTIONS:
        r = agent(action, **a)
        if action == 'downloads':
            for f in r['files']: f['session'] = owner_by_name(f['name'])
            if not a.get('all'): r['files'] = [f for f in r['files'] if f['session'] == s['name']]
        event(sid, action); return r
    if action in GLOBAL_ACTIONS: return run_global(sid, [{'action': action, **a}], action)[0]
    if action not in TAB_ACTIONS: raise RouterError(404, f'no action {action!r} through the router')
    if action == 'cdp' and a.get('tab') == 'browser':
        if a.get('method') not in BROWSER_CDP_OK:
            raise RouterError(403, f'browser-wide {a.get("method")} is the router\'s job (open/close/adopt)')
        return agent('cdp', **a)
    a = dict(a); a['tab'] = own_tab(sid, a.get('tab'))
    if action == 'cdp':
        m = a.get('method', '')
        if m.startswith(TAB_CDP_REFUSED): raise RouterError(403, f'{m} reaches beyond the tab: use the router')
        if m == 'Page.navigate': a['params'] = {**a.get('params', {}), 'url': account_url(sid, a.get('params', {}).get('url'))}
    if action == 'capture': a['save'] = forced_save(sid, a.get('save'))
    if action == 'paste_files':
        url = next((t['url'] for t in targets() if t['targetId'] == a['tab']), '')
        if 'gemini.google.com' in url and not a.pop('no_pace', False): pace(sid, 'image (paste on gemini)')
    r = agent(action, **a)
    event(sid, action, tab=a['tab'][:8], **({'save': a['save']} if action == 'capture' else {}),
          **({'method': a.get('method')} if action == 'cdp' else {}))
    return r


def status():
    with LOCK:
        now = time.time()
        sessions = [{'session': sid, 'name': s['name'], 'account': s.get('account'), 'email': s.get('email', ''),
                     'folder': s['folder'], 'tabs': s.get('tabs', []), 'actions': s.get('actions', 0),
                     'last': s.get('last', ''), 'last_ago_s': round(now - s.get('last_t', now)),
                     'pacing_s': s.get('pacing', 0),
                     'next_image_in_s': max(0, round(s.get('next_ok', 0) - now))} for sid, s in S['sessions'].items()]
        accounts = {a: {'last_image_ago_s': round(now - t),
                        'gap_s': float(CONF['account_gap_s'].get(a, CONF['image_gap_s']))} for a, t in S['last_image'].items()}
    return {'app': 'vm-router', 'version': VERSION, 'pid': os.getpid(), 'port': PORT, 'agent': AGENT,
            'sessions': sessions, 'accounts': accounts, 'focus_lock': FOCUS.view(), 'download_lock': DOWNLOAD.view(),
            'config': CONF, 'events': list(EVENTS)[-30:]}


def selftest():
    """CHECK in the app: a session of its own, a background tab of its own, read it, refuse a stranger, close."""
    out = []
    def step(what, fn):
        try: r = fn(); out.append({'step': what, 'ok': True, 'got': r}); return r
        except RouterError as e: out.append({'step': what, 'ok': False, 'error': str(e)}); raise
    try:
        a = step('session A', lambda: session_new({'name': 'router-check-A', 'account': 9}))['session']
        b = step('session B', lambda: session_new({'name': 'router-check-B'}))['session']
        tab = step('A opens a background tab', lambda: open_tab(a, {'url': 'data:text/html,<title>vm-router check</title>ok'}))['tab']
        step('A reads its tab', lambda: forward(a, 'eval', {'js': 'document.title'}))
        try: forward(b, 'eval', {'js': '1', 'tab': tab}); out.append({'step': 'B is refused on A\'s tab', 'ok': False})
        except RouterError as e: out.append({'step': 'B is refused on A\'s tab', 'ok': e.code == 403, 'got': str(e)})
        try: forward(b, 'eval', {'js': '1'}); out.append({'step': 'B without a tab is refused', 'ok': False})
        except RouterError as e: out.append({'step': 'B without a tab is refused', 'ok': e.code == 409, 'got': str(e)})
        step('account /u/9 is added to a gemini url', lambda: account_url(a, 'https://gemini.google.com/app'))
        step('A closes its tab', lambda: close_tab(a, {'tab': tab}))
    except RouterError: pass
    finally:
        for n in ('router-check-A', 'router-check-B'):
            sid = next((k for k, s in S['sessions'].items() if s['name'] == n), None)
            if sid:
                for t in list(S['sessions'][sid]['tabs']):
                    try: close_tab(sid, {'tab': t})
                    except RouterError: pass
                release(sid, {})
    ok = all(x['ok'] for x in out)
    event(None, 'check ' + ('passed' if ok else 'FAILED'), steps=len(out))
    return {'ok': ok, 'steps': out}


def prune():
    """Leases idle past lease_idle_h go; tabs closed on the VM drop out of their session."""
    while True:
        time.sleep(60)
        try:
            live = {t['targetId'] for t in targets()}
            with LOCK:
                now, changed = time.time(), False
                for sid, s in list(S['sessions'].items()):
                    gone = [t for t in s['tabs'] if t not in live]
                    if gone: s['tabs'] = [t for t in s['tabs'] if t in live]; changed = True
                    if now - s.get('last_t', now) > CONF['lease_idle_h'] * 3600:
                        del S['sessions'][sid]; changed = True; event(None, 'lease expired', name=s['name'])
                if changed: save()
        except Exception as e:
            print('prune:', e, flush=True)


# ---- HTTP ------------------------------------------------------------------------------------------------------------
class H(http.server.BaseHTTPRequestHandler):
    def reply(self, code, obj, raw=None, ctype='application/json'):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def body(self):
        n = int(self.headers.get('Content-Length', 0)); return self.rfile.read(n) if n else b''

    def sid(self, part):
        if part not in S['sessions']: raise RouterError(404, f'no session {part!r}: POST /session {{name}} first')
        S['sessions'][part]['last_t'] = time.time(); return part

    def handle_any(self, method):
        try:
            p = urllib.parse.urlsplit(self.path); parts = [x for x in p.path.split('/') if x]
            q = dict(urllib.parse.parse_qsl(p.query))
            if method == 'GET' and parts == ['health']:
                return self.reply(200, {'app': 'vm-router', 'version': VERSION, 'pid': os.getpid(), 'port': PORT})
            if method == 'GET' and parts == ['status']: return self.reply(200, status())
            if method == 'GET' and parts == ['events']:
                since = int(q.get('since', 0)); return self.reply(200, [e for e in EVENTS if e['n'] > since])
            if method == 'POST' and parts == ['session']:
                return self.reply(200, {'ok': True, 'result': session_new(json.loads(self.body() or b'{}'))})
            if method == 'POST' and parts == ['selftest']: return self.reply(200, {'ok': True, 'result': selftest()})
            if method == 'POST' and parts == ['stop']:
                self.reply(200, {'ok': True}); event(None, 'router stopped')
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0))).start(); return
            if len(parts) >= 3 and parts[0] == 's':
                sid = self.sid(parts[1])
                if parts[2] == 'files' and len(parts) == 4:          # PUT/GET /s/<sid>/files/<name>
                    name = os.path.basename(urllib.parse.unquote(parts[3]))
                    if method == 'PUT':
                        pre = slug(S['sessions'][sid]['name']) + '__'
                        name = name if name.startswith(pre) else pre + name
                        code, raw = agent_raw('PUT', '/files/' + urllib.parse.quote(name), self.body())
                        event(sid, 'put file', file=name); return self.reply(code, None, raw)
                    code, raw = agent_raw('GET', '/files/' + urllib.parse.quote(name))
                    return self.reply(code, None, raw, 'application/octet-stream' if code == 200 else 'application/json')
                if method != 'POST': raise RouterError(405, 'POST')
                a = json.loads(self.body() or b'{}'); op = parts[2]
                if op == 'api' and len(parts) == 4: r = forward(sid, parts[3], a)
                elif op == 'open': r = open_tab(sid, a)
                elif op == 'adopt': r = adopt(sid, a)
                elif op == 'close': r = close_tab(sid, a)
                elif op == 'release': r = release(sid, a)
                elif op == 'global': r = run_global(sid, a['steps'], a.get('label') or '+'.join(x['action'] for x in a['steps']))
                elif op == 'pace': r = pace(sid, a.get('why', 'image'))
                elif op == 'expect_download': r = expect_download(sid, a)
                elif op == 'activate': r = run_global(sid, [{'action': 'activate', **a}], 'activate')
                else: raise RouterError(404, f'no {op!r}')
                return self.reply(200, {'ok': True, 'result': r})
            raise RouterError(404, 'no such path: /health /status /events /session /s/<sid>/api/<action> …')
        except RouterError as e:
            self.reply(e.code, {'ok': False, 'error': str(e)})
        except Exception as e:
            self.reply(500, {'ok': False, 'error': f'{type(e).__name__}: {e}'})

    def do_GET(self): self.handle_any('GET')
    def do_POST(self): self.handle_any('POST')
    def do_PUT(self): self.handle_any('PUT')
    def log_message(self, *a): pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; allow_reuse_address = True


PORT = 8891
if __name__ == '__main__':
    load()
    want = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8891
    sys.path.insert(0, os.path.expanduser('~/Developer/MANTRA_PORTS'))
    try:
        import ports; PORT = ports.claim('vm-router', want)
    except Exception:
        PORT = want
    srv = Server(('127.0.0.1', PORT), H)
    open(PID_FILE, 'w').write(str(os.getpid()))
    threading.Thread(target=prune, daemon=True).start()
    event(None, 'router started', port=PORT, version=VERSION)
    print(f'vm-router v{VERSION} on http://127.0.0.1:{PORT} -> {AGENT}', flush=True)
    srv.serve_forever()
