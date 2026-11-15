#!/usr/bin/env python3
"""ttt-relay: TTT's transcription runs in Frankfurt (chromium-vm), the phone only sends the audio (Marko, 14.11.2026).

"Same as my TTT right now. We are offloading this part to Frankfurt so you just receive the call and do key rotations
and bring back the transcription plus report if something went wrong and it can also retry multiple times and I need
to see my TTT status what is going on with Frankfurt and I can then cancel the transcription and try different engine."

The rules are TTT's own (TTT skill rules 10 and 11), copied here and never loosened:
  * only the engine the phone asked for; NEVER another engine or provider by itself;
  * forward-only key ring per provider: a key out of free use (429/402/quota) or refused (401/403) moves the cursor to
    the next key and it stays there; it wraps to key 1 only after the last; a daily quota rests a key until 00:00 UTC,
    a rate limit a minute, a refused key an hour; every key out = the job fails and says so;
  * no answer / timeout / network error: wait 3 s and try the SAME engine and key again, up to 10 retries;
    a network error never moves the ring;
  * keys are never printed, logged or returned; only their number ("Groq 2/8").

HTTP on the Tailscale address, port 8897 (`TTT_RELAY_PORT`). Who may call: a Tailscale peer whose `tailscale whois`
user is the owner (`/etc/ttt-relay.conf` OWNER=...), or a caller with the token (`X-Mantra-Token`, file
/var/lib/ttt-relay/token). `GET /health` needs neither.

    GET  /health                       {"ok": true, "version": N}
    GET  /status                       rings {ring: {keys, cursor, resting}}, jobs running, version
    POST /keys                         {"rings": {"groq": ["k1", "k2"], ...}, "replace": true} -> {"rings": {ring: count}}
                                       write only: keys can never be read back
    POST /jobs?engine=groq_v3&lang=hr  (lang hr | en | auto; auto since version 2) body = the 16 kHz mono WAV; header X-TTT-Names = base64(JSON list of names)
                                       -> {"id": "...", "state": "queued", ...}
    GET  /jobs/ID?since=V&wait=20      long poll: answers as soon as the job's version is above V (or after wait s)
                                       {"id", "state": queued|sending|retry|done|failed|cancelled, "status", "text",
                                        "engine", "key", "attempt", "error", "version", "ms"}
    POST /jobs/ID/cancel               the job stops at once; a late upstream answer is thrown away
    POST /bench/clip?id=&lang=&kind=wav|aac   one clip of the AAC-against-WAV test (header X-TTT-Ref = base64 text)
    POST /bench/run?engines=a,b        starts the test (aac_bench.py) in the background;  GET /bench  progress + report
    POST /bench/clear                  deletes the test clips

Every finished job is one line in /var/lib/ttt-relay/jobs.log (time, engine, lang, seconds of audio, key number,
attempts, result, ms): never the text, never a key.
"""
import base64, hashlib, io, json, os, secrets, socket, subprocess, sys, tempfile, threading, time, urllib.error
import urllib.parse, urllib.request, uuid, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = 2          # 2 (15.11.2026): lang=auto for the Mac app Voice to Text (Mantra); additive, lang en/hr unchanged
STATE_DIR = os.environ.get('TTT_RELAY_STATE', '/var/lib/ttt-relay')
PORT = int(os.environ.get('TTT_RELAY_PORT', '8897'))
MAX_RETRIES = 10
RETRY_PAUSE = float(os.environ.get('TTT_RELAY_RETRY_PAUSE', '3'))
MAX_AUDIO = 40 * 1024 * 1024
UA = 'curl/8'

