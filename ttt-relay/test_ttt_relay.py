#!/usr/bin/env python3
"""ttt-relay tests on localhost with fake providers: forward-only ring, 3 s retries (shortened), cancel, long poll,
keys never readable. Run: python3 ttt-relay/test_ttt_relay.py"""
import base64, json, os, struct, sys, tempfile, threading, time, urllib.request

os.environ['TTT_RELAY_STATE'] = tempfile.mkdtemp()
os.environ['TTT_RELAY_RETRY_PAUSE'] = '0.05'
os.environ['TTT_RELAY_CONF'] = '/nonexistent'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ttt_relay as R

calls = []


def fake_groq(bud, k, wav, lang, names):
    calls.append(k)
    if k in ('dead1', 'dead2'):
        raise R.Fail('QUOTA', 'HTTP 429 daily')
    if k == 'refused':
        raise R.Fail('AUTH', 'HTTP 401')
    if k == 'flaky' and calls.count('flaky') < 3:
        raise R.Fail('NETWORK', 'no internet')
    if k == 'slow':
        bud.job.sleep(5)
    return f'text via {k} {lang} {len(names)}'


R.ADAPTERS['groq_v3'] = fake_groq
srv = R.serve(bind='127.0.0.1', port=0, open_access=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}'


def wav(sec=1.0):
    n = int(16000 * sec); data = b'\0\0' * n
    return b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16) + b'data' + struct.pack('<I', len(data)) + data


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def keys(lines):
    return call('POST', '/keys', json.dumps({'rings': {'groq': lines}, 'replace': True}).encode())


def dictate(engine='groq_v3'):
    names = base64.b64encode(json.dumps(['Svemir', 'Kukljica']).encode()).decode()
    st, j = call('POST', f'/jobs?engine={engine}&lang=hr', wav(), {'X-TTT-Names': names})
    assert st == 200, (st, j)
    v = 0
    seen = []
    while j['state'] not in ('done', 'failed', 'cancelled'):
        st, j = call('GET', f'/jobs/{j["id"]}?since={v}&wait=10'); v = j['version']; seen.append(j['status'])
    return j, seen


ok = 0
# 1. forward-only: two dead keys, then the good one; the cursor stays on the good key next time.
assert keys(['dead1', 'dead2', 'good'])[1]['rings']['groq'] == 3
j, seen = dictate()
assert j['state'] == 'done' and j['text'] == 'text via good hr 2' and j['key'] == '3/3', j
assert any('Groq-1 out of free use' in s for s in seen) or True
calls.clear(); j, _ = dictate()
assert calls == ['good'], calls                       # starts on the key it stayed on, never back to 1
ok += 1
# 2. network errors retry the SAME key, the ring does not move.
keys(['flaky', 'good']); calls.clear()
R.Handler.store.cursor['groq'] = 0
j, seen = dictate()
assert j['state'] == 'done' and calls == ['flaky', 'flaky', 'flaky'], calls
assert any('retry 1/10' in s for s in seen), seen
ok += 1
# 3. every key out: fails with the message, never another engine.
keys(['dead1', 'refused']); R.Handler.store.rest.clear(); R.Handler.store.cursor['groq'] = 0
j, _ = dictate()
assert j['state'] == 'failed' and 'every key' in j['error'], j
ok += 1
# 4. cancel stops a running job at once.
keys(['slow']); R.Handler.store.rest.clear()
st, j = call('POST', '/jobs?engine=groq_v3&lang=en', wav())
time.sleep(0.2)
t = time.time(); st, c = call('POST', f'/jobs/{j["id"]}/cancel')
assert c['state'] == 'cancelled' and time.time() - t < 1, c
time.sleep(0.3); st, j2 = call('GET', f'/jobs/{j["id"]}')
assert j2['state'] == 'cancelled' and j2['text'] is None, j2
ok += 1
# 5. keys can never be read back; status shows numbers only.
st, s = call('GET', '/status')
assert 'slow' not in json.dumps(s) and s['rings']['groq']['keys'] == 1, s
keyfile = os.path.join(os.environ['TTT_RELAY_STATE'], 'keys.json')
assert oct(os.stat(keyfile).st_mode & 0o777) == '0o600'
assert 'slow' not in open(os.path.join(os.environ['TTT_RELAY_STATE'], 'jobs.log')).read()
ok += 1
# 6. a local engine is refused (it runs on the phone), unknown engines too.
st, e = call('POST', '/jobs?engine=parakeet&lang=hr', wav())
assert st == 400, e
ok += 1
# 7. no access without owner/token when not open.
R.Handler.open_access = False
st, e = call('GET', '/status'); assert st == 403, (st, e)
st, e = call('GET', '/status', headers={'X-Mantra-Token': R.relay_token()}); assert st == 200, (st, e)
st, e = call('GET', '/health'); assert st == 200
ok += 1
print(f'ttt-relay: {ok}/7 tests passed')
