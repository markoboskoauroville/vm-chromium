#!/usr/bin/env python3
"""Gemini on chromium-vm, one image at a time in one tab, until Gemini says the day is done.

Marko, 2.11.2026: "Go and hammer my Gemini account. Let's generate images until it says that it's done for today ...
don't download. You need to take a screenshot and then save the screenshot ... When you transfer something in Gemini
inside the Downloads Chrome folder, you make a Gemini folder", "Generate my life story in different images" (yoga,
frame drumming), on the profile [address removed].

Each picture: a new chat, the prompt, wait for the image, show it alone at its natural size, DevTools screenshot of
exactly that area (1:1, lossless) saved by vm-agent under ~/Downloads/Gemini/life-story/ -> Google Drive -> deleted
from the VM. Never a download or save button.
    python3 tools/gemini_life_story.py <devtools target id of the Gemini tab> [first index]
"""
import json, os, sys, time, urllib.request

BASE = 'http://100.102.86.30:8890/api/'
TOKEN = open(os.path.expanduser('~/Downloads/API/chromium-vm-agent.txt')).read().strip()
LOG = os.path.join(os.path.dirname(__file__), 'gemini_life_story.log')

REFS = ['/home/ubuntu/refs/marko-portrait.jpg', '/home/ubuntu/refs/marko-outdoor.jpg']
WHO = ('The man in every scene is the man in the two attached reference photos: Marko, slim, completely bald head, '
       'clean-shaven, thin dark-rimmed glasses when he is older; keep his face exactly as in the photos. He likes loose '
       'Indian kurta shirts in white, magenta or orange. Only one person looks like him; others are different people.')
STYLE = ('Photorealistic cinematic photograph, natural light, landscape 16:9, rich warm colours, shallow depth of '
         'field, no text, no logos.')
SCENES = [
    ('01-adriatic-boy', 'Marko as a boy of about seven (a child version of the man in the photos) sits on the stone shore of the Adriatic sea in Rijeka, Croatia, in the 1980s, tapping a small round hand drum, the Kvarner bay and the mountains behind him, late afternoon.'),
    ('02-courtyard-teen', 'Marko as a teenager (a young version of the man in the photos) plays a hand drum in an old stone courtyard of a Croatian coastal town, friends listening on the steps, 1990s summer evening.'),
    ('03-young-dj', 'A young man in his twenties DJs with vinyl records in a crowded club in the late 1990s, headphones on one ear, lights in smoke, joy on his face.'),
    ('04-home-studio', 'A young music producer in a small home studio full of synthesizers and a mixing desk at night, a frame drum hanging on the wall.'),
    ('05-train-to-india', 'A European man in his thirties with a backpack looks out of an open Indian train window at green rice fields and palm trees, golden morning light.'),
    ('06-auroville-arrival', 'A man arrives on a red earth road in Auroville, South India, at sunrise, the golden sphere of the Matrimandir far away between tall trees.'),
    ('07-sunrise-yoga', 'A man practises yoga at sunrise on a mat on red earth in a tropical garden in Auroville, a deep forward bend, mist and birds.'),
    ('08-banyan-yoga', 'A man holds a calm yoga balance pose under a huge banyan tree with hanging roots, soft green light, peaceful.'),
    ('09-learning-daf', 'A man learns the frame drum from an older master teacher, both sitting cross-legged on a carpet in a sunlit courtyard, the teacher showing the hand position.'),
    ('10-hands-on-the-drum', 'Close-up of a man\'s hands playing a large frame drum with metal rings inside the frame, motion in the fingers, warm side light.'),
    ('11-drum-circle-fire', 'A circle of people playing frame drums around a fire at night under the stars in a tropical clearing, faces lit orange.'),
    ('12-kirtan-night', 'A kirtan band at night: a man playing frame drum, a woman at a harmonium, people singing with closed eyes, candles and flowers on the floor.'),
    ('13-sound-healing', 'A sound healing session: a man walks slowly between people lying on yoga mats, playing a frame drum softly, evening light through bamboo walls.'),
    ('14-recording-drums', 'A man records a frame drum in front of a studio microphone, headphones on, eyes closed, the mixing screen glowing in the background.'),
    ('15-teaching-online', 'A man teaches frame drumming online from his veranda, a laptop camera in front of him showing a grid of students, a drum in his hands, tropical plants behind.'),
    ('16-filmmaker', 'A man films barefoot dancers on a red earth field in Auroville with a small cinema camera on a gimbal, golden hour.'),
    ('17-ecstatic-dance', 'A DJ plays for an outdoor ecstatic dance at sunset under a big tree, dancers moving freely in colourful clothes, a frame drum beside the decks.'),
    ('18-building-apps', 'A man works late at night on a laptop full of code on a wooden table, a cup of chai, a frame drum leaning against the wall, a lamp and a gecko on the wall.'),
    ('19-monsoon-veranda', 'A man sits on a veranda during monsoon rain in South India, laptop closed, a frame drum on his lap, watching the rain, contented.'),
    ('20-garden-meditation', 'A man meditates cross-legged in a quiet garden of an Indian township, the golden sphere of the Matrimandir reflected in a pond behind him, early morning.'),
    ('21-forest-bicycle', 'A man rides an old bicycle on a red earth path through a green forest in Auroville, a frame drum in a bag on his back, dappled light.'),
    ('22-making-a-drum', 'A man makes a frame drum by hand, stretching a natural skin over a round wooden frame in a workshop, tools and drums around him.'),
    ('23-concert-stage', 'A man plays a frame drum on a small stage in a warmly lit concert hall, the audience in the dark, one spotlight, dust in the light.'),
    ('24-children-workshop', 'A man leads a drumming workshop for laughing children sitting in a circle with small frame drums in an open-air school in India.'),
    ('25-night-of-mantras', 'A night of mantras: a small group chants with a frame drum among dozens of oil lamps on a stone floor, deep blue night outside.'),
    ('26-ganges-dawn', 'A man meditates at dawn on the stone steps of the Ganges in Rishikesh, mist on the river, a frame drum beside him, temple bells far away.'),
    ('27-kvarner-sunset', 'A man in his fifties plays a frame drum on a pebble beach on the Kvarner coast of Croatia at sunset, islands on the horizon.'),
    ('28-passing-it-on', 'An older man with grey hair teaches young drummers to play frame drums in a stone courtyard, all smiling, afternoon light.'),
    ('29-three-worlds', 'Still life on a wooden floor: a yoga mat rolled out, a large frame drum, an open laptop and a mala of beads, morning light through a window.'),
    ('30-rooftop-stars', 'A man plays a frame drum on a flat rooftop under a sky full of stars and the Milky Way, a small lamp beside him, warm night.'),
]
LIMIT_WORDS = ('reached your limit', 'limit for today', 'try again tomorrow', 'daily limit', "can't create more images",
               'cannot create more images', 'image generation limit', 'come back tomorrow', 'reached the limit')

