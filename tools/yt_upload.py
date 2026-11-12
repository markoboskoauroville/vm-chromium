#!/usr/bin/env python3
# Runs on chromium-vm. Drives YouTube Studio in the VM's Chrome (the tab of the channel's own profile) over CDP.
#   yt_upload.py prepare <tab> <video> <title> <description-file>   : file, title, description, not-for-kids, Next x3, UNLISTED; stops BEFORE the final button
#   yt_upload.py done <tab>                                         : clicks the final button (only when UNLISTED is checked)
# Visibility is always UNLISTED; the script refuses to continue if it cannot confirm it.
import sys, json, time, urllib.request, websocket

CH = "UCrmOwfCHxpNds3-COEhj2VA"

class Tab:
    def __init__(self, prefix):
        tabs = json.load(urllib.request.urlopen("http://[::1]:9222/json/list"))
        url = [t for t in tabs if t["id"].startswith(prefix)][0]["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(url, timeout=120, suppress_origin=True); self.i = 0
    def call(self, method, **params):
        self.i += 1; self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                if "error" in m: raise RuntimeError(f"{method}: {m['error']}")
                return m["result"]
    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True, userGesture=True)
        return r.get("result", {}).get("value")
    def wait(self, expr, secs=60, what=""):
        t0 = time.time()
        while time.time() - t0 < secs:
            v = self.js(expr)
            if v: return v
            time.sleep(1)
        raise RuntimeError(f"timeout waiting for {what or expr}")

def prepare(tab, video, title, desc):
    t = Tab(tab); t.call("Runtime.enable"); t.call("DOM.enable"); t.call("Page.enable")
    t.call("Page.navigate", url=f"https://studio.youtube.com/channel/{CH}/videos/upload?d=ud")
    t.wait("!!document.querySelector('input[type=file]')", 60, "file input"); print("upload dialog open", flush=True)
    obj = t.call("Runtime.evaluate", expression="document.querySelector('input[type=file]')")["result"]["objectId"]
    t.call("DOM.setFileInputFiles", files=[video], objectId=obj); print("file handed to Chrome:", video, flush=True)
    t.wait("document.querySelectorAll('#textbox').length>=2", 90, "title and description boxes")
    time.sleep(2)
    for idx, text in ((0, title), (1, desc)):
        t.js("""(()=>{const b=[...document.querySelectorAll('#textbox')][%d]; b.focus(); document.execCommand('selectAll'); document.execCommand('delete');
              return document.execCommand('insertText', false, %s);})()""" % (idx, json.dumps(text)))
        time.sleep(1)
    got = t.js("[...document.querySelectorAll('#textbox')].slice(0,2).map(b=>b.innerText.trim().length)")
    print("title/description lengths in the page:", got, "expected", len(title), len(desc.strip()), flush=True)
    t.js("document.querySelector('[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]').click()"); print("not made for kids: set", flush=True)
    for n in range(3):
        time.sleep(2); t.wait("(()=>{const b=document.querySelector('#next-button'); return b && !b.hasAttribute('disabled')})()", 120, "Next")
        t.js("document.querySelector('#next-button').click()"); print("Next", n + 1, flush=True)
    time.sleep(2)
    t.js("document.querySelector('[name=UNLISTED]').click()"); time.sleep(1)
    state = t.js("""(()=>{const r=n=>document.querySelector('[name='+n+']'); return {unlisted:r('UNLISTED')&&r('UNLISTED').getAttribute('aria-checked'),
                  public:r('PUBLIC')&&r('PUBLIC').getAttribute('aria-checked'), private:r('PRIVATE')&&r('PRIVATE').getAttribute('aria-checked')}})()""")
    print("visibility radios:", state, flush=True)
    if not state or state.get("unlisted") != "true" or state.get("public") == "true":
        raise SystemExit("REFUSING: Unlisted is not confirmed; nothing was published")
    print("READY: Unlisted confirmed, final button not yet pressed", flush=True)

def done(tab):
    t = Tab(tab); t.call("Runtime.enable")
    u = t.js("(document.querySelector('[name=UNLISTED]')||{getAttribute:()=>null}).getAttribute('aria-checked')")
    if u != "true": raise SystemExit("REFUSING: Unlisted is not checked")
    t.js("document.querySelector('#done-button').click()"); print("final button pressed", flush=True)
    time.sleep(4)
    print("dialog text:", (t.js("(document.querySelector('ytcp-prechecks-warning-dialog,ytcp-video-share-dialog,#dialog')||document.body).innerText.slice(0,300)") or "").replace("\n", " / "))

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prepare": prepare(a[1], a[2], a[3], open(a[4]).read().strip())
    elif a[0] == "done": done(a[1])