# The engine ids are TTT's (EngineAdapters.run); the ring id is the key ring the engine draws from, the label the name
# shown with the key number. Local engines (parakeet, android) never come here: they run on the phone.
ENGINES = {
    'groq_turbo': ('groq', 'Groq'), 'groq_v3': ('groq', 'Groq'), 'gemini': ('gemini', 'Gemini'),
    'deepgram': ('deepgram', 'Deepgram'), 'assemblyai': ('assemblyai', 'AssemblyAI'),
    'speechmatics': ('speechmatics', 'Speechmatics'), 'soniox': ('soniox', 'Soniox'), 'google_v1': ('google_v1', 'Google'),
    'elevenlabs': ('elevenlabs', 'ElevenLabs'), 'cloudflare': ('cloudflare', 'Cloudflare'),
    'google_chirp': ('google_chirp', 'Chirp'),
}
# Rings whose lines are ONE credential together (Cloudflare: account id + token; Chirp: the service account JSON).
WHOLE_RINGS = {'cloudflare', 'google_chirp'}


def conf():
    c = {}
    try:
        for line in open(os.environ.get('TTT_RELAY_CONF', '/etc/ttt-relay.conf')):
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.strip().split('=', 1); c[k.strip()] = v.strip()
    except OSError:
        pass
    return c


def log_line(msg):
    try:
        with open(os.path.join(STATE_DIR, 'jobs.log'), 'a') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except OSError:
        pass


# ---------------------------------------------------------------- failures (TTT FailKind)

class Fail(Exception):
    """kind: QUOTA | AUTH | NETWORK | TIMEOUT | ERROR | NOT_CONFIGURED. The message never holds a key or a body."""
    def __init__(self, kind, msg=''):
        super().__init__(msg); self.kind = kind; self.msg = msg


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- the stored keys and the forward-only ring

class Store:
    def __init__(self, d):
        self.d = d; os.makedirs(d, mode=0o700, exist_ok=True)
        self.lock = threading.RLock()
        self.keys = self._load('keys.json', {})
        st = self._load('state.json', {})
        self.cursor = st.get('cursor', {}); self.rest = st.get('rest', {})

    def _load(self, name, default):
        try:
            with open(os.path.join(self.d, name)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self, name, obj):
        p = os.path.join(self.d, name); tmp = p + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f)
        os.replace(tmp, p)

    def save_state(self):
        with self.lock:
            self._save('state.json', {'cursor': self.cursor, 'rest': self.rest})

    def set_keys(self, rings, replace):
        with self.lock:
            for ring, lines in rings.items():
                if ring not in {r for r, _ in ENGINES.values()}:
                    continue
                lines = [l.strip() for l in lines if isinstance(l, str) and l.strip()]
                old = self.keys.get(ring, [])
                if replace:
                    # The phone's file order is the numbering (Groq-1, Groq-2 ...); the cursor stays where it was if it still fits.
                    self.keys[ring] = lines
                else:
                    self.keys[ring] = old + [l for l in lines if l not in old]
                if self.cursor.get(ring, 0) >= max(1, self.n(ring)):
                    self.cursor[ring] = 0
            self._save('keys.json', self.keys)
            self.save_state()
            return {r: self.n(r) for r in self.keys}

    def n(self, ring):
        k = self.keys.get(ring, [])
        return 1 if (ring in WHOLE_RINGS and k) else len(k)

    def key(self, ring, idx):
        k = self.keys.get(ring, [])
        return k if ring in WHOLE_RINGS else k[idx]

    @staticmethod
    def tag(ring, value):
        v = '\n'.join(value) if isinstance(value, list) else value
        return ring + ':' + hashlib.sha256(v.encode()).hexdigest()[:12]

    def status(self):
        now = time.time()
        with self.lock:
            out = {}
            for ring in sorted(self.keys):
                n = self.n(ring)
                resting = sum(1 for i in range(n) if self.rest.get(self.tag(ring, self.key(ring, i)), 0) > now)
                out[ring] = {'keys': n, 'cursor': (self.cursor.get(ring, 0) % n) + 1 if n else 0, 'resting': resting}
            return out