def call(action, **a):
    r = urllib.request.Request(BASE + action, data=json.dumps(a).encode(), method='POST',
                               headers={'X-Mantra-Token': TOKEN})
    j = json.load(urllib.request.urlopen(r, timeout=120))
    if not j.get('ok'): raise RuntimeError(j.get('error'))
    return j['result']

def ev(js, tab): return call('eval', js=js, tab=tab)
def cdp(method, tab, **params): return call('cdp', method=method, params=params, tab=tab)
def log(s):
    line = time.strftime('%H:%M:%S ') + s
    print(line, flush=True); open(LOG, 'a').write(line + '\n')

NEWEST = '''(() => { const im = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 700 && i.complete
  && !i.closest('[data-chromium-vm-overlay]'));
  const t = document.body.innerText.toLowerCase();
  return {n: im.length, w: im.length ? im[im.length-1].naturalWidth : 0, h: im.length ? im[im.length-1].naturalHeight : 0,
          src: im.length ? im[im.length-1].src.slice(0, 60) : '', busy: !!document.querySelector('[aria-label="Stop response"]'),
          tail: t.slice(-600)}; })()'''

def one(tab, name, scene):
    cdp('Page.navigate', tab, url='https://gemini.google.com/app'); time.sleep(6)
    for _ in range(20):
        if ev('!!document.querySelector("rich-textarea .ql-editor")', tab): break
        time.sleep(1)
    before = ev(NEWEST, tab)['n']
    prompt = f'Create an image: {scene} {WHO} {STYLE}'
    call('paste_files', tab=tab, files=REFS); time.sleep(4)          # his face, from the VM's disk
    ev(f'''(() => {{ const b = document.querySelector("rich-textarea .ql-editor"); b.focus();
        document.execCommand("insertText", false, {json.dumps(prompt)}); return true; }})()''', tab)
    time.sleep(1)
    sent = ev('''(() => { const s = document.querySelector('button[aria-label="Send message"]');
        if (!s || s.disabled) return false; s.click(); return true; })()''', tab)
    if not sent: return 'no-send'
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(4)
        st = ev(NEWEST, tab)
        if any(w in st['tail'] for w in LIMIT_WORDS): return 'limit'
        if st['n'] > before and not st['busy']: break
    else:
        return 'timeout'
    time.sleep(2); st = ev(NEWEST, tab); w, h = st['w'], st['h']
    # the picture alone, top-left, at its natural size (1 image pixel = 1 screen pixel), on black
    ev(f'''(() => {{ const im = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 700 && i.complete);
        const src = im[im.length-1]; const d = document.createElement('div'); d.dataset.chromiumVmOverlay = 1;
        d.style.cssText = 'position:fixed;left:0;top:0;width:{w}px;height:{h}px;z-index:2147483647;background:#000';
        const c = src.cloneNode(); c.removeAttribute('srcset');
        c.style.cssText = 'width:{w}px;height:{h}px;max-width:none;max-height:none;display:block';
        d.appendChild(c); document.body.appendChild(d); return true; }})()''', tab)
    cdp('Emulation.setDeviceMetricsOverride', tab, width=max(1280, w), height=max(800, h), deviceScaleFactor=1, mobile=False)
    time.sleep(1.5)
    r = call('capture', tab=tab, x=0, y=0, w=w, h=h, scale=1, save=f'Gemini/life-story/{name}.png')
    cdp('Emulation.clearDeviceMetricsOverride', tab)
    ev('document.querySelectorAll("[data-chromium-vm-overlay]").forEach(e => e.remove())', tab)
    return f"saved {w}x{h} {r['bytes']} bytes"

if __name__ == '__main__':
    tab = sys.argv[1]; start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    skip = set(os.environ.get("SKIP", "").split(","))
    for name, scene in SCENES[start:]:
        if name in skip: continue
        try:
            res = one(tab, name, scene)
        except Exception as e:
            res = f'error {e}'
        log(f'{name}: {res}')
        if res == 'limit':
            log('Gemini says the day is done: stopping.'); break
        time.sleep(3)
    log('finished')
