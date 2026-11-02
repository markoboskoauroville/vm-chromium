#!/usr/bin/env python3
"""gemini-worker: makes Gemini images on chromium-vm by itself, with no session connected.

Marko, 2.11.2026: "I don't want you to be connected ... prepare in the Google Drive ... the whole batch of tasks, and
then make a worker inside my virtual environment which is going to do it exactly at that time and run it", "write
results ... automatically in the same folder where the pictures are in text file", "let's start our adventure in
creating different workers for our virtual environment".

The batch lives on Google Drive: Chromium Downloads/Gemini/_batch/batch.json (+ refs/). Every round:
  1. fetch the batch and the reference photos from Drive;
  2. open Gemini in the tab of the batch's account (Chrome profile with that Google account), one tab only;
  3. for each item not yet in the Drive folder (nor in _wrong): new chat, paste two random references, the prompt,
     wait for the picture in Gemini's answer, take it 1:1 (DevTools screenshot, never a download button), save it
     under ~/Downloads/<folder>/ (vm-agent sends it to Drive and deletes it from the VM);
  4. a human pace between images; on "Your limit resets at …" stop, write RESULTS.txt, sleep until that time + 5 min.
RESULTS.txt (in the pictures' folder on Drive) and worker.log say what happened. Runs as the systemd service
chromium-vm-worker-gemini; uses vm-agent (100.102.86.30:8890) for Chrome.
"""
import datetime as dt, zoneinfo, json, os, random, re, subprocess, sys, time, urllib.request

HOME = os.path.expanduser('~')
STATE = os.path.join(HOME, '.config/chromium-vm/workers/gemini'); os.makedirs(STATE, exist_ok=True)
LOG = os.path.join(STATE, 'worker.log')
TOKEN = open(os.path.join(HOME, '.config/chromium-vm/agent-token')).read().strip()
AGENT = 'http://100.102.86.30:8890/api/'
DRIVE = 'gdrive:Chromium Downloads/'
BATCH_DRIVE = DRIVE + 'Gemini/_batch'
REFS_LOCAL = os.path.join(STATE, 'refs')
LIMIT_WORDS = ('your limit resets', 'limit resets at', 'reached your limit', 'limit for today', 'try again tomorrow',
               'daily limit', "can't create more images", 'cannot create more images', 'come back tomorrow')

def log(s):
    line = time.strftime('%Y-%m-%d %H:%M:%S UTC ') + s
    print(line, flush=True); open(LOG, 'a').write(line + '\n')

def call(action, **a):
    r = urllib.request.Request(AGENT + action, data=json.dumps(a).encode(), method='POST', headers={'X-Mantra-Token': TOKEN})
    j = json.load(urllib.request.urlopen(r, timeout=150))
    if not j.get('ok'): raise RuntimeError(j.get('error'))
    return j['result']

def ev(js, tab): return call('eval', js=js, tab=tab)
def cdp(method, tab, **p): return call('cdp', method=method, params=p, tab=tab)
def rclone(*args, timeout=600):
    return subprocess.run(['rclone', *args], capture_output=True, text=True, timeout=timeout)

# ---- the batch and what is done -----------------------------------------------------------------------------------
def fetch_batch():
    os.makedirs(REFS_LOCAL, exist_ok=True)
    rclone('copy', BATCH_DRIVE + '/refs', REFS_LOCAL)
    r = rclone('cat', BATCH_DRIVE + '/batch.json')
    return json.loads(r.stdout)

def done_names(folder):
    names = set()
    for sub in ('', '_wrong (reference captured)'):
        r = rclone('lsf', DRIVE + folder + ('/' + sub if sub else ''), '--files-only')
        names |= {os.path.splitext(x.strip())[0] for x in r.stdout.splitlines() if x.strip()}
    local = os.path.join(HOME, 'Downloads', folder)                     # saved, not yet on Drive
    if os.path.isdir(local):
        names |= {os.path.splitext(f)[0] for f in os.listdir(local)}
    return names

# ---- the Gemini tab of the batch's account -----------------------------------------------------------------------
ACCOUNT_JS = '(document.querySelector("a[aria-label*=\\"Google Account\\"]")||{}).ariaLabel||""'