def next_utc_midnight(now):
    return (int(now) // 86400 + 1) * 86400


def ring_run(store, ring, label, job, block):
    """TTT's KeyRing.run, forward only. block(key) returns the text or raises Fail."""
    with store.lock:
        n = store.n(ring)
        if n == 0:
            raise Fail('NOT_CONFIGURED', f'{label}: no key in Frankfurt')
        now = time.time()
        start = store.cursor.get(ring, 0)
        start = start if 0 <= start < n else 0
        order = [(start + i) % n for i in range(n)]
        ready = [i for i in order if store.rest.get(store.tag(ring, store.key(ring, i)), 0) <= now] or order
    last = Fail('NOT_CONFIGURED', 'no key')
    for pos, idx in enumerate(ready):
        job.check()
        k = store.key(ring, idx)
        number = idx + 1
        job.update(key=f'{number}/{n}', key_label=f'{label} {number}/{n}')
        try:
            r = block(k)
            with store.lock:
                store.cursor[ring] = idx; store.save_state()
            return r
        except Fail as f:
            if f.kind not in ('QUOTA', 'AUTH'):
                raise                                         # network / timeout / error: the ring does not move
            m = f.msg.lower(); now = time.time()
            daily = f.kind == 'QUOTA' and any(w in m for w in ('day', 'daily', 'quota', 'credit'))
            until = now + 3600 if f.kind == 'AUTH' else next_utc_midnight(now) if daily else now + 60
            what = 'out of free use' if f.kind == 'QUOTA' else 'refused'
            nxt = ready[pos + 1] if pos + 1 < len(ready) else (idx + 1) % n
            with store.lock:
                store.rest[store.tag(ring, k)] = until
                store.cursor[ring] = nxt; store.save_state()
            if pos < len(ready) - 1:
                job.note(f'{label}-{number} {what} → {label}-{nxt + 1}')
            last = f
    raise last


# ---------------------------------------------------------------- HTTP to the providers

class Budget:
    """The attempt's deadline (TTT: 8 s + half the clip length); every request gets what is left."""
    def __init__(self, seconds, job):
        self.until = time.time() + seconds; self.job = job

    def left(self):
        self.job.check()
        t = self.until - time.time()
        if t <= 0:
            raise Fail('TIMEOUT', 'no answer')
        return max(1.0, t)


def send(budget, url, data=None, headers=None, method=None):
    """The body of a 2xx answer; any other status becomes a typed failure (TTT EngineAdapters.send)."""
    h = {'User-Agent': UA}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(req, timeout=budget.left()) as r:
            return r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            pass
        low = body.lower()
        if e.code == 404 and any(w in low for w in ('model_not_found', 'decommission', 'does not exist')):
            raise Fail('NOT_CONFIGURED', 'model retired')
        if e.code in (429, 402):
            kind = 'QUOTA'
        elif e.code == 401 or (e.code == 400 and ('api key not valid' in low or 'api_key_invalid' in low)):
            kind = 'AUTH'                                     # Gemini says a bad key with a 400
        elif e.code == 403:
            kind = 'QUOTA' if any(w in low for w in ('quota', 'credit', 'limit')) else 'AUTH'
        else:
            kind = 'ERROR'
        msg = f'HTTP {e.code}'
        if e.code == 400:
            msg += ': ' + ' '.join(body[:140].split())
        if kind == 'QUOTA' and any(w in low for w in ('day', 'daily')):
            msg += ' daily'
        raise Fail(kind, msg)
    except (socket.timeout, TimeoutError):
        raise Fail('TIMEOUT', 'no answer')
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        raise Fail('NETWORK', 'no internet')


def multipart(fields, file_field, wav, filename='clip.wav', ctype='audio/wav'):
    b = '----ttt' + secrets.token_hex(12)
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode()); out.write(str(v).encode()); out.write(b'\r\n')
    if file_field:
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                  f'Content-Type: {ctype}\r\n\r\n'.encode())
        out.write(wav); out.write(b'\r\n')
    out.write(f'--{b}--\r\n'.encode())
    return out.getvalue(), f'multipart/form-data; boundary={b}'


def lang2(lang):
    return 'en' if lang == 'en' else 'auto' if lang == 'auto' else 'hr'


def glang(lang):
    return 'en-US' if lang2(lang) == 'en' else 'hr-HR'


def js(text):
    try:
        return json.loads(text)
    except ValueError:
        raise Fail('ERROR', 'bad answer')


