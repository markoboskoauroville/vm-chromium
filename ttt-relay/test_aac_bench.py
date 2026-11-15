#!/usr/bin/env python3
"""aac_bench with fake engines: one engine where AAC = WAV (SAME), one where AAC loses a word (WORSE -> keep WAV)."""
import os, subprocess, sys, tempfile
os.environ['TTT_RELAY_STATE'] = tempfile.mkdtemp(); os.environ['TTT_RELAY_CONF'] = '/nonexistent'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ttt_relay as R, aac_bench as B

d = tempfile.mkdtemp()
w = os.path.join(d, 'c.wav'); a = os.path.join(d, 'c.m4a')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=3', '-ar', '16000', '-ac', '1', w], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', w, '-c:a', 'aac', '-b:a', '32k', a], check=True)
wav, aac = open(w, 'rb').read(), open(a, 'rb').read()
REF = 'Bok Ana, javit ću ti sutra oko podneva'
for i in range(3):
    B.save_clip(f'c{i}', 'hr', REF, 'wav', wav); B.save_clip(f'c{i}', 'hr', '', 'aac', aac)
ORIG = wav

def same(bud, k, data, lang, names): return REF
def lossy(bud, k, data, lang, names): return REF if data == ORIG else 'Bok Ana, javit ti sutra oko podneva'
R.ADAPTERS['groq_v3'] = same; R.ADAPTERS['deepgram'] = lossy
st = R.Store(R.STATE_DIR); st.set_keys({'groq': ['k1'], 'deepgram': ['k2']}, True)
rep = B.run(['groq_v3', 'deepgram', 'gemini'], st)
assert rep['engines']['groq_v3']['verdict'] == 'SAME', rep
assert rep['engines']['deepgram']['verdict'] == 'WORSE' and rep['engines']['deepgram']['delta'] > 10, rep
assert 'gemini' not in rep['engines']                      # no key: not tested, not counted
assert rep['decision'] == 'WAV', rep
R.ADAPTERS['deepgram'] = same
assert B.run(['groq_v3', 'deepgram'], st)['decision'] == 'AAC'
assert abs(B.wer('a b c d', 'a x c d') - 25.0) < 1e-9 and B.wer('Čaj, šta?', 'čaj šta') == 0.0
print(open(os.path.join(B.BENCH, 'report.md')).read())
print('aac_bench: 5/5 tests passed')
