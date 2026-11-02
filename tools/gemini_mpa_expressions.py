#!/usr/bin/env python3
"""MPA cover: the chosen picture (cover-listening-motionblur) with the other face expressions of the template
(MPA references/EXPRESSIONS.md), only the face changes. Marko, 2.11.2026: "Image is good. Just make different expressions
of the face by the template".   python3 tools/gemini_mpa_expressions.py <devtools tab id>"""
import sys, time, random
import gemini_mpa_drums as g
REFS = ['/home/ubuntu/refs/mpa/cover-base.png']
BASE = ('Create an image: exactly the same picture as the attached image, identical in every detail: the same man and face, '
        'the same head, pose, black shirt, frame drum, the motion blur of the striking right hand, the light and the dark '
        'background. Change only his facial expression to: ')
EXPR = [('trance', 'deep trance: eyes fully closed, heavy eyelids, face completely relaxed, lips slightly apart as if breathing out with the rhythm, calm and present.'),
        ('groove', 'concentrated groove: eyes open but lowered, looking past his hand into the drum, a faint focus between the brows, absorbed in the motion of playing.'),
        ('release', 'release: head tilted slightly back, eyes closed, mouth slightly open, the moment of surrender after a strong phrase, carried by the sound.')]
if __name__ == '__main__':
    tab = sys.argv[1]
    orig = g.call
    def call(action, **a):
        if action == 'paste_files': a['files'] = REFS
        return orig(action, **a)
    g.call = call
    for i, (k, e) in enumerate(EXPR):
        name = f'cover-{k}'
        try: res = g.one(tab, 'https://gemini.google.com/u/1/app', name, BASE + e + ' No text.')
        except Exception as ex: res = f'error {ex}'
        g.log(f'{name}: {res}')
        if res == 'limit': break
        if i < len(EXPR) - 1: time.sleep(random.uniform(40, 70))
