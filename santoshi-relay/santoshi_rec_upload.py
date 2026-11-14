#!/usr/bin/env python3
"""santoshi-rec-upload: the relay's recording to Google Drive (Marko, 14.11.2026: one stream to Frankfurt, recorded).

MediaMTX (santoshi-relay) writes the stream in 1 min fmp4 pieces to /srv/santoshi-rec/santoshi/. This loop (user ubuntu, the
VM's rclone remote gdrive:, scope drive.file) puts them on Drive in the same layout as the browser recording of the admin page:

    Santoshi Band live (relay) / Santoshi live YYYY-MM-DD HH-MM (green) / Video (blue) / <pieces>.mp4
                                                                     + Google Docs "Chat" and "Stream statistics"

"(relay)": drive.file lets each app see only its own files, so the VM cannot write into the folder the admin page made.
A stream = pieces with less than 3 min between them; its name is the Croatia time of its first piece. A piece is finished when a
newer one exists, or nothing was written to it for 75 s. The two Docs are rewritten every 2 min while the stream runs and once
after it ends, from the site's /api/relay (Bearer = the relay key in /etc/santoshi-relay/key; chat and the room's statistics).
State: ~/.local/state/santoshi-relay/state.json. Status line: /srv/santoshi-rec/upload-status.json. No key is ever printed.
"""
import configparser, datetime as dt, html, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

REC = os.environ.get("REC_DIR", "/srv/santoshi-rec/santoshi")
STATE = os.path.expanduser("~/.local/state/santoshi-relay/state.json")
STATUS = "/srv/santoshi-rec/upload-status.json"
CONF = os.path.expanduser("~/.config/rclone/rclone.conf")
SITE = os.environ.get("SITE", "https://santoshi-band.pages.dev")
KEYFILE = "/etc/santoshi-relay/key"
ROOT_NAME = "Santoshi Band live (relay)"
GAP, IDLE, DOCS_EVERY = 180, 75, 120
HR = ZoneInfo("Europe/Zagreb")
NAME = re.compile(r"^(\d{4})-(\d\d)-(\d\d)_(\d\d)-(\d\d)-(\d\d)-(\d+)\.mp4$")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"sessions": [], "done": {}}


def save(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    t = STATE + ".tmp"
    json.dump(s, open(t, "w"), indent=1)
    os.replace(t, STATE)


def start_of(f):
    m = NAME.match(f)
    if not m:
        return None
    y, mo, d, h, mi, s, us = m.groups()
    return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), tzinfo=dt.timezone.utc).timestamp()


# --- Drive: the access token rclone keeps fresh in its own config -----------------------------------------------------
_tok = {"v": None, "exp": 0}


def token():
    if _tok["v"] and _tok["exp"] - time.time() > 60:
        return _tok["v"]
    for _ in range(3):
        c = configparser.ConfigParser()
        c.read(CONF)
        t = json.loads(c["gdrive"]["token"])
        exp = dt.datetime.fromisoformat(re.sub(r"(\.\d{6})\d*", r"\1", t["expiry"]).replace("Z", "+00:00")).timestamp()
        if exp - time.time() > 60:
            _tok.update(v=t["access_token"], exp=exp)
            return _tok["v"]
        # rclone refreshes only an expired token: wait for it to expire, then let rclone touch Drive once
        wait = max(0, exp - time.time() + 2)
        if wait > 0:
            time.sleep(min(wait, 70))
        subprocess.run(["rclone", "lsf", "gdrive:", "--max-depth", "1", "--dirs-only"], capture_output=True, timeout=120)
    raise RuntimeError("no Drive token from rclone")


def drive(method, path, body=None, ctype="application/json", base="https://www.googleapis.com"):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Authorization": "Bearer " + token(), "Content-Type": ctype})
    with urllib.request.urlopen(r, timeout=60) as x:
        return json.loads(x.read() or b"{}")


