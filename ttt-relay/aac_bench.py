#!/usr/bin/env python3
"""AAC against WAV, on Frankfurt with Frankfurt's keys (Marko, 15.11.2026).

"Please test accuracy between AAC and Wave. The virtual machine has all API codes and all engines. Build the test for
virtual machine, see the differences. If there is a difference, keep wave, if there is the same, we go with AAC."

The phone sends its own clips (TTT ClipBuffer: his last dictations, 16 kHz WAV, with the text he finally sent as the
reference) and, for each, the AAC 32 kbit/s file its OWN encoder made (MaEncoder, the file History would keep). Here,
for every engine that has keys:

    WAV  run 1  -> transcript A      (word error rate against his text: WER_wav)
    WAV  run 2  -> transcript A2     (the engine's own run-to-run noise: |WER(A2) - WER(A)|)
    AAC  (decoded to 16 kHz WAV by ffmpeg, the same bytes every engine can take) -> transcript B   (WER_aac)

Verdict per engine: SAME when WER_aac - WER_wav <= noise + 1.0 point, else WORSE (or BETTER). Overall: AAC only if no
engine is WORSE ("if there is a difference, keep wave"). Report: bench/report.md and report.json in the relay's state
directory, and GET /bench. Text of the transcripts stays in report.json on the VM only (his voice, his words).

CLI on the VM:  sudo -u ttt-relay TTT_RELAY_STATE=/var/lib/ttt-relay python3 /usr/local/lib/chromium-vm/aac_bench.py [engines]
"""
import json, os, re, shutil, subprocess, sys, tempfile, threading, time

import ttt_relay as R

BENCH = os.path.join(R.STATE_DIR, 'bench')
DEFAULT_ENGINES = ['groq_v3', 'groq_turbo', 'gemini', 'deepgram', 'assemblyai', 'speechmatics', 'google_v1', 'cloudflare', 'elevenlabs', 'soniox', 'google_chirp']
MARGIN = 1.0          # percentage points on top of the engine's own noise

state = {'state': 'idle', 'done': 0, 'total': 0, 'note': '', 'report': None}
_lock = threading.Lock()


def bench_dir():
    os.makedirs(BENCH, mode=0o700, exist_ok=True)
    return BENCH


def save_clip(cid, lang, ref, kind, data):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', cid) or kind not in ('wav', 'aac'):
        raise ValueError('bad clip id or kind')
    d = bench_dir()
    with open(os.path.join(d, f'{cid}.{"wav" if kind == "wav" else "m4a"}'), 'wb') as f:
        f.write(data)
    meta = os.path.join(d, f'{cid}.json')
    m = {}
    if os.path.exists(meta):
        m = json.load(open(meta))
    m.update({'lang': 'en' if lang == 'en' else 'hr'})
    if ref:
        m['ref'] = ref
    json.dump(m, open(meta, 'w'))


def clips():
    d = bench_dir(); out = []
    for name in sorted(os.listdir(d)):
        if name.endswith('.json') and name != 'report.json':
            cid = name[:-5]
            w, a = os.path.join(d, cid + '.wav'), os.path.join(d, cid + '.m4a')
            if os.path.exists(w) and os.path.exists(a):
                m = json.load(open(os.path.join(d, name)))
                if m.get('ref', '').strip():
                    out.append({'id': cid, 'lang': m['lang'], 'ref': m['ref'], 'wav': w, 'aac': a})
    return out


def clear():
    shutil.rmtree(BENCH, ignore_errors=True)


def decode_aac(path):
    """The AAC file back to 16 kHz mono WAV (what the phone would hand an engine after keeping AAC in History)."""
    fd, out = tempfile.mkstemp(suffix='.wav', dir=bench_dir()); os.close(fd)
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', out],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        os.unlink(out); raise RuntimeError('ffmpeg could not decode the AAC: ' + r.stderr.decode()[:200])
    data = open(out, 'rb').read(); os.unlink(out)
    return data


# ---------------------------------------------------------------- words

def words(t):
    t = (t or '').lower()
    t = re.sub(r"[^\w\s']", ' ', t)          # \w keeps č ć đ š ž
    return t.split()


def wer(ref, hyp):
    """Word error rate in percent (Levenshtein over words)."""
    r, h = words(ref), words(hyp)
    if not r:
        return 0.0 if not h else 100.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return 100.0 * prev[-1] / len(r)


# ---------------------------------------------------------------- one transcription with the relay's own ring

def transcribe(store, engine, wav, lang, tries=3):
    ring, label = R.ENGINES[engine]
    sec = R.wav_seconds(wav)
    last = None
    for attempt in range(tries):
        job = R.Job.dummy()
        bud = R.Budget(20 + sec, job)
        try:
            return R.ring_run(store, ring, label, job, lambda k: R.ADAPTERS[engine](bud, k, wav, lang, []))
        except R.Fail as f:
            last = f
            if f.kind in ('QUOTA', 'AUTH', 'NOT_CONFIGURED'):
                raise
            time.sleep(3)
    raise last


