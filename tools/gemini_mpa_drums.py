#!/usr/bin/env python3
"""MPA Academy: the frame drum as the page's leitmotif, made by Gemini on chromium-vm (account auroville.community).

Marko, 2.11.2026 (MPA-ACADEMY session): "this drum now becoming the leitmotif from the whole page, drum only. So you need
to regenerate the same drum in different angles with Gemini over virtual machine", "this can be background during the
chat ... the classroom background", "Please use a secondary account to run this task ... arable[auroville].community".
Then: "make a series of images with this man, this shirt, this frame, in different concert environments, different
jamming environments, different classroom environments, traveling environment" (SERIES, after the drums).

Same way as gemini_life_story.py: one tab, a new chat per picture, the reference photo pasted from the VM's disk, the
picture shown alone at natural size and saved by DevTools screenshot (never a download button) under
~/Downloads/Gemini/MPA-Academy/ -> Google Drive -> deleted from the VM. A human pace between pictures.
    python3 tools/gemini_mpa_drums.py <devtools tab id> [drums|series|all] [first index]
"""
import json, os, random, sys, time, urllib.request

BASE = 'http://100.102.86.30:8890/api/'
TOKEN = open(os.path.expanduser('~/Downloads/API/chromium-vm-agent.txt')).read().strip()
LOG = os.path.join(os.path.dirname(__file__), 'gemini_mpa_drums.log')
REF = '/home/ubuntu/refs/mpa/drum-ref.png'      # Marko with his frame drum, dark wooden room (34-frame-drum-dark)

DRUM = ('The drum is exactly the frame drum in the attached photo: a large round frame drum about 45 cm across, a natural '
        'goat-skin head in warm cream and honey tones with darker mottled patches and one dark mark near the bottom, a '
        'thin dark-brown wooden frame about 6 cm deep, no jingles. Keep its look, colours and skin pattern.')
NOBODY = 'No people, no hands, no text, no logos.'
STYLE = 'Photorealistic, cinematic, warm low-key light, deep dark background, landscape 16:9, shallow depth of field.'
DRUMS = [
    ('d01-front-dark', 'The frame drum alone, seen straight from the front, floating in darkness, a soft warm light grazing the skin from the left so its texture shows.'),
    ('d02-three-quarter', 'The frame drum alone standing on its edge on a dark wooden floor, seen at a three-quarter angle so the depth of the wooden frame shows, warm lamp light from the side.'),
    ('d03-side-edge', 'The frame drum alone standing on its edge, seen almost from the side, the wooden frame and the curve of the skin catching a thin rim of warm light, black background.'),
    ('d04-back', 'The frame drum alone seen from the back: the inside of the wooden frame and the back of the skin glowing with warm light shining through it, dark room.'),
    ('d05-top-floor', 'The frame drum lying flat on an old dark wooden floor, seen from directly above, a warm pool of light on the skin, the rest of the floor fading into darkness.'),
    ('d06-skin-macro', 'Extreme close-up of the skin of the frame drum near the rim: fibres, mottled patches and the wooden edge, warm side light, very shallow depth of field.'),
    ('d07-cushion-room', 'The frame drum alone resting on a meditation cushion in an empty, dim teaching room with wooden walls, one warm lamp, quiet and inviting.'),
    ('d08-wall', 'The frame drum hanging alone on a dark wooden wall, a single warm spotlight on it, a soft shadow beside it.'),
    ('d09-classroom-wide', 'An empty frame drum classroom at evening: the frame drum on a low wooden stand in the middle, cushions in a circle on a wooden floor, warm lamps, dark wooden walls; wide calm composition with empty space on the left for text.'),
    ('d10-candles', 'The frame drum alone leaning against a wall on a wooden floor among a few candles, warm flickering light on the skin, deep dark room.'),
    ('d11-tilted-light', 'The frame drum alone tilted towards the camera, light coming through the skin from behind so it glows like the moon, darkness around.'),
    ('d12-low-angle', 'The frame drum alone standing on its edge seen from a low angle at floor level, the wooden floor stretching away into the dark, warm rim light.'),
]
WHO = ('The man is exactly the man in the attached photo: completely bald, clean-shaven, slim, in the same black shirt, '
       'holding the same frame drum. Keep his face and the drum exactly. Only one person looks like him.')