def groq(model):
    def run(bud, k, wav, lang, names):
        f = {'model': model, 'response_format': 'json', 'temperature': '0'}
        if lang2(lang) != 'auto':
            f['language'] = lang2(lang)
        if names:
            f['prompt'] = ', '.join(names)[:600]
        body, ct = multipart(f, 'file', wav)
        return js(send(bud, 'https://api.groq.com/openai/v1/audio/transcriptions', body,
                       {'Authorization': f'Bearer {k}', 'Content-Type': ct}))['text']
    return run


def cloudflare(bud, k, wav, lang, names):
    if len(k) < 2:
        raise Fail('NOT_CONFIGURED', 'needs account id and token')
    b = {'audio': base64.b64encode(wav).decode()}
    if lang2(lang) != 'auto':
        b['language'] = lang2(lang)
    body = json.dumps(b).encode()
    return js(send(bud, f'https://api.cloudflare.com/client/v4/accounts/{k[0]}/ai/run/@cf/openai/whisper-large-v3-turbo', body,
                   {'Authorization': f'Bearer {k[1]}', 'Content-Type': 'application/json'}))['result']['text']


def gemini(bud, k, wav, lang, names):
    l = {'en': 'English', 'auto': 'Croatian or English, whichever is spoken (write each part in the language it is in)'}.get(lang2(lang), 'Croatian')
    p = f'Transcribe this speech exactly and verbatim in {l}, with punctuation, no commentary.'
    if names:
        p += ' Names that may occur: ' + ', '.join(names)[:600] + '.'
    b = {'contents': [{'parts': [{'text': p}, {'inline_data': {'mime_type': 'audio/wav', 'data': base64.b64encode(wav).decode()}}]}]}
    r = js(send(bud, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent',
                json.dumps(b).encode(), {'x-goog-api-key': k, 'Content-Type': 'application/json'}))
    return r['candidates'][0]['content']['parts'][0]['text'].strip()


def deepgram(bud, k, wav, lang, names):
    q = [('model', 'nova-3'), ('language', 'multi' if lang2(lang) == 'auto' else lang2(lang)), ('smart_format', 'true')] + [('keyterm', n) for n in names[:50]]
    r = js(send(bud, 'https://api.deepgram.com/v1/listen?' + urllib.parse.urlencode(q), wav,
                {'Authorization': f'Token {k}', 'Content-Type': 'audio/wav'}))
    return r['results']['channels'][0]['alternatives'][0]['transcript']


def elevenlabs(bud, k, wav, lang, names):
    body, ct = multipart(dict({'model_id': 'scribe_v1'}, **({} if lang2(lang) == 'auto' else {'language_code': lang2(lang)})), 'file', wav)
    return js(send(bud, 'https://api.elevenlabs.io/v1/speech-to-text', body, {'xi-api-key': k, 'Content-Type': ct}))['text']


def _results(r):
    return ' '.join(x['alternatives'][0].get('transcript', '') for x in (r.get('results') or [])).strip()


def google_v1(bud, k, wav, lang, names):
    cfg = {'encoding': 'LINEAR16', 'sampleRateHertz': 16000, 'languageCode': glang(lang), 'enableAutomaticPunctuation': True}
    if lang2(lang) == 'auto':
        cfg['alternativeLanguageCodes'] = ['en-US']
    if names:
        cfg['speechContexts'] = [{'phrases': names[:100]}]
    body = json.dumps({'config': cfg, 'audio': {'content': base64.b64encode(wav).decode()}}).encode()
    return _results(js(send(bud, 'https://speech.googleapis.com/v1/speech:recognize', body,
                            {'x-goog-api-key': k, 'Content-Type': 'application/json'})))


