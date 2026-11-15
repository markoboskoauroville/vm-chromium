#!/usr/bin/env python3
"""Cache Rules for live.santoshiband.org (15.11.2026): segments and parts (.mp4/.m4s) cached 60 s at the edge with the query string left out of
the cache key (MediaMTX puts ?session=<viewer> on every URI), errors never stored; playlists (.m3u8) bypass the cache (LL-HLS blocking
reloads must reach the relay). Token: the one inside ~/.cloudflared/cert.pem (from `cloudflared tunnel login`), or the file named by
CF_TOKEN_FILE (a token with Zone > Cache Rules > Edit for santoshiband.org). Nothing secret is printed. Safe to run again (replaces only
rules whose ref starts with santoshi-hls)."""
import base64, json, os, re, sys, urllib.request
HOST, ZONE = "live.santoshiband.org", "santoshiband.org"
def token():
    f = os.environ.get("CF_TOKEN_FILE")
    if f: return open(f).read().strip(), None
    pem = open(os.path.expanduser("~/.cloudflared/cert.pem")).read()
    m = re.search(r"-----BEGIN ARGO TUNNEL TOKEN-----(.+?)-----END ARGO TUNNEL TOKEN-----", pem, re.S)
    j = json.loads(base64.b64decode("".join(m.group(1).split())))
    return j["apiToken"], j.get("zoneID")
TOK, ZID = token()
def api(method, path, body=None):
    r = urllib.request.Request("https://api.cloudflare.com/client/v4" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"authorization": "Bearer " + TOK, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        try: return e.code, json.load(e)
        except Exception: return e.code, {}
if not ZID:
    st, j = api("GET", "/zones?name=" + ZONE)
    if st != 200 or not j.get("result"): sys.exit(f"zone lookup failed ({st}): {[e.get('message') for e in j.get('errors', [])]}")
    ZID = j["result"][0]["id"]
seg = f'(http.host eq "{HOST}" and (ends_with(http.request.uri.path, ".mp4") or ends_with(http.request.uri.path, ".m4s")))'
lst = f'(http.host eq "{HOST}" and ends_with(http.request.uri.path, ".m3u8"))'
mine = [
    {"ref": "santoshi-hls-segments", "description": "Santoshi HLS segments: 60 s, query ignored", "expression": seg, "action": "set_cache_settings",
     "action_parameters": {"cache": True, "edge_ttl": {"mode": "override_origin", "default": 60, "status_code_ttl": [{"status_code_range": {"from": 300, "to": 599}, "value": -1}]},
                           "browser_ttl": {"mode": "override_origin", "default": 60},
                           "cache_key": {"custom_key": {"query_string": {"exclude": {"all": True}}}}}},
    {"ref": "santoshi-hls-playlists", "description": "Santoshi HLS playlists: never cached", "expression": lst, "action": "set_cache_settings",
     "action_parameters": {"cache": False}},
]
phase = f"/zones/{ZID}/rulesets/phases/http_request_cache_settings/entrypoint"
st, j = api("GET", phase)
if st == 200: rules = [r for r in j["result"].get("rules", []) if not str(r.get("ref", "")).startswith("santoshi-hls")]
elif st == 404: rules = []
else: sys.exit(f"cannot read the cache rules ({st}): {[e.get('message') for e in j.get('errors', [])]} -> a token with Zone > Cache Rules > Edit is needed (CF_TOKEN_FILE)")
keep = [{k: r[k] for k in ("ref", "description", "expression", "action", "action_parameters", "enabled") if k in r} for r in rules]
st, j = api("PUT", phase, {"rules": keep + mine})
if st != 200: sys.exit(f"cache rules not written ({st}): {[e.get('message') for e in j.get('errors', [])]}")
print("cache rules set:", [r.get("ref") for r in j["result"]["rules"]])