SERIES = [
    ('s01-concert-hall', 'He plays the frame drum on stage in a warmly lit concert hall, one spotlight, the audience in the dark.'),
    ('s02-concert-open-air', 'He plays the frame drum at an open-air evening concert, stage lights and a crowd, warm dusk sky.'),
    ('s03-jam-living-room', 'He jams on the frame drum with friends on guitar and oud in a cosy living room with rugs and lamps, laughing.'),
    ('s04-jam-beach-fire', 'He plays the frame drum in a jam around a beach fire at night with other musicians, sparks and stars.'),
    ('s05-classroom-circle', 'He teaches a small circle of students sitting on cushions with frame drums in a warm wooden classroom.'),
    ('s06-classroom-online', 'He teaches frame drum online in front of a laptop camera in a calm home studio, warm lamp, a second drum on the wall.'),
    ('s07-travel-train', 'He travels with the frame drum in a soft case, sitting by the window of a train through green hills, morning light.'),
    ('s08-travel-old-town', 'He walks through the stone streets of an old Mediterranean town at golden hour, the frame drum on his back.'),
    ('s09-travel-desert', 'He sits on a dune in the desert at sunset playing the frame drum, a camel caravan far behind.'),
    ('s10-jam-studio', 'He records the frame drum in a recording studio with a microphone, headphones on, eyes closed.'),
]

LIMIT_WORDS = ('reached your limit', 'limit for today', 'try again tomorrow', 'daily limit', "can't create more images",
               'cannot create more images', 'image generation limit', 'come back tomorrow', 'reached the limit', 'limit resets', 'as soon as your limit')
NEWEST = '''(() => { const im = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 700 && i.complete
  && i.closest('generated-image') && !i.closest('[data-chromium-vm-overlay]'));
  const t = document.body.innerText.toLowerCase();
  return {n: im.length, w: im.length ? im[im.length-1].naturalWidth : 0, h: im.length ? im[im.length-1].naturalHeight : 0,
          busy: !!document.querySelector('[aria-label="Stop response"]'), tail: t.slice(-600)}; })()'''

VM = None   # 2.11.2026: with VMR_NAME set, the job goes through vm-router as its own session (router/README.md)
def via_router(tab):
    global VM
    if os.environ.get('VMR_NAME'):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'router')); import vmr
        VM = vmr.Session(os.environ['VMR_NAME'], account=1, folder='Gemini/MPA-Academy', tab=tab)

def call(action, **a):
    if VM: return VM.call(action, **a)
    r = urllib.request.Request(BASE + action, data=json.dumps(a).encode(), method='POST', headers={'X-Mantra-Token': TOKEN})
    j = json.load(urllib.request.urlopen(r, timeout=120))
    if not j.get('ok'): raise RuntimeError(j.get('error'))
    return j['result']
def ev(js, tab): return call('eval', js=js, tab=tab)
def cdp(method, tab, **params): return call('cdp', method=method, params=params, tab=tab)
def log(s):
    line = time.strftime('%H:%M:%S ') + s
    print(line, flush=True); open(LOG, 'a').write(line + '\n')