_gtoken = {}


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def google_token(bud, sa):
    cached = _gtoken.get(sa['client_email'])
    if cached and cached[1] > time.time():
        return cached[0]
    now = int(time.time()); uri = sa.get('token_uri', 'https://oauth2.googleapis.com/token')
    head = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    claims = _b64url(json.dumps({'iss': sa['client_email'], 'scope': 'https://www.googleapis.com/auth/cloud-platform',
                                 'aud': uri, 'iat': now, 'exp': now + 3000}).encode())
    # RS256 with the openssl command (no third-party Python package needed); the key lives only in a 0600 temp file.
    fd, path = tempfile.mkstemp(dir=STATE_DIR, prefix='.sa-'); os.close(fd)
    try:
        with open(path, 'w') as f:
            f.write(sa['private_key'])
        sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', path], input=f'{head}.{claims}'.encode(),
                             capture_output=True, timeout=10).stdout
    finally:
        os.unlink(path)
    if not sig:
        raise Fail('NOT_CONFIGURED', 'service account key unreadable')
    form = urllib.parse.urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                   'assertion': f'{head}.{claims}.{_b64url(sig)}'}).encode()
    tok = js(send(bud, uri, form, {'Content-Type': 'application/x-www-form-urlencoded'}))['access_token']
    _gtoken[sa['client_email']] = (tok, time.time() + 50 * 60)
    return tok


