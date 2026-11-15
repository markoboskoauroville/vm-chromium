# ttt-relay: TTT's transcription in Frankfurt

Marko, 14.11.2026: *"only the actual transcription is going through the Frankfurt always ... it rotates the key and does
everything same as my TTT right now ... bring back the transcription plus report if something went wrong and it can also
retry multiple times and I need to see my TTT status ... I can then cancel the transcription and try different engine."*

- The phone (TTT, `engines/FrankfurtRelay.kt`) records as always and POSTs the 16 kHz WAV here; this relay runs the engine
  the H/E key chose with the phone's keys, the forward-only key ring and the 3 s × 10 retries (the same rules as TTT,
  written in `ttt_relay.py`), and the phone long-polls the status to show it under the recorder.
- Address: `http://100.102.86.30:8897` (the Tailscale address only). Who may call: a Tailscale peer whose user is OWNER in
  `/etc/ttt-relay.conf` (checked with `tailscale whois`), or `X-Mantra-Token` = `/var/lib/ttt-relay/token`.
- Keys: `/var/lib/ttt-relay/keys.json`, mode 600, user `ttt-relay`; the phone sends them by itself when they change
  (`POST /keys`, write only, never readable through the API). Ring cursors and rests: `state.json`.
- Log: `/var/lib/ttt-relay/jobs.log`, one line per job (engine, language, seconds, key number, attempts, result, ms);
  never a text, never a key.
- API: see the docstring at the top of `ttt_relay.py`.

## Install / update (on the VM, from the repo checkout ~/vm-chromium-git)

```
git pull --rebase origin main
sudo ttt-relay/install.sh        # user, state dir, unit, registry entry; enabled at boot; prints /health
```

Registry: core service `ttt-relay` (short TTT), in vmsvc.slice under ckbond, MemoryMax 300M, ~20 MB idle.

## Test

`python3 ttt-relay/test_ttt_relay.py` (fake providers on localhost): forward-only ring, same-key retries on network
errors, every key out = failed without another engine, cancel at once, keys never readable, local engines refused,
access refused without owner/token.

## AAC against WAV (15.11.2026)

Marko: *"test accuracy between AAC and Wave ... If there is a difference, keep wave, if there is the same, we go with AAC."*
`aac_bench.py` (endpoints `/bench/clip`, `/bench/run`, `GET /bench`, `/bench/clear`): TTT's button Settings > Voice
transcription buttons > Advanced > "Test AAC against WAV in Frankfurt" (or adb broadcast `dev.ttt.engines.AAC_BENCH`) sends
every kept dictation as WAV + the phone's own AAC 32 kbit/s. For each engine with keys: WAV twice (noise) and AAC decoded by
ffmpeg once; WER against the text he sent. SAME when AAC minus WAV <= noise + 1 point; decision AAC only if no engine is
WORSE. Report in /var/lib/ttt-relay/bench/report.md (+ report.json with the transcripts, on the VM only). Needs ffmpeg
(install.sh installs it). Test: `python3 ttt-relay/test_aac_bench.py`. Clear the clips after: `POST /bench/clear`.