def one(tab, app, name, prompt):
    cdp('Page.navigate', tab, url=app); time.sleep(6)
    for _ in range(20):
        if ev('!!document.querySelector("rich-textarea .ql-editor")', tab): break
        time.sleep(1)
    call('paste_files', tab=tab, files=[REF]); time.sleep(4)
    before = ev(NEWEST, tab)['n']
    ev(f'''(() => {{ const b = document.querySelector("rich-textarea .ql-editor"); b.focus();
        document.execCommand("insertText", false, {json.dumps(prompt)}); return true; }})()''', tab)
    time.sleep(1)
    if not ev('''(() => { const s = document.querySelector('button[aria-label="Send message"]');
        if (!s || s.disabled) return false; s.click(); return true; })()''', tab): return 'no-send'
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(4); st = ev(NEWEST, tab)
        if any(w in st['tail'] for w in LIMIT_WORDS): return 'limit'
        if st['n'] > before and not st['busy']: break
    else:
        return 'timeout'
    time.sleep(2); st = ev(NEWEST, tab); w, h = st['w'], st['h']
    ev(f'''(() => {{ const im = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 700 && i.complete && i.closest('generated-image'));
        const src = im[im.length-1]; const d = document.createElement('div'); d.dataset.chromiumVmOverlay = 1;
        d.style.cssText = 'position:fixed;left:0;top:0;width:{w}px;height:{h}px;z-index:2147483647;background:#000';
        const c = src.cloneNode(); c.removeAttribute('srcset');
        c.style.cssText = 'width:{w}px;height:{h}px;max-width:none;max-height:none;display:block';
        d.appendChild(c); document.body.appendChild(d); return c.decode().then(() => true, () => false); }})()''', tab)
    vp = ev('({w: innerWidth, h: innerHeight})', tab)
    big = w > vp['w'] or h > vp['h']
    if big: cdp('Emulation.setDeviceMetricsOverride', tab, width=max(vp['w'], w), height=max(vp['h'], h), deviceScaleFactor=1, mobile=False)
    time.sleep(1.5 if big else 0.5)
    # the cover must stand while the picture is taken (2.11.2026: two saves were the Gemini page itself)
    if not ev("!!document.querySelector('[data-chromium-vm-overlay] img') && document.querySelector('[data-chromium-vm-overlay] img').complete", tab):
        ev('document.querySelectorAll("[data-chromium-vm-overlay]").forEach(e => e.remove())', tab); return 'no-cover'
    r = call('capture', tab=tab, x=0, y=0, w=w, h=h, scale=1, save=f'Gemini/MPA-Academy/{name}.png')
    if not ev("!!document.querySelector('[data-chromium-vm-overlay] img') && document.querySelector('[data-chromium-vm-overlay] img').complete", tab):
        return f"cover-lost {w}x{h} (saved file is bad: {r.get('path', '')})"
    if big: cdp('Emulation.clearDeviceMetricsOverride', tab)
    ev('document.querySelectorAll("[data-chromium-vm-overlay]").forEach(e => e.remove())', tab)
    return f"saved {w}x{h} {r['bytes']} bytes"

if __name__ == '__main__':
    tab = sys.argv[1]; via_router(tab); which = sys.argv[2] if len(sys.argv) > 2 else 'all'; start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    app = os.environ.get('GEMINI_APP', 'https://gemini.google.com/u/1/app')     # u/1 = auroville.community once signed in
    jobs = []
    if which in ('drums', 'all'): jobs += [(n, f'Create an image: {s} {DRUM} {NOBODY} {STYLE}') for n, s in DRUMS]
    if which in ('series', 'all'): jobs += [(n, f'Create an image: {s} {WHO} {DRUM} Photorealistic, cinematic, landscape 16:9, no text, no logos.') for n, s in SERIES]
    # Marko, 2.11.2026: "Your goal is to generate 55 images." After the list, variations of both lists until 55 are saved
    # (MADE_BEFORE = pictures already in Drive's Gemini/MPA-Academy from an earlier run).
    TARGET = int(os.environ.get('TARGET', '55')); made_before = int(os.environ.get('MADE_BEFORE', '0'))
    VARS = ['another camera angle of the same scene', 'the same scene in soft blue-hour light', 'the same scene by candle light',
            'a closer, more intimate framing of the same scene', 'the same scene seen from further away, more of the room']
    jobs = jobs[start:]
    skip = set(os.environ.get('SKIP', '').split(','))     # names already saved (e.g. after a limit)
    jobs = [(n, p) for n, p in jobs if n not in skip]
    for v in VARS:
        jobs += [(f'{n}-v{VARS.index(v) + 2}', f'{p[:-1]} ({v}).') for n, p in
                 [(n, f'Create an image: {s} {DRUM} {NOBODY} {STYLE}') for n, s in DRUMS] +
                 [(n, f'Create an image: {s} {WHO} {DRUM} Photorealistic, cinematic, landscape 16:9, no text, no logos.') for n, s in SERIES]]
    jobs = [(n, p) for n, p in jobs if n not in skip]
    made = 0
    for name, prompt in jobs:
        if made_before + made >= TARGET: log(f'target reached: {made_before + made} pictures'); break
        try: res = one(tab, app, name, prompt)
        except Exception as e: res = f'error {e}'
        if res.startswith('saved'): made += 1
        log(f'{name}: {res}  (made: {made_before + made} of {TARGET})')
        if res == 'limit': log('Gemini says the day is done on this account: stopping.'); break
        time.sleep(random.uniform(45, 100))
    log('finished')
