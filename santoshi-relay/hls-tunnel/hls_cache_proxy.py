#!/usr/bin/env python3
"""santoshi-hls-proxy (15.11.2026): the small door between the Cloudflare Tunnel (live.santoshiband.org) and MediaMTX's HLS (:8888).
Why: MediaMTX gives every reader a session (?session=<id> on every URI) and that makes every viewer's segment URL different, so
Cloudflare would cache nothing; it also sends "private, no-cache". This proxy holds ONE MediaMTX session itself, removes ?session= from
the playlists, and answers segments/parts with public max-age=60 (their names are unique per stream), so every viewer asks for the same
URL and Cloudflare's default cache (.mp4 is a cached extension) keeps each piece once per location. Playlists stay no-cache; LL-HLS
blocking reloads (_HLS_msn/_HLS_part) pass through. Only GET /santoshi/<name>.(m3u8|mp4); everything else 404. Listens on 127.0.0.1 only.
Nothing about viewers is logged."""
import http.client, http.server, re, ssl, threading, urllib.parse
LISTEN = ("127.0.0.1", 8896)
PATH = re.compile(r"^/(santoshi)/([A-Za-z0-9_.-]{1,96})\.(m3u8|mp4)$")
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE   # loopback to MediaMTX's own TLS port
SID = re.compile(r"[?&]session=[0-9a-f-]+")
sess, lock = {}, threading.Lock()

def up(path, timeout=10):
    c = http.client.HTTPSConnection("127.0.0.1", 8888, context=CTX, timeout=timeout)
    try:
        c.request("GET", path, headers={"host": "relay.ples-duse.org:8888"}); r = c.getresponse(); return r.status, r.read()
    finally: c.close()

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
        try:
            if name == "index.m3u8":
                st, body = new_session(stream)
            else:
                q = urllib.parse.parse_qs(u.query)
                extra = {k: q[k][0] for k in ("_HLS_msn", "_HLS_part", "_HLS_skip") if k in q}
                st, body = fetch(stream, name, extra)
        except Exception:
            return self.send(502, b"relay error", "text/plain", "no-store")
        if st != 200: return self.send(404 if st == 404 else 502, b"not live" if st == 404 else b"relay error", "text/plain", "no-store")
        if ext == "m3u8":
            return self.send(200, SID.sub("", body.decode()).encode(), "application/vnd.apple.mpegurl", "no-cache, no-store")
        return self.send(200, body, "video/mp4", "public, max-age=60, s-maxage=60")

if __name__ == "__main__":
    http.server.ThreadingHTTPServer.daemon_threads = True
    http.server.ThreadingHTTPServer(LISTEN, H).serve_forever()
