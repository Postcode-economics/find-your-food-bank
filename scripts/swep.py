"""SWEP (Severe Weather Emergency Protocol) watcher. Runs with the shelters refresh.
* Source list: overrides/swep_sources.json ({"council", "url"}), kept up to date by discover() during the
  overnight sweep: each council site in scripts/sweep_sources.json is scanned (homepage + known pages, 1-2
  requests per council, polite) for links about SWEP / severe weather / rough sleeping.
* Every run: fetch each SWEP page and classify it from the council's own wording: active / not active / unknown.
  Writes logs/swep_status.json and lists changes (activated / deactivated) for Dean's daily review.
Nothing here changes the map: SWEP is reached through outreach/StreetLink, not a walk-in address, so it is
flagged for review, never auto-pinned."""
import json, os, re, sys, datetime, concurrent.futures as cf, urllib.parse, time
sys.path.insert(0, os.path.dirname(__file__))
SRC, LOG = "overrides/swep_sources.json", "logs/swep_status.json"
KW = re.compile(r"\bSWEP\b|severe weather emergency|severe weather protocol|cold weather (shelter|provision|protocol)", re.I)
ON = re.compile(r"(SWEP|severe weather emergency protocol|severe weather protocol|cold weather provision)[^.]{0,80}?\b(is (now |currently )?(active|activated|in place|in operation|open|running)|has been (activated|triggered|implemented)|(will be|has been) put in place)(?! (when|if|during|whenever))", re.I)
OFF = re.compile(r"(SWEP|severe weather emergency protocol|severe weather protocol)[^.]{0,80}?\b(is (not|no longer) (active|in place|in operation)|has been (de-?activated|stood down|lifted|ended)|is currently inactive|stood down)", re.I)
LINK = re.compile(r'href="([^"#]+)"[^>]*>([^<]{0,140})<', re.I)
LINKWORDS = re.compile(r"swep|severe[- ]weather|rough[- ]sleep|cold[- ]weather|winter[- ]shelter|night[- ]shelter", re.I)
def classify(text, run_day=None):
    """Return (status, quote). The LATEST-mentioned state on the page wins when both appear."""
    t = re.sub(r"\s+", " ", text or "")
    if not KW.search(t): return "no SWEP wording", ""
    on = list(ON.finditer(t)); off = list(OFF.finditer(t))
    if not on and not off: return "unknown", ""
    last_on = on[0] if on else None; last_off = off[0] if off else None  # first mention = page headline / latest news
    if last_on and (not last_off or last_on.start() < last_off.start()): m, st = last_on, "active"
    else: m, st = last_off, "not active"
    q = t[max(0, m.start() - 60): m.end() + 80]
    if st == "active" and run_day:
        import seasonal
        ds = [d for d in seasonal._all(t) if d.isoformat() <= run_day]
        if ds and (datetime.date.fromisoformat(run_day) - max(ds)).days > 10:
            return "old notice (latest date on page %s)" % max(ds).isoformat(), q
    return st, q
def _fetch(u):
    from discover import fetch_raw
    return fetch_raw(u)
def run(fetcher=None, run_day=None, threads=8):
    fetcher = fetcher or _fetch; run_day = run_day or datetime.date.today().isoformat()
    srcs = json.load(open(SRC)) if os.path.exists(SRC) else []
    prev = {x["url"]: x for x in (json.load(open(LOG)).get("pages", []) if os.path.exists(LOG) else [])}
    def one(s):
        r = fetcher(s["url"]); h = r.get("html") or r.get("text") or ""
        txt = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", h))
        st, q = classify(txt, run_day) if r.get("http") == 200 else ("unreachable", "")
        return {"council": s["council"], "url": s["url"], "http": r.get("http"), "status": st, "quote": q,
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    with cf.ThreadPoolExecutor(threads) as ex: pages = list(ex.map(one, srcs))
    changes = []
    for p in pages:
        o = prev.get(p["url"])
        if o and o["status"] != p["status"] and "active" in (o["status"], p["status"]) or (not o and p["status"] == "active"):
            changes.append({"council": p["council"], "url": p["url"], "from": (o or {}).get("status", "new"), "to": p["status"], "quote": p["quote"]})
    out = {"run": run_day, "sources": len(srcs), "active": [p["council"] for p in pages if p["status"] == "active"], "changes": changes, "pages": pages}
    json.dump(out, open(LOG, "w"), indent=1, ensure_ascii=False)
    return out
def discover(fetcher=None, councils_path="scripts/sweep_sources.json", budget_s=1500):
    """Overnight: scan council sites for SWEP / rough sleeping pages. Adds new URLs to overrides/swep_sources.json."""
    fetcher = fetcher or _fetch
    cs = json.load(open(councils_path))["councils"]
    have = json.load(open(SRC)) if os.path.exists(SRC) else []
    seen = {x["url"] for x in have}; t0 = time.time()
    def one(c):
        found = []
        for u in [c["site"]] + [u for u in c.get("known_pages", [])[:1]]:
            r = fetcher(u)
            if r.get("http") != 200: continue
            for href, txt in LINK.findall(r.get("html") or ""):
                if LINKWORDS.search(href + " " + txt):
                    full = urllib.parse.urljoin(u, href)
                    if urllib.parse.urlparse(full).netloc.split(":")[0].endswith(urllib.parse.urlparse(c["site"]).netloc.replace("www.", "")):
                        found.append({"council": c["name"], "url": full, "found_on": u})
        return found
    added = []
    with cf.ThreadPoolExecutor(6) as ex:
        for f in ex.map(one, cs):
            for x in f:
                if x["url"] not in seen: seen.add(x["url"]); have.append(x); added.append(x)
            if time.time() - t0 > budget_s: break
    json.dump(have, open(SRC, "w"), indent=1, ensure_ascii=False)
    return {"councils": len(cs), "sources": len(have), "added": len(added)}
if __name__ == "__main__":
    if sys.argv[1:] == ["discover"]: print(discover())
    else: r = run(); print(r["sources"], "SWEP pages;", len(r["active"]), "active;", len(r["changes"]), "changes")