def folder(name, parent=None, color=None):
    q = "name='%s' and mimeType='application/vnd.google-apps.folder' and trashed=false and '%s' in parents" % (
        name.replace("'", "\\'"), parent or "root")
    r = drive("GET", "/drive/v3/files?fields=files(id)&q=" + urllib.parse.quote(q))
    if r.get("files"):
        return r["files"][0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent] if parent else ["root"]}
    if color:
        meta["folderColorRgb"] = color
    return drive("POST", "/drive/v3/files?fields=id", meta)["id"]


def put_doc(doc_id, name, parent, page):
    if doc_id:
        drive("PATCH", "/upload/drive/v3/files/%s?uploadType=media&fields=id" % doc_id, page.encode(), "text/html; charset=UTF-8")
        return doc_id
    b = "sb%d" % int(time.time() * 1000)
    meta = json.dumps({"name": name, "mimeType": "application/vnd.google-apps.document", "parents": [parent]})
    body = ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n%s\r\n--%s\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n%s\r\n--%s--"
            % (b, meta, b, page, b)).encode()
    return drive("POST", "/upload/drive/v3/files?uploadType=multipart&fields=id", body, "multipart/related; boundary=" + b)["id"]


# --- the site: chat + statistics of the stream ------------------------------------------------------------------------
def site_log():
    try:
        key = open(KEYFILE).read().strip()
    except Exception:
        return None
    r = urllib.request.Request(SITE + "/api/relay", headers={"Authorization": "Bearer " + key, "User-Agent": "santoshi-relay"})
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return json.loads(x.read())
    except Exception as e:
        log("site:", type(e).__name__)
        return None


CSS = ('<style>body{font-family:Arial,sans-serif}h1{font-size:22pt}h2{font-size:15pt;color:#7a4b00}table{border-collapse:collapse}'
       'td,th{border:1px solid #bbb;padding:3px 8px;font-size:10pt}th{background:#f1e8d8;text-align:left}</style>')
e = lambda t: html.escape(str(t))
hz = lambda ms, sec=False: dt.datetime.fromtimestamp(ms / 1000, HR).strftime("%H:%M:%S" if sec else "%H:%M")
dz = lambda ms: dt.datetime.fromtimestamp(ms / 1000, HR).strftime("%d/%m/%Y")


def dur(ms):
    s = round(ms / 1000)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return "%d h %d min %d s" % (h, m, s) if h else "%d min %d s" % (m, s) if m else "%d s" % s


def kv(rows):
    return "<table>" + "".join("<tr><td><b>%s</b></td><td>%s</td></tr>" % (e(a), e(b)) for a, b in rows) + "</table>"


def cnts(o):
    if not o:
        return "<p><i>None yet.</i></p>"
    return "<table><tr><th>Value</th><th>Viewers</th></tr>" + "".join(
        "<tr><td>%s</td><td>%d</td></tr>" % (e("unknown" if k == "?" else k), o[k]) for k in sorted(o, key=lambda k: -o[k])) + "</table>"


def chat_html(stamp, chat):
    now = dt.datetime.now(HR).strftime("%d/%m/%Y %H:%M:%S")
    rows = "".join("<tr><td>%s</td><td><b>%s%s</b></td><td>%s</td></tr>" % (hz(m["ts"], True), e(m["name"]), " (band)" if m.get("band") else "", e(m["text"]))
                   for m in chat)
    return ('<html><head><meta charset="utf-8">' + CSS + '</head><body><h1>Santoshi live chat %s</h1><p><b>Messages:</b> %d &nbsp; <b>Updated:</b> %s</p><h2>Chat</h2>'
            % (e(stamp), len(chat), now) + ("<table><tr><th>Time</th><th>Name</th><th>Message</th></tr>" + rows + "</table>" if chat else "<p><i>No messages yet.</i></p>")
            + "<p><i>Recorded by the Santoshi relay (Frankfurt).</i></p></body></html>")


