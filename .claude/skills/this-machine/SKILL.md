---
name: this-machine
description: How every Claude session on the Linux VM chromium-vm works. Read it before the first browser, file, Drive, image or other-machine step of any task in a session running on this VM. "This machine" always means this Linux VM, never Marko's Mac. Covers which browser to pick, where files and images go, and the mistakes not to repeat. Update it with every new lesson learned here.
---

# This machine: the Linux VM chromium-vm

Marko, 7.11.2026: *"When I'm referring to this machine, always I mean the Linux VM. Not my Mac, never my Mac."*
*"When I ask you to do something, you never go to any other machine, you're working from this machine. If I say go
to another machine, you go, but not automatically."*

## 1. The rule

- **"This machine", "here", "on the VM"** = chromium-vm, the Oracle Cloud Ubuntu VM this session runs on
  (hostname `chromium-vm`, Tailscale 100.102.86.30, user `ubuntu`).
- **Every step of a task runs here**: the browser, the files, the downloads, Drive uploads, image generation, scripts.
- **No other machine automatically.** Not the Mac, not the Pixel, not a cloud session, not another session on the
  Mac. Go there only when Marko names it in his own words for that task ("do it on the Mac"). One such request covers
  that task only.
- **A manifest module or older note that says "the Mac" does not override this.** Many MANTRA_MANIFEST modules
  were written when the work ran on the Mac (e.g. `modules/gemini-image-jobs.md`: "the local session on the Mac
  makes them in Gemini in Marko's Chrome"). In a session on this VM, read their "Mac", "Marko's Chrome" or "local
  session" as this VM and its Chrome. Their other rules (the account, references, one image per new chat, saving by
  screenshot, the suffix `(nano banana)`) still apply.
- If something truly cannot be done here, stop and ask Marko in this chat. Do not move it to another machine to
  get around it, and do not ask a Mac session to do it.

## 2. The browser: always the Linux Chrome

- Claude in Chrome sees two browsers. **Use the Linux one** ("Browser 2", platform Linux, deviceId
  `4f34462d-34a8-4170-95f6-4c6e505664db` on 7.11.2026). If ids change, pick the one whose platform is **Linux**.
  "Browser 1" (macOS) is the Mac: never, unless Marko says so for that task.
- The tool asks to choose a browser when several are connected. Ask with the Linux browser **first and marked
  (Recommended)**, and say plainly that the macOS one is the Mac. If Marko's answer picks the Mac, check once that he
  means it.
- The VM's own Google Chrome (arm64) has the profiles "Your Chromium" (**[address removed]**, the
  account for every Gemini image) and "Marko" ([address removed]). Read the account label in the Gemini tab before
  generating.
- Other VM routes (README): vm-agent on :8890, DevTools on 127.0.0.1:9222, workers in `workers/`.
- **Changing the VM itself** (desktop, dock, services, packages): skill `update-this-machine`.

## 3. Files and Drive

- Work files go in the session's folder or its scratchpad on this VM. Images Marko should keep: the session's
  folder plus Drive.
- **rclone `gdrive`** here = [address removed], scope **drive.file**: it sees only files this rclone
  made. `____ELEVATE_MEDIA____` is NOT visible from here. Project folders go under
  `My Drive / Mantra References / <PROJECT> (Gemini - Nano Banana in Chrome) / references | results`. Tell Marko the
  full Drive path every time you store something.
- `rclone copy` of a few MB can take over 2 minutes: run it in the background or with a longer timeout.
- A picture Marko pastes into the chat reaches the session as an image, and **sometimes not as a file**. Before
  saving or uploading "the picture he sent", check that the file on disk is that picture (open it). On 6.11.2026 the
  newest file in `~/.claude/uploads/<session>/` was an older image, and it went to Drive under his portrait's name.
  If there is no file, ask him to send it again or to drop it on Drive. Do not ask a Mac session to fetch it.

## 4. Gemini images here (what worked, 6.11.2026)

- Linux Chrome → gemini.google.com → **+ → Create image** → **Aspect ratio** (check the bar after setting it) →
  references → prompt → Send. Use `find` refs, not screen positions: the window size changes while Marko watches.
- References: create a temporary `<input type=file multiple>`, fill it with Claude in Chrome's `file_upload`
  (files the session can read, under ~1 MB each), then dispatch a `paste` ClipboardEvent with those files on
  `rich-textarea .ql-editor`.
