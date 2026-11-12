#!/usr/bin/env python3
# Runs on chromium-vm: transcribes one audio file with the YT_TRANSCRIBER engine (Groq whisper-large-v3, free-key rotation),
# language forced (default en). The paid key ending 5WeT (Queen only) is excluded. No keys are printed.
import sys, argparse, inspect
from pathlib import Path
sys.path.insert(0, str(Path.home() / "YT_TRANSCRIBER"))
import yt_transcribe as y

p = argparse.ArgumentParser(); p.add_argument("audio"); p.add_argument("out"); p.add_argument("--lang", default="en"); a = p.parse_args()
_all = y.keys
y.keys = lambda: [k for k in _all() if not k.endswith("5WeT")]
print(f"free keys in rotation: {len(y.keys())} of {len(_all())} (paid 5WeT excluded)", flush=True)
src = inspect.getsource(y.groq_call).replace('("temperature", "0")', f'("temperature", "0"), ("language", "{a.lang}")')
exec(src, y.__dict__)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
ctx = y.Ctx(out / "_work"); wd = out / "_work"
class A: local_only = False
segs, model = y.transcribe(ctx, A, Path(a.audio), wd)
(out / "transcript.txt").write_text("\n".join(f"[{y.ts(s['start'])}] {s['text']}" for s in segs) + "\n")
(out / "transcript.srt").write_text("\n".join(f"{i}\n{y.ts(s['start'], True)} --> {y.ts(s['end'], True)}\n{s['text']}\n" for i, s in enumerate(segs, 1)))
print(f"done: {len(segs)} segments, {sum(len(s['text'].split()) for s in segs)} words, engine {model}, language {a.lang}")
