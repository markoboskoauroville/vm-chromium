#!/usr/bin/env python3
# On chromium-vm: make the Studio upload dialog's visibility UNLISTED with real mouse events and verify it from the page.
# Never Public. Prints the radio states and the upload footer. Usage: yt_unlisted.py <tab-id-prefix>
import json, sys, time, urllib.request, websocket

tab = sys.argv[1]
t = [t for t in json.load(urllib.request.urlopen("http://[::1]:9222/json/list")) if t["id"].startswith(tab)][0]
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60, suppress_origin=True); n = [0]

def call(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == n[0]: return r.get("result")

def ev(e): return call("Runtime.evaluate", expression=e, returnByValue=True)["result"].get("value")
def state(): return json.loads(ev("JSON.stringify([...document.querySelectorAll('tp-yt-paper-radio-button')].map(r=>[r.getAttribute('name'),r.getAttribute('aria-checked')]))"))
def checked(): return [a for a, b in state() if b == "true"]

for k in range(5):
    if checked() == ["UNLISTED"]: break
    x, y = json.loads(ev("JSON.stringify((q=>[Math.round(q.x+q.width/2),Math.round(q.y+q.height/2)])(document.querySelector('[name=UNLISTED]').getBoundingClientRect()))"))
    call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y); time.sleep(0.4)
    call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1); time.sleep(0.1)
    call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1); time.sleep(1.5)
    print("try", k, (x, y), "checked now:", checked(), flush=True)
print("RESULT checked =", checked())
print("footer:", (ev("(document.querySelector('ytcp-uploads-dialog #footer, #dialog .footer')||{innerText:'?'}).innerText.replace(/\\n/g,' / ').slice(0,200)") or "?"))
sys.exit(0 if checked() == ["UNLISTED"] else 2)