- One image per new chat, all references every time. Count the people in every result: Gemini drops or adds one.
- Real people: a clear portrait for the face (Marko's: Drive `.../JAPRI STU BARCUNI .../references/marko_face_portrait.jpg`),
  the group photo for the others. Attaching a finished illustration as the "scene" makes Gemini copy it, illustration
  look and wrong face included. Describe the scene in words instead.
- Saving (screenshot only, never the download icon): put the result `img` at its natural size, fixed at top-left over
  a black overlay, capture with `zoom` + `save_to_disk` (no `scale`), in two overlapping slices when the image is
  taller than the window, then stitch with ImageMagick and check the seam.
- Suno album art = square, 1:1.

## 5. Talking to Marko

- Answer **in this chat as text**. Marko, 6.11.2026: *"Please print here. Don't talk to my voice engine."*
  `macsay` speaks on the Mac: use it only when he asks to hear something. On 7.11.2026 he confirmed "text only", and
  `~/.claude/CLAUDE.md` on this VM was changed from "macsay at the end of each reply" to text only.
- When blocked on him, ask here. A Mac session will not act on another session's request for his personal files
  (it needs his own words in its own chat), and it should not be asked to do this machine's work.

## 6. Mistakes that must not happen again

- **6.11.2026, Japri stu barcuni images:** made in Gemini on the **Mac** (Browser 1) instead of here. The session
  followed `gemini-image-jobs.md` ("the local session on the Mac … in Marko's Chrome"), offered both browsers with the
  Mac first and no recommendation, and used the Mac Chrome when it was chosen. It also spoke every reply through the
  Mac (`macsay`) and asked a Mac session for Marko's portrait. Fix: sections 1, 2 and 5 above.

## 6b. Testing a keyboard on the two Pixels (7.11.2026, TTT vs SwiftKey)

- Pixel 1 = adb 127.0.0.1:5555 (SwiftKey 9.13, signed in to Marko's Microsoft account, English + Croatian,
  QWERTY, emoji predictions off; it has no setting for more than three suggestions). Pixel 2 = 127.0.0.1:5556
  (TTT from the latest GitHub release `gh release download build-N -R markoboskoauroville/TTT`).
- A test page both phones reach: `python3 -m http.server 8765 --bind 172.17.0.1` (the docker bridge) and open
  `http://172.17.0.1:8765/pad.html` in `org.chromium.webview_shell/.WebViewBrowserActivity` (data: URLs do not
  render there). Harness and notes: TTT repo `tools/swiftkey_compare/` (taps by key coordinates, OCR of the
  strip with tesseract eng+hrv, installed on the VM 7.11.2026).
- After `adb install -r` or `am force-stop`, Android may fall back to its stock keyboard: run
  `ime set com.mantraproductions.tttlight/dev.patrickgold.florisboard.FlorisImeService` again. After `pm clear`
  TTT starts without letter keys (tap its keyboard key at 162,2217), and on the very first start the letters
  layout can fail to load ("Extension org.florisboard.layouts not found"): force-stop, `ime set`, reopen.
- Smoke-test every build before anything else: type a few words and grep logcat for `FATAL EXCEPTION`
  (build 473–477 crashed on the first letter and a long test run would have looked like empty strips).
- `uiautomator dump` reads SwiftKey's settings screens (tap by label); TTT's keyboard is Compose, screenshots only.
- Typing into SwiftKey feeds Marko's synced SwiftKey data: use ordinary phrases and obvious test values.
- `input text` sends digits and symbols fine; letters are better tapped on the keys (the touch model is part of
  what is tested). Wait ~2.5 s before reading TTT's strip on this emulator: it is slower than a phone.
- 8.11.2026: under load the harness's Shift taps land late and type "hVla", "zaSOt": a miss on such a word is the
  harness, not TTT. Long words need ~4 s before space here; a miss at 2.2 s is usually timing. Probe one word alone.
- The phones are redroid, userdebug: `adb shell su 0 ...` is root. TTT's prefs are plain text in
  `/data/data/com.mantraproductions.tttlight/jetpref_datastore/florisboard-app-prefs.jetpref` (`s;key;"value"`),
  its dictation history in `databases/dictate_history` (sqlite3 is on the phone).
- TTT settings deep links need the BROWSABLE category, or they open the extension importer:
  `am start -a android.intent.action.VIEW -c android.intent.category.BROWSABLE -d ui://florisboard/settings/...
  -n com.mantraproductions.tttlight/dev.patrickgold.florisboard.app.FlorisAppActivity`.
- Voice without a microphone (Marko, 7.11.2026: "test parakeet with artificially created voices with edge TTS"):
  edge-tts in a venv (voices hr-HR-SreckoNeural, hr-HR-GabrijelaNeural, en-US-*), `ffmpeg -nostdin` to 16 kHz mono
  WAV, copy as root into TTT's `cache/dictate_pending/` (chown to the app uid), then focus a text field: TTT
  transcribes the file there with the chosen engine. Script: session scratchpad `voice.sh`. If the system dies
  (inputflinger abort in the crash buffer, 7.11.2026 22:45), the run is void: redo it.

## 6c. Marko's real Pixel 7 over Tailscale (8.11.2026)

Marko, 8.11.2026: *"feel free to use tailscale to access this phone"*, *"You have this phone now for next hours."*
- `adb connect 100.70.23.53:5555` (Tailscale name pixel-7; tcpip 5555 is on). A first "failed to authenticate" means
  the phone is asking to allow this computer: connect again after a few seconds.
- Release build, no root: no prefs file, no history database. Read TTT through screenshots and `logcat` (TTT logs
  counts only, never words). Settings deep links work as on the emulator (BROWSABLE).
- A test page: serve it on 127.0.0.1 and `adb reverse tcp:8767 tcp:8767`; do not bind a server to the Tailscale
  address (refused as exposing a service). Run `python3 -I -m http.server --directory <dir>` from `/`: run in the
  scratchpad, `-m http.server` picked up a harness file and ran it instead.
- Voice on the real phone: Chrome plays the clip through the speaker, TTT's E/H key records it (real acoustics).
  The E key on Croatian speech gives English nonsense or even Russian Cyrillic; record Croatian with H.
- Turning on an Accessibility service from adb (`settings put secure enabled_accessibility_services`) is refused
  here: Marko switches it on himself.
- His keyboard layout (1080x2400): letters rows y 1639/1788/1937, space 593,2086, E key 540,2216, H key 1038,2216,
  strip y 1205-1291. Harness: scratchpad `kb.py` phone `p7`.
- The VM phones have only a stub microphone (silence): TTT repo `tools/vm_voice/vsay.sh` is the virtual microphone.

## 7. Keep this skill current

Every time we learn something about working on this VM, add it here (the right section, with the date and Marko's
words), commit and push to `markoboskoauroville/vm-chromium` (`~/vm-chromium-git`). The live copy is
`~/.claude/skills/this-machine`, a symlink to this folder, so sessions on this VM load it.