def gemini_tab(account):
    tabs = call('cdp', method='Target.getTargets', params={}, tab='browser')['targetInfos']
    pages = [t for t in tabs if t['type'] == 'page']
    for t in pages:
        if 'gemini.google.com' in t['url']:
            try:
                if account in ev(ACCOUNT_JS, t['targetId']): return t['targetId']
            except Exception: pass
    for ctx in sorted({t.get('browserContextId') for t in pages}):            # try a new tab in each profile
        tid = call('cdp', method='Target.createTarget', params={'url': 'https://gemini.google.com/app', 'browserContextId': ctx}, tab='browser')['targetId']
        time.sleep(8)
        try:
            if account in ev(ACCOUNT_JS, tid): return tid
        except Exception: pass
        call('cdp', method='Target.closeTarget', params={'targetId': tid}, tab='browser')
    raise RuntimeError(f'no Chrome profile signed in to Gemini as {account}')

NEWEST = '''(() => { const im = [...document.querySelectorAll('model-response img')].filter(i => i.naturalWidth >= 700 && i.complete);
  const t = document.body.innerText.toLowerCase();
  return {n: im.length, w: im.length ? im[im.length-1].naturalWidth : 0, h: im.length ? im[im.length-1].naturalHeight : 0,
          busy: !!document.querySelector('[aria-label="Stop response"]'), tail: t.slice(0, 30000)}; })()'''   # the whole page text: the limit notice sits above the box

def limit_text(st):
    return next((w for w in LIMIT_WORDS if w in st['tail']), None)

def reset_time(tail):
    """'your limit resets at 2:35 pm' -> the next such moment (UTC, the VM's clock), else in 3 hours."""
    m = re.search(r'resets at (\d{1,2}):(\d{2})\s*([ap]m)?', tail)
    now = dt.datetime.utcnow()
    if not m: return now + dt.timedelta(hours=3)
    h, mi = int(m.group(1)), int(m.group(2))
    if m.group(3) == 'pm' and h < 12: h += 12
    if m.group(3) == 'am' and h == 12: h = 0
    t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    return t if t > now else t + dt.timedelta(days=1)

def one(tab, batch, item, refs):
    cdp('Page.navigate', tab, url='https://gemini.google.com/app'); time.sleep(7)
    for _ in range(20):
        if ev('!!document.querySelector("rich-textarea .ql-editor")', tab): break
        time.sleep(1)
    st = ev(NEWEST, tab)
    if limit_text(st): return 'limit', st
    call('paste_files', tab=tab, files=random.sample(refs, min(batch.get('refs_per_image', 2), len(refs)))); time.sleep(5)
    prompt = f"Create an image: {item['scene']} {batch['who']} {batch['style']}"
    ev(f'''(() => {{ const b = document.querySelector("rich-textarea .ql-editor"); b.focus();
        document.execCommand("insertText", false, {json.dumps(prompt)}); return true; }})()''', tab)
    time.sleep(1.5)
    if not ev('''(() => { const s = document.querySelector('button[aria-label="Send message"]');
        if (!s || s.disabled) return false; s.click(); return true; })()''', tab):
        st = ev(NEWEST, tab)
        return ('limit' if limit_text(st) else 'no-send'), st
    t0 = time.time()
    while time.time() - t0 < 200:
        time.sleep(4)
        st = ev(NEWEST, tab)
        if st['n'] > 0 and not st['busy']: break
        if not st['busy'] and time.time() - t0 > 20 and limit_text(st): return 'limit', st
    else:
        return 'timeout', st
    time.sleep(2); st = ev(NEWEST, tab); w, h = st['w'], st['h']
    ev(f'''(() => {{ const im = [...document.querySelectorAll('model-response img')].filter(i => i.naturalWidth >= 700 && i.complete);
        const d = document.createElement('div'); d.dataset.chromiumVmOverlay = 1;
        d.style.cssText = 'position:fixed;left:0;top:0;width:{w}px;height:{h}px;z-index:2147483647;background:#000';
        const c = im[im.length-1].cloneNode(); c.removeAttribute('srcset');
        c.style.cssText = 'width:{w}px;height:{h}px;max-width:none;max-height:none;display:block';
        d.appendChild(c); document.body.appendChild(d); return true; }})()''', tab)
    vp = ev('({w: innerWidth, h: innerHeight})', tab)
    big = w > vp['w'] or h > vp['h']
    if big: cdp('Emulation.setDeviceMetricsOverride', tab, width=max(vp['w'], w), height=max(vp['h'], h), deviceScaleFactor=1, mobile=False)
    time.sleep(1.5 if big else 0.7)
    try:
        r = call('capture', tab=tab, x=0, y=0, w=w, h=h, scale=1, save=f"{batch['folder']}/{item['name']}.png")
    finally:
        if big: cdp('Emulation.clearDeviceMetricsOverride', tab)
        ev('document.querySelectorAll("[data-chromium-vm-overlay]").forEach(e => e.remove())', tab)
    return f"saved {w}x{h}", st