def google_chirp(bud, k, wav, lang, names):
    try:
        sa = json.loads('\n'.join(k))
    except ValueError:
        raise Fail('NOT_CONFIGURED', 'service account unreadable')
    project = sa.get('project_id') or ''
    if not project:
        raise Fail('NOT_CONFIGURED', 'no project id')
    tok = google_token(bud, sa)
    body = json.dumps({'config': {'autoDecodingConfig': {}, 'languageCodes': ['auto'] if lang2(lang) == 'auto' else [glang(lang)], 'model': 'chirp_3'},
                       'content': base64.b64encode(wav).decode()}).encode()
    return _results(js(send(bud, f'https://us-speech.googleapis.com/v2/projects/{project}/locations/us/recognizers/_:recognize',
                            body, {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'})))


def assemblyai(bud, k, wav, lang, names):
    up = js(send(bud, 'https://api.assemblyai.com/v2/upload', wav, {'authorization': k, 'Content-Type': 'application/octet-stream'}))['upload_url']
    b = {'audio_url': up, 'speech_models': ['universal-3-5-pro', 'universal-2']}
    if lang2(lang) == 'auto':
        b.update({'language_detection': True, 'language_detection_options': {'expected_languages': ['en', 'hr']}})
    else:
        b['language_code'] = lang2(lang)
    if names:
        b['word_boost'] = names[:100]
    tid = js(send(bud, 'https://api.assemblyai.com/v2/transcript', json.dumps(b).encode(),
                  {'authorization': k, 'Content-Type': 'application/json'}))['id']
    while True:
        r = js(send(bud, f'https://api.assemblyai.com/v2/transcript/{tid}', headers={'authorization': k}))
        if r.get('status') == 'completed':
            return r.get('text') or ''
        if r.get('status') == 'error':
            raise Fail('ERROR', 'engine error')
        bud.job.sleep(0.7)


def speechmatics(bud, k, wav, lang, names):
    cfg = json.dumps({'type': 'transcription', 'transcription_config': {'language': lang2(lang)}})
    body, ct = multipart({'config': cfg}, 'data_file', wav)
    auth = {'Authorization': f'Bearer {k}'}
    jid = js(send(bud, 'https://asr.api.speechmatics.com/v2/jobs', body, dict(auth, **{'Content-Type': ct})))['id']
    while True:
        st = js(send(bud, f'https://asr.api.speechmatics.com/v2/jobs/{jid}', headers=auth))['job']['status']
        if st == 'done':
            break
        if st in ('rejected', 'deleted'):
            raise Fail('ERROR', f'job {st}')
        bud.job.sleep(0.8)
    return send(bud, f'https://asr.api.speechmatics.com/v2/jobs/{jid}/transcript?format=txt', headers=auth).strip()


def soniox(bud, k, wav, lang, names):
    auth = {'Authorization': f'Bearer {k}'}
    body, ct = multipart({}, 'file', wav)
    fid = js(send(bud, 'https://api.soniox.com/v1/files', body, dict(auth, **{'Content-Type': ct})))['id']
    try:
        b = json.dumps({'model': 'stt-async-v6', 'file_id': fid, 'language_hints': ['en', 'hr'] if lang2(lang) == 'auto' else [lang2(lang)]}).encode()
        tid = js(send(bud, 'https://api.soniox.com/v1/transcriptions', b, dict(auth, **{'Content-Type': 'application/json'})))['id']
        while True:
            st = js(send(bud, f'https://api.soniox.com/v1/transcriptions/{tid}', headers=auth))['status']
            if st == 'completed':
                break
            if st == 'error':
                raise Fail('ERROR', 'engine error')
            bud.job.sleep(0.6)
        return js(send(bud, f'https://api.soniox.com/v1/transcriptions/{tid}/transcript', headers=auth))['text']
    finally:
        try:
            send(Budget(5, Job.dummy()), f'https://api.soniox.com/v1/files/{fid}', headers=auth, method='DELETE')
        except Exception:
            pass


ADAPTERS = {
    'groq_turbo': groq('whisper-large-v3-turbo'), 'groq_v3': groq('whisper-large-v3'), 'gemini': gemini,
    'deepgram': deepgram, 'assemblyai': assemblyai, 'speechmatics': speechmatics, 'soniox': soniox,
    'google_v1': google_v1, 'elevenlabs': elevenlabs, 'cloudflare': cloudflare, 'google_chirp': google_chirp,
}


# ---------------------------------------------------------------- jobs

def wav_seconds(wav):
    try:
        with wave.open(io.BytesIO(wav)) as w:
            return w.getnframes() / float(w.getframerate() or 16000)
    except Exception:
        return max(0.0, (len(wav) - 44) / 32000.0)


class Job:
    jobs = {}
    lock = threading.Lock()

    def __init__(self, engine, lang, names, wav):
        self.id = uuid.uuid4().hex[:12]; self.engine = engine; self.lang = lang; self.names = names; self.wav = wav
        self.created = time.time(); self.state = 'queued'; self.status = 'Frankfurt: queued'; self.text = None
        self.error = None; self.key = None; self.key_label = None; self.attempt = 0; self.version = 1; self.ms = None
        self.cancelled = False; self.cv = threading.Condition()

    @classmethod
    def dummy(cls):
        return cls('none', 'en', [], b'')

    def check(self):
        if self.cancelled:
            raise Cancelled()

    def sleep(self, s):
        with self.cv:
            self.cv.wait_for(lambda: self.cancelled, timeout=s)
        self.check()

    def update(self, **kw):
        with self.cv:
            for k, v in kw.items():
                setattr(self, k, v)
            self.version += 1; self.cv.notify_all()

    def note(self, status):
        self.update(status=status)

    def view(self):
        return {'id': self.id, 'state': self.state, 'status': self.status, 'text': self.text, 'engine': self.engine,
                'key': self.key, 'attempt': self.attempt, 'error': self.error, 'version': self.version, 'ms': self.ms}

    def wait(self, since, seconds):
        with self.cv:
            self.cv.wait_for(lambda: self.version > since, timeout=seconds)
        return self.view()

    def cancel(self):
        with self.cv:
            if self.state in ('done', 'failed', 'cancelled'):
                return
            self.cancelled = True; self.state = 'cancelled'; self.status = 'Frankfurt: cancelled'
            self.version += 1; self.cv.notify_all()


SLOTS = threading.BoundedSemaphore(int(os.environ.get('TTT_RELAY_PARALLEL', '4')))


def run_job(store, job):
    ring, label = ENGINES[job.engine]
    sec = wav_seconds(job.wav)
    t0 = time.time()
    result = 'failed'
    try:
        with SLOTS:
            job.check()
            while True:
                job.update(state='sending' if job.attempt == 0 else 'retry',
                           status=f'Frankfurt · {label}' + ('' if job.attempt == 0 else f' · retry {job.attempt}/{MAX_RETRIES}'))
                try:
                    bud = Budget(8 + sec * 0.5, job)
                    text = ring_run(store, ring, label, job, lambda k: ADAPTERS[job.engine](bud, k, job.wav, job.lang, job.names))
                    job.check()
                    job.update(state='done', text=text, ms=int((time.time() - t0) * 1000),
                               status=f'Frankfurt · {job.key_label or label} · done')
                    result = 'ok'
                    return
                except Fail as f:
                    if f.kind in ('QUOTA', 'AUTH'):
                        job.update(state='failed', error=f'{label}: every key is out of free use or refused',
                                   status=f'Frankfurt · {label}: every key is out')
                        return
                    if f.kind == 'NOT_CONFIGURED':
                        job.update(state='failed', error=f.msg or f'{label} is not set up in Frankfurt',
                                   status=f'Frankfurt · {f.msg or label + " not set up"}')
                        return
                    job.attempt += 1
                    if job.attempt > MAX_RETRIES:
                        job.update(state='failed', error=f'{label} did not answer after {MAX_RETRIES} tries',
                                   status=f'Frankfurt · {label} · gave up after {MAX_RETRIES} tries')
                        return
                    why = {'NETWORK': 'no internet', 'TIMEOUT': 'no answer'}.get(f.kind, f.msg or 'failed')
                    job.update(state='retry', status=f'Frankfurt · {job.key_label or label} · retry {job.attempt}/{MAX_RETRIES} · {why}')
                    job.sleep(RETRY_PAUSE)
    except Cancelled:
        result = 'cancelled'
    except Exception as e:                                    # a bug here must still end the job, never hang the phone
        job.update(state='failed', error=f'relay error {type(e).__name__}', status='Frankfurt · relay error')
    finally:
        job.wav = b''
        log_line(f'{job.engine} {job.lang} {sec:.1f}s key {job.key or "-"} attempts {job.attempt + 1} {result} '
                 f'{int((time.time() - t0) * 1000)}ms')


def gc_jobs():
    while True:
        time.sleep(60)
        now = time.time()
        with Job.lock:
            for jid in [j for j, job in Job.jobs.items() if now - job.created > 1800]:
                Job.jobs.pop(jid, None)


# ---------------------------------------------------------------- access

_whois = {}


def tailscale_user(ip):
    hit = _whois.get(ip)
    if hit and hit[1] > time.time():
        return hit[0]
    user = None
    try:
        out = subprocess.run(['tailscale', 'whois', '--json', ip], capture_output=True, timeout=5, text=True).stdout
        user = (json.loads(out).get('UserProfile') or {}).get('LoginName')
    except Exception:
        pass
    _whois[ip] = (user, time.time() + 600)
    return user


def relay_token():
    p = os.path.join(STATE_DIR, 'token')
    try:
        return open(p).read().strip()
    except OSError:
        t = secrets.token_urlsafe(32)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(t + '\n')
        return t


class Handler(BaseHTTPRequestHandler):
    server_version = 'ttt-relay'
    store = None
    owner = None
    open_access = False

    def log_message(self, fmt, *args):
        pass                                                  # nothing per request: no paths with ids, no headers

    def answer(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def allowed(self):
        if self.open_access:
            return True
        t = self.headers.get('X-Mantra-Token') or (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
        if t and secrets.compare_digest(t, relay_token()):
            return True
        ip = self.client_address[0]
        return bool(self.owner) and ip.startswith('100.') and tailscale_user(ip) == self.owner

    def body(self, limit=MAX_AUDIO):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('too big')
        return self.rfile.read(n) if n else b''

    def route(self):
        u = urllib.parse.urlparse(self.path); parts = [p for p in u.path.split('/') if p]; q = urllib.parse.parse_qs(u.query)
        return parts, {k: v[0] for k, v in q.items()}

    def do_GET(self):
        parts, q = self.route()
        if parts == ['health']:
            return self.answer(200, {'ok': True, 'version': VERSION})
        if not self.allowed():
            return self.answer(403, {'error': 'not allowed'})
        if parts == ['status']:
            with Job.lock:
                running = sum(1 for j in Job.jobs.values() if j.state in ('queued', 'sending', 'retry'))
            return self.answer(200, {'version': VERSION, 'rings': self.store.status(), 'running': running})
        if parts == ['bench']:
            import aac_bench
            return self.answer(200, aac_bench.status())
        if len(parts) == 2 and parts[0] == 'jobs':
            job = Job.jobs.get(parts[1])
            if not job:
                return self.answer(404, {'error': 'no such job'})
            since = int(q.get('since', '0') or 0); wait = min(25.0, float(q.get('wait', '0') or 0))
            return self.answer(200, job.wait(since, wait) if wait > 0 else job.view())
        self.answer(404, {'error': 'unknown'})

    def do_POST(self):
        parts, q = self.route()
        if not self.allowed():
            return self.answer(403, {'error': 'not allowed'})
        try:
            if parts == ['keys']:
                d = json.loads(self.body(1024 * 1024) or b'{}')
                rings = d.get('rings') or {}
                return self.answer(200, {'rings': self.store.set_keys(rings, bool(d.get('replace', True)))})
            if parts and parts[0] == 'bench':
                # AAC against WAV (Marko, 15.11.2026): the phone sends clips, Frankfurt compares (aac_bench.py).
                import aac_bench
                if parts == ['bench', 'clip']:
                    ref = ''
                    if self.headers.get('X-TTT-Ref'):
                        ref = base64.b64decode(self.headers['X-TTT-Ref']).decode('utf-8', 'replace')
                    aac_bench.save_clip(q.get('id', ''), q.get('lang', 'hr'), ref, q.get('kind', 'wav'), self.body())
                    return self.answer(200, {'clips': len(aac_bench.clips())})
                if parts == ['bench', 'run']:
                    eng = [e for e in q.get('engines', '').split(',') if e] or None
                    started = aac_bench.start_async(eng, self.store)
                    return self.answer(200, dict(aac_bench.status(), started=started))
                if parts == ['bench', 'clear']:
                    aac_bench.clear()
                    return self.answer(200, {'clips': 0})
            if parts == ['jobs']:
                engine = q.get('engine', ''); lang = q.get('lang') if q.get('lang') in ('en', 'auto') else 'hr'
                if engine not in ENGINES:
                    return self.answer(400, {'error': f'engine {engine or "?"} does not run in Frankfurt'})
                names = []
                h = self.headers.get('X-TTT-Names')
                if h:
                    try:
                        names = [str(n) for n in json.loads(base64.b64decode(h).decode())][:200]
                    except Exception:
                        names = []
                wav = self.body()
                if len(wav) < 100:
                    return self.answer(400, {'error': 'no audio'})
                job = Job(engine, lang, names, wav)
                with Job.lock:
                    Job.jobs[job.id] = job
                threading.Thread(target=run_job, args=(self.store, job), daemon=True).start()
                return self.answer(200, job.view())
            if len(parts) == 3 and parts[0] == 'jobs' and parts[2] == 'cancel':
                job = Job.jobs.get(parts[1])
                if not job:
                    return self.answer(404, {'error': 'no such job'})
                job.cancel()
                return self.answer(200, job.view())
        except ValueError as e:
            return self.answer(400, {'error': str(e) or 'bad request'})
        self.answer(404, {'error': 'unknown'})


def tailscale_ip():
    try:
        return subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=5).stdout.split()[0]
    except Exception:
        return None


def serve(bind=None, port=PORT, open_access=False):
    c = conf()
    Handler.store = Store(STATE_DIR)
    Handler.owner = c.get('OWNER') or os.environ.get('TTT_RELAY_OWNER')
    Handler.open_access = open_access
    relay_token()
    bind = bind or c.get('BIND') or tailscale_ip()
    if not bind:
        print('no Tailscale address yet', file=sys.stderr); sys.exit(1)
    threading.Thread(target=gc_jobs, daemon=True).start()
    srv = ThreadingHTTPServer((bind, port), Handler)
    srv.daemon_threads = True
    print(f'ttt-relay v{VERSION} on {bind}:{port}', flush=True)
    return srv


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'token':
        print(relay_token())                                   # for the install script / the Mac copy only
    else:
        serve().serve_forever()
