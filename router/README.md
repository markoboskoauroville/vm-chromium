# vm-router + VM Router (Mantra)

Marko, 2.11.2026: "please build the router for using virtual machines. If multiple sessions are using it, it should be
seamless, not getting one image from the other session and so on." The case: two Gemini jobs on chromium-vm at once
(life story on [address removed] /u/0, MPA drums on [address removed] /u/1).

## The router (`vm-router.py`, 127.0.0.1:8891, MANTRA_PORTS name `vm-router`)

Every session talks to the router on the Mac; the router talks to vm-agent (100.102.86.30:8890, token from
~/Downloads/API/chromium-vm-agent.txt). Stdlib Python, loopback only. State in ~/.config/vm-router/
(state.json, config.json, events.jsonl, router.log).

| What collided | What the router does |
|---|---|
| tab = "first matching url" | a session owns its tabs; no tab = its own first tab; another session's tab or an unowned id → 403; a url/title match only among its own tabs |
| new tabs stealing the front | `open` is `Target.createTarget {background: true}` |
| browser-wide DevTools | `cdp` with tab `browser` only for read-only methods; Target.*/Browser.* on a tab refused; open/close/adopt are the router's |
| Google account choice | `account` N stored with the session: gemini/drive/photos/mail urls without /u/ get /u/N; a navigation to another /u/M → 403 |
| clipboard, type, key, shot | one global lock, a queue in order; type/key first bring the session's tab to the front. Steps that belong together go as one `POST /s/<sid>/global {steps:[…]}` |
| capture save paths | forced under the session's folder (default Router/<name>, e.g. Gemini/life-story) |
| Drive journal with no owner | `downloads` answers with `session` per file: by folder, by the `<name>__` prefix of files put from the Mac, by `expect_download` claims (one claim at a time, so never a guess). Kept after release |
| Gemini reCAPTCHA | a minimum gap between image requests per account (config `image_gap_s` 40, `account_gap_s` per account): `paste_files` on a gemini tab waits by itself, `pace` waits on demand |
| result vs pasted preview | `gemini_state` / `gemini_wait {before, wait=300}` count only `<generated-image> img` (both are blob:) |

`GET /health`, `GET /status`, `GET /events?since=N`, `POST /session {name, account, folder, email, tab}`,
`POST /s/<sid>/api/<vm-agent action>`, `/s/<sid>/open|adopt|close|release|global|pace|expect_download|activate`,
`PUT|GET /s/<sid>/files/<name>`, `POST /selftest`, `POST /stop`.

## A session uses it

    vmr -s mpa-drums -a 1 -f Gemini/MPA-Academy open https://gemini.google.com/app   # opens /u/1/app, background
    vmr -s mpa-drums eval "document.title"
    vmr -s mpa-drums capture 0 0 1024 572 d01.png      # -> ~/Downloads/Gemini/MPA-Academy/d01.png -> Drive
    vmr -s mpa-drums release --close

From Python: `import vmr; vm = vmr.Session('life-story', account=0, folder='Gemini/life-story', tab='<id>')`, then
`vm.call('eval', js=…)` (vm-agent's shape). The two Gemini scripts go through the router when `VMR_NAME` is set;
`cvm` too (`VMR_NAME=x cvm …`); without it both still talk to vm-agent directly. `vmr` starts the router if it is down.

## The app: VM Router (Mantra) v1

`router/app/App.swift`, `./build.sh` (swiftc, signed "Mantra Apps", bundle id community.auroville.vmrouter, installed in
/Applications, relaunched through its OFF by MANTRA_SOUND_RECORDER tools/relaunch.swift; `--no-run` only installs).
Star: folder Mac, row `vmrouter`. Window: top row VM ROUTER · ON · OFF · TOP · v1 · ✕; ① START | STOP the router;
② CHECK (the router's self-test); a table SESSIONS | TABS | GLOBAL LOCK | WAITING, images per account; each session's
NAME, ACCOUNT, TAB, FOLDER, ACTIONS, LAST, NEXT IMAGE; the last events. AX ids: on, off, top, close, start, check.
**OFF quits the window's app only; the router keeps serving** (a build presses OFF and must never cut a running job).
Nothing starts at login: put `vmrouter` in ALWAYS in Swift Matrix and the Star opens the app with `--login`, which
starts the router with the window hidden.
