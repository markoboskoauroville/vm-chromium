#!/usr/bin/env python3
"""MPA Academy cover on Gemini (chromium-vm, free), request 134, Marko 2.11.2026: "I cannot spend any more credits. Go in
the virtual machine and create images with these two references ... just say same image as cover image, and face
reference needs to be refined. That's all."

Two references pasted from the VM's disk: image 1 = the cover (Desktop "cover image.png"), image 2 = his face (Desktop
"aura update 2024 - 2.png"). Saved by the same safe capture as the drums, to Gemini/MPA-Academy/cover-*.png.
    python3 tools/gemini_mpa_cover.py <devtools tab id> [tries]
"""
import sys, time, random
import gemini_mpa_drums as g

REFS = ['/home/ubuntu/refs/mpa/cover-image.png', '/home/ubuntu/refs/mpa/face-reference.jpg']
BASE = ('Create an image: the same image as image 1, exactly the same picture (the same man, pose, black shirt, frame drum, '
        'hands, framing and dark background). Refine his face and head with the face reference in image 2: the same face '
        'as image 2, his complete round bald head, a natural sharp face. Light: very low key, black around him, a hard '
        'warm back light from behind and above that draws a bright edge on the round back of his head, his ear and his '
        'shoulders, a little warm light on his face from the drum skin. No glasses, no text. Expression: ')
# expressions from Marko's references (Desktop "face expression references", frames of a frame drum film), 2.11.2026
EXPRESSIONS = [
    ('listening', 'inner listening: eyes half closed looking down at the drum skin, head tilted slightly toward the drum, lips closed and relaxed, soft brow, turned inward as if listening to the sound settle.'),
    ('trance', 'deep trance: eyes fully closed, heavy eyelids, face completely relaxed, lips slightly apart as if breathing out with the rhythm, calm and present.'),
    ('groove', 'concentrated groove: eyes open but lowered, looking past his hand into the drum, a faint focus between the brows, his face close to the rim, inside the motion of playing.'),
]
if __name__ == '__main__':
    tab = sys.argv[1]; tries = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    g.REF = None
    orig = g.call
    def call(action, **a):                       # paste both references instead of the drum reference
        if action == 'paste_files': a['files'] = REFS
        return orig(action, **a)
    g.call = call
    for i, (key, expr) in enumerate(EXPRESSIONS[:tries], 1):
        name = f'cover-{key}'
        try: res = g.one(tab, g.os.environ.get('GEMINI_APP', 'https://gemini.google.com/u/1/app'), name, BASE + expr)
        except Exception as e: res = f'error {e}'
        g.log(f'{name}: {res}')
        if res == 'limit': break
        if i < tries: time.sleep(random.uniform(45, 90))