def stat_html(stamp, s, relay):
    c = s["chat"]
    mx = max(1, s["peak"])
    summ = kv([["Stream start (Croatia time)", dz(s["start"]) + " " + hz(s["start"], True)],
               ["Now (still live)" if s["live"] else "Stream stop (Croatia time)", dz(s["end"]) + " " + hz(s["end"], True)],
               ["Duration", dur(s["duration"])], ["Watching now", s["now"]], ["Peak viewers", "%d at %s" % (s["peak"], hz(s["peakAt"], True))],
               ["Average viewers", "%.1f" % s["average"]], ["Unique viewers", s["unique"]], ["Total joins", "%d (%d of them reconnects)" % (s["joins"], s["reconnects"])],
               ["Average watch time per viewer", dur(s["avgWatch"])], ["Median watch time", dur(s["medianWatch"])],
               ["Longest continuous viewer", dur(s["longest"])], ["Viewers who stayed 5 min or more", s["stayed5"]]])
    rows = "".join('<tr><td>%s</td><td>%d</td><td><font face="Courier New" color="#c77700">%s</font></td></tr>'
                   % (hz(r[0]), r[1], "&#9608;" * max(1, round(r[1] / mx * 30)) if r[1] else "") for r in s["series"])
    rel = kv([["Pieces on Drive", relay["pieces"]], ["Recorded", dur(relay["seconds"] * 1000)], ["Size on Drive", "%.0f MB" % (relay["bytes"] / 1e6)]])
    return ('<html><head><meta charset="utf-8">' + CSS + '</head><body><h1>Stream statistics %s</h1><p><b>Updated:</b> %s%s</p><h2>Summary</h2>%s'
            % (e(stamp), dt.datetime.now(HR).strftime("%d/%m/%Y %H:%M:%S"), " (stream is live, numbers keep growing)" if s["live"] else "", summ)
            + "<h2>Viewers over time</h2><p>One row per %d min (Croatia time), the highest number watching in that slot.</p>" % (s["slot"] // 60000)
            + "<table><tr><th>Time</th><th>Watching</th><th>Bar</th></tr>" + rows + "</table>"
            + "<h2>Chat</h2>" + kv([["Messages from viewers", c["viewerMessages"]], ["Messages from the band", c["bandMessages"]], ["People who chatted", c["chatters"]],
                                     ["Busiest minute", "%s (%d messages)" % (hz(c["busiestMinute"]), c["busiestCount"]) if c["busiestCount"] else "none"]])
            + "<h2>Countries</h2>" + cnts(s["countries"]) + "<h2>Devices</h2>" + cnts(s["devices"])
            + "<h2>Recording (relay)</h2>" + rel + "<p><i>Counts only: no names, no IP addresses.</i></p></body></html>")


# --- the loop ---------------------------------------------------------------------------------------------------------
def pieces():
    try:
        fs = [f for f in os.listdir(REC) if NAME.match(f)]
    except FileNotFoundError:
        return []
    out = []
    for f in sorted(fs):
        p = os.path.join(REC, f)
        try:
            st = os.stat(p)
        except FileNotFoundError:
            continue
        out.append({"f": f, "p": p, "t0": start_of(f), "mt": st.st_mtime, "size": st.st_size})
    return out


def ensure_folders(sess):
    if sess.get("video"):
        return
    root = folder(ROOT_NAME)
    sess["folder"] = folder(sess["name"], root, "#16a766")
    sess["video"] = folder("Video", sess["folder"], "#4986e7")
    log("Drive folders made for", sess["name"])


def upload(sess, batch):
    """One rclone call for every finished piece of a stream: rclone's shared Google client allows few requests a minute
    (403 "Queries per minute" on 15.11.2026 made one call per piece take about a minute)."""
    lst = os.path.join(os.path.dirname(STATE), "batch.txt")
    with open(lst, "w") as f:
        f.write("".join(pc["f"] + "\n" for pc in batch))
    r = subprocess.run(["rclone", "copy", REC, "gdrive,root_folder_id=%s:" % sess["video"], "--files-from-raw", lst, "--no-traverse",
                        "--transfers", "2", "--retries", "5", "--low-level-retries", "20", "--tpslimit", "4"],
                       capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError("rclone: " + (r.stderr.strip().splitlines() or ["?"])[-1][:200])


def docs(sess, final=False):
    j = site_log()
    if not j or "stats" not in j:
        return False
    ensure_folders(sess)
    stamp = sess["name"].replace("Santoshi live ", "")
    relay = {"pieces": sess.get("pieces", 0), "seconds": sess.get("seconds", 0), "bytes": sess.get("bytes", 0)}
    sess["chat_doc"] = put_doc(sess.get("chat_doc"), "Chat", sess["folder"], chat_html(stamp, j.get("chat", [])))
    sess["stats_doc"] = put_doc(sess.get("stats_doc"), "Stream statistics", sess["folder"], stat_html(stamp, j["stats"], relay))
    sess["docs_at"] = time.time()
    if final:
        sess["final"] = True
    return True


def status(st, note):
    cur = st["sessions"][-1] if st["sessions"] else None
    o = {"at": int(time.time()), "note": note, "session": cur and cur["name"], "pieces": cur and cur.get("pieces", 0),
         "waiting": cur and cur.get("waiting", 0)}
    try:
        t = STATUS + ".tmp"
        json.dump(o, open(t, "w"))
        os.replace(t, STATUS)
    except Exception:
        pass


def flush(st, batch):
    """Uploads the collected pieces of one stream (pieces under 20 kB, the stubs of a reconnect, are only marked done)."""
    if not batch:
        return
    sess = batch[0][0]
    real = [pc for _, pc in batch if pc["size"] >= 20_000]
    if real:
        ensure_folders(sess)
        upload(sess, real)
    for _, pc in batch:
        st["done"][pc["f"]] = sess["name"]
    sess["pieces"] = sess.get("pieces", 0) + len(real)
    sess["bytes"] = sess.get("bytes", 0) + sum(pc["size"] for pc in real)
    sess["seconds"] = sess.get("seconds", 0) + sum(max(1, int(pc["mt"] - pc["t0"])) for pc in real)
    sess["waiting"] = 0
    log("uploaded %d piece(s), %.1f MB -> %s/Video" % (len(real), sum(pc["size"] for pc in real) / 1e6, sess["name"]))
    batch.clear()
    save(st)


def step(st):
    batch = []
    ps = pieces()
    now = time.time()
    newest = ps[-1]["f"] if ps else None
    for pc in ps:
        if pc["f"] in st["done"]:
            continue
        finished = pc["f"] != newest or now - pc["mt"] > IDLE
        last = st["sessions"][-1] if st["sessions"] else None
        if last is None or pc["t0"] - last.get("end", 0) > GAP:
            if last is not None and pc["t0"] - last.get("end", 0) > GAP and not last.get("final"):
                docs(last, final=True)
            name = "Santoshi live " + dt.datetime.fromtimestamp(pc["t0"], HR).strftime("%Y-%m-%d %H-%M")
            last = {"name": name, "start": pc["t0"], "end": pc["t0"]}
            st["sessions"].append(last)
            st["sessions"] = st["sessions"][-50:]
            log("new stream:", name)
        last["end"] = max(last.get("end", 0), pc["mt"])
        if not finished:
            last["waiting"] = 1
            break
        if batch and batch[0][0] is not last:
            flush(st, batch)
        batch.append((last, pc))
    flush(st, batch)
    # forget pieces MediaMTX has already deleted (recordDeleteAfter)
    have = {p["f"] for p in ps}
    st["done"] = {k: v for k, v in st["done"].items() if k in have}
    cur = st["sessions"][-1] if st["sessions"] else None
    if cur and not cur.get("final"):
        running = ps and now - ps[-1]["mt"] < IDLE
        if running and now - cur.get("docs_at", 0) > DOCS_EVERY:
            docs(cur)
        elif not running and now - cur.get("end", 0) > GAP and all(p["f"] in st["done"] for p in ps):
            docs(cur, final=True)
            log("stream finished:", cur["name"], cur.get("pieces", 0), "pieces")
    save(st)
    status(st, "ok")


def main():
    st = load()
    log("santoshi-rec-upload: watching", REC)
    while True:
        try:
            step(st)
        except Exception as x:
            log("error:", type(x).__name__, str(x)[:200])
            status(st, "error: " + type(x).__name__)
            time.sleep(30)
        time.sleep(30)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        s = load(); step(s); print(json.dumps(s["sessions"][-1:] if s["sessions"] else [], indent=1))
    else:
        main()