def run(engines=None, store=None):
    store = store or R.Store(R.STATE_DIR)
    cs = clips()
    if not cs:
        raise RuntimeError('no clips with both WAV and AAC and a reference: send them from TTT first')
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('ffmpeg is not installed on the VM (sudo apt-get install -y ffmpeg)')
    with_keys = [e for e in (engines or DEFAULT_ENGINES) if e in R.ENGINES and store.n(R.ENGINES[e][0]) > 0]
    decoded = {c['id']: decode_aac(c['aac']) for c in cs}
    with _lock:
        state.update(state='running', done=0, total=len(cs) * len(with_keys), note='')
    rows = {}
    detail = []
    for e in with_keys:
        acc = {'wav': [], 'wav2': [], 'aac': [], 'skipped': 0, 'error': None}
        for c in cs:
            wav = open(c['wav'], 'rb').read()
            try:
                a = transcribe(store, e, wav, c['lang'])
                b = transcribe(store, e, decoded[c['id']], c['lang'])
                a2 = transcribe(store, e, wav, c['lang'])
                acc['wav'].append(wer(c['ref'], a)); acc['aac'].append(wer(c['ref'], b)); acc['wav2'].append(wer(c['ref'], a2))
                detail.append({'engine': e, 'clip': c['id'], 'lang': c['lang'], 'wer_wav': round(acc['wav'][-1], 1),
                               'wer_aac': round(acc['aac'][-1], 1), 'wer_wav2': round(acc['wav2'][-1], 1),
                               'wav': a, 'aac': b, 'wav2': a2})
            except R.Fail as f:
                acc['skipped'] += 1
                if f.kind in ('QUOTA', 'AUTH', 'NOT_CONFIGURED'):
                    acc['error'] = f'{f.kind.lower()}: {f.msg}'
                    with _lock:
                        state['done'] += len(cs) - cs.index(c)
                    break
            with _lock:
                state['done'] += 1
        n = len(acc['wav'])
        if n == 0:
            rows[e] = {'clips': 0, 'verdict': 'NOT TESTED', 'error': acc['error']}
            continue
        mw, ma, m2 = sum(acc['wav']) / n, sum(acc['aac']) / n, sum(acc['wav2']) / n
        noise = sum(abs(x - y) for x, y in zip(acc['wav'], acc['wav2'])) / n
        delta = ma - mw
        verdict = 'SAME' if abs(delta) <= noise + MARGIN else ('WORSE' if delta > 0 else 'BETTER')
        rows[e] = {'clips': n, 'wer_wav': round(mw, 2), 'wer_wav2': round(m2, 2), 'wer_aac': round(ma, 2),
                   'delta': round(delta, 2), 'noise': round(noise, 2), 'verdict': verdict, 'error': acc['error']}
    tested = [r for r in rows.values() if r['clips'] > 0]
    overall = 'AAC' if tested and all(r['verdict'] != 'WORSE' for r in tested) else 'WAV'
    report = {'when': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), 'clips': len(cs),
              'hr': sum(1 for c in cs if c['lang'] == 'hr'), 'en': sum(1 for c in cs if c['lang'] == 'en'),
              'engines': rows, 'decision': overall, 'margin_points': MARGIN}
    json.dump(dict(report, detail=detail), open(os.path.join(bench_dir(), 'report.json'), 'w'), ensure_ascii=False, indent=1)
    open(os.path.join(bench_dir(), 'report.md'), 'w').write(markdown(report))
    with _lock:
        state.update(state='done', report=report)
    return report


def markdown(rep):
    out = [f"# AAC 32 kbit/s against WAV 16 kHz ({rep['when']})", '',
           f"{rep['clips']} of Marko's own dictations ({rep['hr']} Croatian, {rep['en']} English), reference = the text he sent.",
           'WER = word error rate in percent, lower is better. Noise = how much the same engine differs between two WAV runs.', '',
           '| engine | clips | WER WAV | WER WAV again | WER AAC | AAC minus WAV | noise | verdict |', '|---|---|---|---|---|---|---|---|']
    for e, r in rep['engines'].items():
        if r['clips'] == 0:
            out.append(f"| {e} | 0 | | | | | | not tested ({r.get('error') or 'no answer'}) |")
        else:
            out.append(f"| {e} | {r['clips']} | {r['wer_wav']} | {r['wer_wav2']} | {r['wer_aac']} | {r['delta']:+} | {r['noise']} | {r['verdict']} |")
    out += ['', f"**Decision: {rep['decision']}** (AAC only when no engine is worse by more than its own noise + {rep['margin_points']} point)."]
    return '\n'.join(out) + '\n'


def start_async(engines=None, store=None):
    with _lock:
        if state['state'] == 'running':
            return False
        state.update(state='running', done=0, total=0, note='', report=None)

    def go():
        try:
            run(engines, store)
        except Exception as e:
            with _lock:
                state.update(state='failed', note=str(e)[:300])
    threading.Thread(target=go, daemon=True).start()
    return True


def status():
    with _lock:
        s = dict(state)
    s['clips'] = len(clips())
    return s


if __name__ == '__main__':
    eng = sys.argv[1].split(',') if len(sys.argv) > 1 else None
    rep = run(eng)
    print(markdown(rep))
