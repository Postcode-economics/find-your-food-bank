import json, os, re, time, urllib.request, datetime
UA = {"User-Agent": "postcode-economics-map/1.0 (+https://postcode-economics.github.io/find-your-food-bank/)"}
PC_RE = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b", re.I)
def today(): return datetime.date.today().isoformat()
def get(url, data=None, tries=3, timeout=90):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
        except Exception as e:
            err = e; time.sleep(5 * (k + 1))
    raise err
def postcode(s):
    m = PC_RE.search(s or "")
    return (m.group(1) + " " + m.group(2)).upper() if m else ""
def reverse_postcodes(points):
    """points: list of (key, lat, lng) -> {key: postcode} via postcodes.io bulk reverse (free)."""
    out = {}
    for i in range(0, len(points), 100):
        chunk = points[i:i+100]
        body = json.dumps({"geolocations": [{"latitude": la, "longitude": ln, "limit": 1, "radius": 500} for _, la, ln in chunk]}).encode()
        try:
            req = urllib.request.Request("https://api.postcodes.io/postcodes", data=body, headers={**UA, "Content-Type": "application/json"})
            res = json.load(urllib.request.urlopen(req, timeout=60))["result"]
            for (k, _, _), r in zip(chunk, res):
                if r["result"]: out[k] = r["result"][0]["postcode"]
        except Exception: pass
    return out
def load_js(path, var):
    if not os.path.exists(path): return None
    t = open(path, encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))
def write_js(path, var, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"var {var}=" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n")
def merge_lifecycle(prev, fresh, run_day, stale_days=7, close_after=14, keep_closed=30):
    """Keep previous entries missing from today's scan (last_verified unchanged), flag stale >7d,
    move to recently_closed after `close_after` days unseen or when flagged closed; purge closed after 30d."""
    d = lambda s: datetime.date.fromisoformat(s)
    rd = d(run_day)
    items = {x["id"]: x for x in fresh}
    closed = {x["id"]: x for x in (prev or {}).get("recently_closed", [])}
    for x in (prev or {}).get("items", []):
        if x["id"] in items: continue
        unseen = (rd - d(x["last_verified"])).days
        if unseen > close_after:
            x["closed_on"] = run_day; x["closed_reason"] = f"No longer listed by source (unseen {unseen} days)"; closed[x["id"]] = x
        else: items[x["id"]] = x
    for k, x in list(items.items()):
        if x.get("flag_closed"):
            x.setdefault("closed_on", run_day); closed[k] = items.pop(k)
    for k in list(closed):
        if k in items and not items[k].get("flag_closed"): closed.pop(k)  # re-listed
        elif (rd - d(closed[k]["closed_on"])).days > keep_closed: closed.pop(k)
    for x in items.values():
        x["stale"] = (rd - d(x["last_verified"])).days > stale_days
    return sorted(items.values(), key=lambda x: x["name"].lower()), sorted(closed.values(), key=lambda x: x["closed_on"], reverse=True)
def append_log(path, entry):
    log = json.load(open(path)) if os.path.exists(path) else []
    log.insert(0, entry); json.dump(log[:120], open(path, "w"), indent=1)
