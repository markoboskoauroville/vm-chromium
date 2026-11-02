#!/usr/bin/env python3
"""vmr: chromium-vm through vm-router, so many sessions can use the VM at once without crossing.

  vmr start | stop | status | events | check        the router itself (start: detached, if it is not running)
  vmr -s NAME [-a N] [-f FOLDER] <command> ...      as session NAME (same name = same session; or $VMR_NAME)
      session                       register (with -a: Google account /u/N, -f: folder under ~/Downloads)
      open URL | adopt TAB | close [TAB] | tabs     the session's own tabs (open is in the background)
      eval JS [TAB] | text [TAB] | capture x y w h SAVE [TAB]       on the session's tab (capture: under its folder)
      type TEXT | key KEYS | clip | clip set TEXT   one at a time, the session's tab in front (the global lock)
      paste-files VMPATH... | pace                  pace = wait for the account's image gap
      gemini [BEFORE]               results on the Gemini tab (<generated-image> only); with BEFORE wait for a new one
      expect-download [SECONDS]     the next Chrome download is this session's
      put FILE... | get NAME [DEST] | downloads     files (put names get the session's prefix)
      release [--close]             end the session (--close also closes its tabs)

In a script:   sys.path.insert(0, os.path.expanduser('~/Developer/vm-chromium/router')); import vmr
               vm = vmr.Session('life-story', account=0, folder='Gemini/life-story', tab='09C5…')
               vm.call('eval', js='document.title')      # same shape as vm-agent's /api/<action>
"""
import json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROUTER = os.path.join(HERE, 'vm-router.py')
LOG = os.path.expanduser('~/.config/vm-router/router.log')


def base():
    try:
        e = json.load(open(os.path.expanduser('~/.config/mantra-ports.json'))).get('vm-router')
        if e: return e['url']
    except Exception: pass
    return 'http://127.0.0.1:8891'


def alive():
    try:
        with urllib.request.urlopen(base() + '/health', timeout=2) as f: return json.load(f)
    except Exception: return None


def start():
    if alive(): return alive()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    subprocess.Popen([sys.executable, ROUTER], stdout=open(LOG, 'a'), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        time.sleep(0.25)
        h = alive()
        if h: return h
    raise SystemExit('vmr: the router did not start; see ' + LOG)


def http(method, path, body=None, raw=None, timeout=600):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(base() + path, data=data, method=method, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f: return f.read()
    except urllib.error.HTTPError as e: return e.read()


class Error(RuntimeError): pass


class Session:
    """One lease on chromium-vm. call() has vm-agent's shape; a tab is optional (the session's own first tab)."""
    def __init__(self, name, account=None, folder=None, tab=None, email=None, autostart=True):
        if autostart: start()
        a = {'name': name}
        for k, v in (('account', account), ('folder', folder), ('tab', tab), ('email', email)):
            if v is not None: a[k] = v
        r = self._j(http('POST', '/session', a))
        self.id, self.info = r['session'], r

    @staticmethod
    def _j(raw):
        j = json.loads(raw)
        if not j.get('ok'): raise Error(j.get('error'))
        return j['result']

    def post(self, op, **a): return self._j(http('POST', f'/s/{self.id}/{op}', a))
    def call(self, action, **a): return self.post('api/' + action, **a)
    def open(self, url, front=False): return self.post('open', url=url, front=front)['tab']
    def adopt(self, tab): return self.post('adopt', tab=tab)
    def close(self, tab=None): return self.post('close', **({'tab': tab} if tab else {}))
    def steps(self, *steps, label=None): return self.post('global', steps=list(steps), **({'label': label} if label else {}))
    def pace(self, why='image'): return self.post('pace', why=why)
    def expect_download(self, seconds=120): return self.post('expect_download', seconds=seconds)
    def release(self, close_tabs=False): return self.post('release', close_tabs=close_tabs)

    def put(self, path):
        return json.loads(http('PUT', f'/s/{self.id}/files/' + urllib.parse.quote(os.path.basename(path)),
                               raw=open(path, 'rb').read(), timeout=3600))

    def get(self, name, dest=None):
        d = http('GET', f'/s/{self.id}/files/' + urllib.parse.quote(name)); dest = dest or name
        open(dest, 'wb').write(d); return dest


def out(x): print(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1))


def main(argv):
    name, account, folder = os.environ.get('VMR_NAME'), None, None
    while argv and argv[0] in ('-s', '-a', '-f'):
        flag, val, argv = argv[0], argv[1], argv[2:]
        if flag == '-s': name = val
        elif flag == '-a': account = int(val)
        else: folder = val
    c, args = (argv[0] if argv else 'help'), argv[1:]
    if c == 'start': out(start()); return
    if c == 'stop':
        if alive(): http('POST', '/stop', {})
        print('vm-router stopped'); return
    if c == 'status':
        h = alive()
        if not h: print('vm-router is not running (vmr start)'); return
        out(json.loads(http('GET', '/status'))); return
    if c == 'events': out(json.loads(http('GET', '/events?since=' + (args[0] if args else '0')))); return
    if c == 'check': start(); out(json.loads(http('POST', '/selftest', {}))['result']); return
    if c in ('help', '-h', '--help') or not name:
        print(__doc__ if c in ('help', '-h', '--help') else 'vmr: give a session name: vmr -s NAME … (or VMR_NAME)'); return
    s = Session(name, account, folder)
    try:
        if c == 'session': out(s.info)
        elif c == 'open': out(s.open(args[0]))
        elif c == 'adopt': out(s.adopt(args[0]))
        elif c == 'close': out(s.close(args[0] if args else None))
        elif c == 'tabs': out(s.call('tabs'))
        elif c == 'eval': out(s.call('eval', js=args[0], **({'tab': args[1]} if len(args) > 1 else {})))
        elif c == 'text': out(s.call('page_text', **({'tab': args[0]} if args else {})))
        elif c == 'capture':
            x, y, w, h, save = args[:5]
            out(s.call('capture', x=x, y=y, w=w, h=h, save=save, **({'tab': args[5]} if len(args) > 5 else {})))
        elif c == 'type': out(s.call('type', text=' '.join(args)))
        elif c == 'key': out(s.call('key', keys=' '.join(args)))
        elif c == 'clip':
            if args[:1] == ['set']: out(s.call('clip_set', text=' '.join(args[1:])))
            else: out(s.call('clip_get'))
        elif c == 'paste-files': out(s.call('paste_files', files=args))
        elif c == 'pace': out(s.pace())
        elif c == 'gemini': out(s.call('gemini_wait', before=int(args[0])) if args else s.call('gemini_state'))
        elif c == 'expect-download': out(s.expect_download(int(args[0]) if args else 120))
        elif c == 'put':
            for p in args: out(s.put(p))
        elif c == 'get': out(s.get(args[0], args[1] if len(args) > 1 else None))
        elif c == 'downloads': out(s.call('downloads', since=0))
        elif c == 'release': out(s.release('--close' in args))
        else: print(__doc__)
    except Error as e:
        sys.exit('vmr: ' + str(e))


if __name__ == '__main__':
    main(sys.argv[1:])