# ---- RESULTS.txt in the pictures' folder ------------------------------------------------------------------------
def write_results(batch, rounds, pending, next_at):
    ct = lambda t: t.replace(tzinfo=dt.timezone.utc).astimezone(zoneinfo.ZoneInfo('Europe/Zagreb')).strftime('%d.%m.%Y %H:%M CT')
    lines = [f"RESULTS of the Gemini worker on chromium-vm  ({batch['name']}, {batch['account']})",
             f"written {ct(dt.datetime.utcnow())}", '',
             f"Pictures in this folder: {len(done_names(batch['folder']))}   still to make: {pending}",
             (f"Next round: {ct(next_at)} (Gemini's limit resets then)" if next_at else 'Next round: when a new batch appears'), '']
    for r in rounds[-30:]:
        lines.append(f"Round from {ct(r['start'])}: {r['made']} made, {r['failed']} failed, stopped by: {r['stop']}")
        for x in r['items'][-80:]: lines.append(f"   {x}")
        lines.append('')
    lines.append('How it works: README in markoboskoauroville/vm-chromium, workers/gemini-images. The batch: Gemini/_batch/batch.json')
    p = os.path.join(STATE, 'RESULTS.txt'); open(p, 'w').write('\n'.join(lines) + '\n')
    rclone('copyto', p, DRIVE + batch['folder'] + '/RESULTS.txt')

def main():
    rounds = json.load(open(os.path.join(STATE, 'rounds.json'))) if os.path.exists(os.path.join(STATE, 'rounds.json')) else []
    for r in rounds: r['start'] = dt.datetime.fromisoformat(r['start'])
    def save_rounds():
        json.dump([dict(r, start=r['start'].isoformat()) for r in rounds], open(os.path.join(STATE, 'rounds.json'), 'w'), indent=1)
    while True:
        try:
            batch = fetch_batch()
            refs = sorted(os.path.join(REFS_LOCAL, f) for f in os.listdir(REFS_LOCAL) if f.lower().endswith(('.jpg', '.jpeg', '.png')))
            done = done_names(batch['folder'])
            todo = [i for i in batch['items'] if i['name'] not in done]
            if not todo:
                log('batch complete; looking again in an hour'); write_results(batch, rounds, 0, None); time.sleep(3600); continue
            tab = gemini_tab(batch['account'])
            rnd = {'start': dt.datetime.utcnow(), 'made': 0, 'failed': 0, 'stop': 'running', 'items': []}
            rounds.append(rnd); log(f'round starts: {len(todo)} to make, tab {tab[:8]}')
            next_at = None
            for item in todo:
                try:
                    res, st = one(tab, batch, item, refs)
                except Exception as e:
                    res, st = f'error {e}', {'tail': ''}
                stamp = dt.datetime.now(zoneinfo.ZoneInfo('Europe/Zagreb')).strftime('%H:%M CT')
                if res.startswith('saved'):
                    rnd['made'] += 1; rnd['items'].append(f"{stamp}  {item['name']}  {res}")
                elif res == 'limit':
                    next_at = reset_time(st['tail']); rnd['stop'] = f"Gemini's limit after {rnd['made']} images"; break
                else:
                    rnd['failed'] += 1; rnd['items'].append(f"{stamp}  {item['name']}  {res}")
                    if rnd['failed'] >= 5 and rnd['made'] == 0:
                        next_at = dt.datetime.utcnow() + dt.timedelta(hours=1); rnd['stop'] = 'five failures in a row'; break
                log(f"{item['name']}: {res}")
                save_rounds(); write_results(batch, rounds, len(todo) - rnd['made'] - rnd['failed'], None)
                time.sleep(random.uniform(*batch.get('pause_seconds', [60, 150])))
            else:
                rnd['stop'] = 'the batch was finished'
            save_rounds()
            pending = len([i for i in batch['items'] if i['name'] not in done_names(batch['folder'])])
            write_results(batch, rounds, pending, next_at)
            wait = ((next_at or dt.datetime.utcnow() + dt.timedelta(minutes=30)) - dt.datetime.utcnow()).total_seconds() + 300
            log(f"round ends: {rnd['made']} made, stop: {rnd['stop']}; sleeping {wait / 60:.0f} min")
            time.sleep(max(60, wait))
        except Exception as e:
            log(f'round failed: {e}; again in 15 min'); time.sleep(900)

if __name__ == '__main__':
    main()
