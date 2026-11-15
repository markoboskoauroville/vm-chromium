#!/usr/bin/env python3
"""santoshi-hls-proxy (15.11.2026): the small door between the Cloudflare Tunnel (live.santoshiband.org) and MediaMTX's HLS (:8888).
Why: MediaMTX gives every reader a session (?session=<id> on every URI) and that makes every viewer's segment URL different, so
Cloudflare would cache nothing; it also sends "private, no-cache". This proxy holds ONE MediaMTX session itself, removes ?session= from
the playlists, and answers segments/parts with public max-age=60 (their names are unique per stream), so every viewer asks for the same
URL and Cloudflare's default cache (.mp4 is a cached extension) keeps each piece once per location. Playlists stay no-cache; LL-HLS
blocking reloads (_HLS_msn/_HLS_part) pass through. Only GET /santoshi/<name>.(m3u8|mp4); everything else 404. Listens on 127.0.0.1 only.
Nothing about viewers is logged."""
import collections, http.client, http.server, re, ssl, threading, time, urllib.parse
LISTEN = ("127.0.0.1", 18888)
PATH = re.compile(r"^/(santoshi)/([A-Za-z0-9_.-]{1,96})\.(m3u8|mp4)$")
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE   # loopback to MediaMTX's own TLS port
sess, lock = {}, threading.Lock()
# counts only (no viewer data): what reaches the VM per 30 s, to see whether Cloudflare's cache works (one request per segment name and
# Cloudflare location = working). Logged to the journal.
stat = collections.Counter(); names = collections.defaultdict(set)
def count(kind, name=None, colo=None):
    with lock:
        stat[kind] += 1
        if name: names[kind].add(name)
        if colo: names["colo"].add(colo)
def report():
    while True:
        time.sleep(30)
        with lock:
            line = " ".join(f"{k}={v}" for k, v in sorted(stat.items())) + " " + " ".join(f"distinct_{k}={len(v)}" for k, v in sorted(names.items()) if k != "colo")
            colos = ",".join(sorted(names["colo"])); stat.clear(); names.clear()
        if line.strip(): print(f"30s: {line} colos={colos}", flush=True)

local = threading.local()
def up(path, timeout=10):
    # one kept-alive TLS connection to MediaMTX per thread (a new TLS handshake per request cost most of the CPU under load)
    for attempt in range(2):
        c = getattr(local, "c", None)
        if c is None: c = local.c = http.client.HTTPSConnection("127.0.0.1", 8888, context=CTX, timeout=timeout)
        try:
            c.timeout = timeout
            c.request("GET", path, headers={"host": "relay.ples-duse.org:8888"}); r = c.getresponse(); body = r.read()
            if r.getheader("connection", "").lower() == "close": c.close(); local.c = None
            return r.status, body
        except (http.client.HTTPException, OSError):
            try: c.close()
            except Exception: pass
            local.c = None
            if attempt: raise

# 15.11.2026 (102 readers: ~80 playlist requests a second, each one fetched from MediaMTX and rewritten): every playlist is fetched from
# MediaMTX at most once per PL_TTL and rewritten once; everyone in between gets the same bytes. Playlists are served as PLAIN HLS (the
# LL-HLS lines are removed), so no player sends blocking reloads; _HLS_msn/_HLS_part from an old page are ignored.
PL_TTL = 0.5
LL = re.compile(rb"^#EXT-X-(PART|PART-INF|PRELOAD-HINT|SERVER-CONTROL|RENDITION-REPORT|SKIP)\b[^\n]*\n?", re.M)
SIDB = re.compile(rb"[?&]session=[0-9a-f-]+")
plc, pl_locks = {}, {}
def plain(body):
    b = LL.sub(b"", SIDB.sub(b"", body))
    lines = b.rstrip(b"\n").split(b"\n")
    while lines and (lines[-1].startswith(b"#EXT-X-PROGRAM-DATE-TIME") or lines[-1].startswith(b"#EXTINF") or not lines[-1].strip()): lines.pop()
    return b"\n".join(lines) + b"\n"
def playlist(stream, name):
    key = (stream, name); now = time.monotonic()
    hit = plc.get(key)
    if hit and hit[0] > now: return 200, hit[1], True
    with lock: l = pl_locks.setdefault(key, threading.Lock())
    with l:   # one upstream fetch per playlist; the others wait for it and take its copy
        hit = plc.get(key)
        if hit and hit[0] > time.monotonic(): return 200, hit[1], True
        st, body = new_session(stream) if name == "index.m3u8" else fetch(stream, name, {})
        if st != 200: return st, b"", False
        body = plain(body)
        plc[key] = (time.monotonic() + (5 if name == "index.m3u8" else PL_TTL), body)
        return 200, body, False

def new_session(stream):
    st, body = up(f"/{stream}/index.m3u8?cookieCheck=1")
    m = re.search(rb"[?&]session=([0-9a-f-]{8,64})", body) if st == 200 else None
    with lock:
        if m: sess[stream] = m.group(1).decode()
    return st, body

def fetch(stream, name, extra):
    for _ in range(2):
        s = sess.get(stream) or (new_session(stream) and sess.get(stream))
        if not s: return 404, b""
        q = dict(extra); q["session"] = s
        st, body = up(f"/{stream}/{name}?{urllib.parse.urlencode(q)}", timeout=15 if extra else 10)
        if st in (401, 403) or 300 <= st < 400:
            with lock: sess.pop(stream, None)
            continue
        return st, body
    return 502, b""

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def send(self, st, body, ctype, cc):
        self.send_response(st); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", cc); self.send_header("access-control-allow-origin", "*"); self.end_headers()
        if self.command == "GET": self.wfile.write(body)
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); m = PATH.match(u.path)
        if not m: return self.send(404, b"not found", "text/plain", "no-store")
        stream, base, ext = m.groups(); name = f"{base}.{ext}"
        ray = self.headers.get("cf-ray", ""); colo = ray.rsplit("-", 1)[-1] if "-" in ray else None
        kind = "playlist" if ext == "m3u8" else ("part" if "_part" in base else "segment")
        count(kind + ("_q" if u.query else ""), name if ext == "mp4" else None, colo)
        if self.headers.get("cookie"): count("with_cookie")
        try:
            if ext == "m3u8":
                st, body, shared = playlist(stream, name)
                if shared: count("playlist_shared")
            else:
                st, body = fetch(stream, name, {})
        except Exception:
            return self.send(502, b"relay error", "text/plain", "no-store")
        if st != 200: return self.send(404 if st == 404 else 502, b"not live" if st == 404 else b"relay error", "text/plain", "no-store")
        if ext == "m3u8":
            # no-cache for browsers: the zone's Browser Cache TTL (4 h) would turn a short max-age into hours; Cloudflare does not cache
            # .m3u8 by default (no Cache Rule on this zone), so the shared copy here is what spares MediaMTX
            return self.send(200, body, "application/vnd.apple.mpegurl", "no-cache")
        return self.send(200, body, "video/mp4", "public, max-age=60, s-maxage=60")

if __name__ == "__main__":
    threading.Thread(target=report, daemon=True).start()
    http.server.ThreadingHTTPServer.daemon_threads = True
    http.server.ThreadingHTTPServer(LISTEN, H).serve_forever()
