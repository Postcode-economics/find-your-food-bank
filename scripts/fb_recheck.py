"""Food bank recheck gate (Dean, 21 Oct 2026): food banks get the same per-run over-check as shelters and warm spaces.
Every 3x-daily run, inside scripts/build.py:
 1. Source fetch: each Give Food API endpoint is fetched fresh. HTTP status, final URL (must still be givefood.org.uk),
    ETag, Last-Modified and the sha256 of the response are stored and compared with the last run. Any failure stops the
    whole run (fail safe: data.js is not replaced).
 2. Per entry: sha256 of the exact source record + fetched_at are stored and compared with the last run
    (changed_since_last_run). IFAN-discovered entries carry their own-site fetch (HTTP 200, same site, sha256).
 3. Source URL: the entry's Give Food page must be on givefood.org.uk and be the page for THIS record (slug match).
    A rotating sample of pages is fetched live each run (all pages covered every few days); a page that loads but
    does not name the food bank -> entry left off; a page that does not load -> flagged in the log.
 4. Schema: every published field is validated (id, type, names, UK lat/lng, postcode format, address, phone digits,
    website/givefood URLs, opening_times shape in Mon-Sun order with HH:MM ranges, labels). Failures -> left off.
Omitted entries go to logs/foodbank_pending.json with the reason; everything is logged in logs/foodbank_recheck.json.
scripts/verify_fresh.py foodbanks refuses to publish unless every published entry matches this run's log."""
import re, json, os, hashlib, datetime, urllib.request, urllib.parse, ssl
CTX = ssl.create_default_context()
UA = {"User-Agent": "foodbank-map-refresh (github actions; recheck)"}
PC_RE = re.compile(r"^(GIR 0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})$")
HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LABELS_EN = {"Donations only"}; LABELS_CY = {"Rhoddion yn unig"}
def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
def sha(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def host(u):
    h = urllib.parse.urlparse(u or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h
def fetch_api(url, data=None, tries=3):
    """-> (parsed_json, meta). meta holds http, final_url, etag, last_modified, sha256, fetched_at."""
    err = None
    for _ in range(tries):
        try:
            h = dict(UA)
            if data is not None: h["Content-Type"] = "application/json"
            r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=90)
            raw = r.read()
            meta = {"url": url, "http": r.status, "final_url": r.geturl(), "etag": r.headers.get("ETag", ""),
                    "last_modified": r.headers.get("Last-Modified", ""), "sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": now()}
            return json.loads(raw), meta
        except Exception as e: err = e
    raise err
def api_errors(meta, prev=None):
    e = []
    if meta.get("http") != 200: e.append("HTTP %s" % meta.get("http"))
    if host(meta.get("final_url")) != "givefood.org.uk": e.append("API redirected to %s" % host(meta.get("final_url")))
    prev = prev or {}
    meta["changed_since_last_run"] = bool(prev.get("sha256")) and prev["sha256"] != meta["sha256"]
    meta["headers_changed"] = bool(prev) and (prev.get("etag"), prev.get("last_modified")) != (meta["etag"], meta["last_modified"])
    return e
def url_ok(u): return isinstance(u, str) and (u == "" or re.match(r"^https?://[^\s/]+\.[^\s]+$", u) is not None)
def schema_errors(i):
    e = []
    if not isinstance(i.get("id"), str) or not i["id"].strip(): e.append("id missing")
    if i.get("type") not in ("foodbank", "location"): e.append("type invalid")
    for k in ("name", "foodbank"):
        if not isinstance(i.get(k), str) or not i[k].strip(): e.append(f"{k} missing")
    if not isinstance(i.get("lat"), (int, float)) or not 49.0 <= i["lat"] <= 61: e.append("lat out of UK range")  # 49.0: Jersey/Guernsey/Alderney are on the map
    if not isinstance(i.get("lng"), (int, float)) or not -8.7 <= i["lng"] <= 2: e.append("lng out of UK range")
    pc = i.get("postcode") or ""
    if pc and not PC_RE.match(pc.upper()): e.append("postcode invalid")
    ph = i.get("phone") or ""
    if not isinstance(ph, str) or (ph and len(re.sub(r"\D", "", ph)) < 10): e.append("phone has fewer than 10 digits")
    if not url_ok(i.get("website", "")): e.append("website not a URL")
    g = i.get("givefood", "")
    if g and host(g) != "givefood.org.uk": e.append("givefood URL not on givefood.org.uk")
    ot = i.get("opening_times")
    if ot is not None:
        if not isinstance(ot, dict) or ot.get("status") not in ("TIMES_FOUND", "TIMES_TEXT_ONLY"): e.append("opening_times status invalid")
        else:
            s = ot.get("structured")
            if ot["status"] == "TIMES_FOUND":
                if not isinstance(s, dict) or not s: e.append("opening_times structured missing")
                else:
                    if any(k not in DAYS for k in s): e.append("opening_times day key invalid")
                    elif list(s) != [d for d in DAYS if d in s]: e.append("opening_times not in Mon-Sun order")
                    for d, rs in s.items():
                        for r in rs if isinstance(rs, list) else [None]:
                            if not (isinstance(r, list) and len(r) == 2 and all(isinstance(t, str) and HM.match(t) for t in r)):
                                e.append(f"opening_times {d} range invalid"); break
            elif not (ot.get("lines") or ot.get("raw")): e.append("opening_times text missing")
    if "label_en" in i and i["label_en"] not in LABELS_EN and not i.get("locked"): e.append("label_en not an approved label")
    if "label_cy" in i and i["label_cy"] not in LABELS_CY and not i.get("locked"): e.append("label_cy not an approved label")
    for k in ("moved_to_postcode", "pc_checked", "phone_checked", "locked"):
        if k in i and not isinstance(i[k], bool): e.append(f"{k} not boolean")
    return e
def gf_path_ok(i):
    """The Give Food page must be the page for THIS record: /needs/at/<foodbank-slug>/[<location-slug>/]."""
    g = i.get("givefood") or ""
    if i.get("manual"): return url_ok(i.get("evidence_url") or "") and bool(i.get("evidence_url"))  # own-site checked extra location
    if not g: return i.get("directory") == "IFAN"  # IFAN finds have no Give Food page; their own site is the source
    if host(g) != "givefood.org.uk": return False
    path = urllib.parse.urlparse(g).path.strip("/").split("/")
    want = i["id"].split("/")
    return all(w in path for w in want)
def live_fetch(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25, context=CTX)
        t = r.read(1_500_000).decode("utf8", "ignore")
        return {"http": r.status, "final_url": r.geturl(), "text": t, "sha256": hashlib.sha256(t.encode()).hexdigest()}
    except Exception as e:
        return {"http": getattr(e, "code", None) or "error", "final_url": u, "text": ""}
def sample(items, run_key, per_run):
    """Rotating sample: hash(id + run slot) so a different slice of pages is fetched each run."""
    cand = [i for i in items if i.get("givefood") and not i.get("manual")]
    cand.sort(key=lambda i: hashlib.md5((i["id"] + run_key).encode()).hexdigest())
    return {i["id"] for i in cand[:per_run]}
def gate(items, records, api_meta, log_path, pending_path, fetcher=None, per_run=None, run_key=None):
    """items: built entries; records: {id: source record dict}; api_meta: {endpoint: meta}. Returns (published, omitted)."""
    fetcher = fetcher or live_fetch
    per_run = int(os.environ.get("FB_LIVE_SAMPLE", "120")) if per_run is None else per_run
    t = now(); run_key = run_key or t[:13]
    prev = json.load(open(log_path)) if os.path.exists(log_path) else {}
    errs = {}
    for ep, m in api_meta.items():
        e = api_errors(m, (prev.get("_run") or {}).get("api", {}).get(ep))
        if e: errs[ep] = e
    if errs: raise RuntimeError("source API failed the recheck: %r" % errs)
    live_ids = sample(items, run_key, per_run)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(12) as ex:
        live = dict(zip(sorted(live_ids), ex.map(lambda k: fetcher(next(i["givefood"] for i in items if i["id"] == k)), sorted(live_ids))))
    out, pub, omitted, seen = {}, [], [], set()
    for i in items:
        rec = records.get(i["id"])
        r = {"source_url": (i.get("manual") and i.get("evidence_url")) or i.get("givefood") or (i.get("own_site_check") or {}).get("final_url") or i.get("website"),
             "fetched_at": (i.get("own_site_check") and t) or t, "record_sha256": sha(rec) if rec is not None else None}
        p = prev.get(i["id"]) or {}
        r["changed_since_last_run"] = bool(p.get("record_sha256")) and p["record_sha256"] != r["record_sha256"]
        r["new_since_last_run"] = bool(prev) and not p
        r["schema_errors"] = schema_errors(i)
        if i["id"] in seen: r["schema_errors"].append("duplicate id")
        seen.add(i["id"])
        reason = None; flagged = []
        if not (i.get("address") or i.get("postcode")): flagged.append("no address or postcode in source (Give Food area/ward location); pin kept, needs review")
        if rec is None: reason = "no source record this run"
        elif r["schema_errors"]: reason = "schema: " + "; ".join(r["schema_errors"][:3])
        elif not gf_path_ok(i): reason = "source URL is not the Give Food page for this record"
        elif i.get("directory") == "IFAN":
            ev = i.get("own_site_check") or {}
            r.update({k: ev.get(k) for k in ("http", "final_url", "sha256", "etag", "last_modified")})
            if ev.get("http") != 200: reason = "own-site source did not load (HTTP %s)" % ev.get("http")
        if not reason and i["id"] in live:
            L = live[i["id"]]; r["live"] = {"http": L["http"], "final_url": L["final_url"], "sha256": L.get("sha256")}
            if L["http"] == 200 and host(L["final_url"]) == "givefood.org.uk":
                words = [w for w in re.findall(r"[a-z]{4,}", i["foodbank"].lower()) if w not in ("food", "bank", "foodbank")]
                low = L["text"].lower()
                if words and not any(w in low for w in words): reason = "Give Food page no longer names this food bank"
            else: flagged.append("Give Food page did not load this run (HTTP %s)" % L["http"])
        r["ok"] = reason is None; r["reason"] = reason or "confirmed this run"; r["flags"] = flagged
        out[i["id"]] = r
        if reason: omitted.append({"id": i["id"], "name": i["name"], "postcode": i.get("postcode", ""), "reason": "omitted this run: " + reason,
                                   "recheck": {k: r.get(k) for k in ("source_url", "fetched_at", "record_sha256", "schema_errors")}})
        else:
            i["fetched_at"] = t; pub.append(i)
    out["_run"] = {"fetched_at": t, "entries": len(items), "published": len(pub), "omitted": len(omitted),
                   "flagged": sum(1 for v in out.values() if isinstance(v, dict) and v.get("flags")),
                   "live_checked": len(live), "api": api_meta}
    json.dump(out, open(log_path, "w"), indent=0, ensure_ascii=False)
    json.dump(omitted, open(pending_path, "w"), indent=1, ensure_ascii=False)
    return pub, omitted
