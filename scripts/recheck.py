"""Per-run source re-scan (Dean, 21 Oct 2026). Every run (3x daily) re-fetches the page each published entry relies on
(evidence_url for verified, sign_url for unverified) and re-extracts what we publish from it. Nothing is carried over:
if the page is unreachable, or no longer confirms the entry, the entry is not published this run (logged to pending
with the reason). Results per entry are stored in logs/<layer>_recheck.json: url, fetched_at, http status, extracted values."""
import re, html, json, ssl, datetime, hashlib, os, urllib.request, urllib.parse, concurrent.futures as cf
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (FindYourFoodBank verification; +https://github.com/)"}
def fetch(url):
    """HTTP GET with redirects followed; returns status, final URL, ETag/Last-Modified, sha256 of the text."""
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25, context=CTX)
        raw = r.read(2_000_000); t = raw.decode("utf8", "ignore"); code = r.status; final = r.geturl()
        etag = r.headers.get("ETag", ""); lm = r.headers.get("Last-Modified", "")
    except Exception as e:
        return {"http": getattr(e, "code", None) or "error", "error": str(e)[:120], "text": "", "final_url": url}
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)); t = re.sub(r"\s+", " ", t)
    return {"http": code, "text": t, "final_url": final, "etag": etag, "last_modified": lm,
            "sha256": hashlib.sha256(t.encode()).hexdigest()}
def fetch_js(url):
    """Headless Chrome fallback for pages that only render after a JavaScript challenge. None if Chrome is unavailable."""
    import shutil, subprocess
    exe = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not exe: return None
    try:
        raw = subprocess.run([exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=15000",
                              "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36", "--dump-dom", url],
                             capture_output=True, timeout=90).stdout.decode("utf8", "ignore")
    except Exception:
        return None
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)); t = re.sub(r"\s+", " ", t)
    if len(t) < 200: return None
    return {"http": 200, "text": t, "final_url": url, "etag": "", "last_modified": "", "sha256": hashlib.sha256(t.encode()).hexdigest(), "via": "headless-chrome"}
def host(u):
    h = urllib.parse.urlparse(u or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d - ([01]\d|2[0-3]):[0-5]\d$")
DAYKEYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
PC_RE = re.compile(r"^(GIR 0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})$")
def schema_errors(x, layer):
    """Validate every published field. Returns a list of problems (empty = valid)."""
    e = []
    if not x.get("name"): e.append("name missing")
    if not isinstance(x.get("lat"), (int, float)) or not 49.8 <= x["lat"] <= 61: e.append("lat out of UK range")
    if not isinstance(x.get("lng"), (int, float)) or not -8.7 <= x["lng"] <= 2: e.append("lng out of UK range")
    if x.get("postcode") and not PC_RE.match(str(x["postcode"]).upper()): e.append("postcode invalid")
    if not (x.get("address") or x.get("postcode")): e.append("address missing")
    h = x.get("hours")
    if isinstance(h, dict):
        for k, v in h.items():
            if k not in DAYKEYS: e.append(f"hours day key invalid: {k}")
            if str(v) == "24 hours": continue  # 24/7 from OSM, laid out per day by hours_norm
            for part in str(v).replace(" Monthly", "").replace(" Fortnightly", "").split(" / "):
                if not TIME_RE.match(part.strip()): e.append(f"hours value invalid: {k}={v}")
    elif h not in ("", None) and not isinstance(h, str): e.append("hours wrong type")
    if layer == "sh":
        if x.get("access_type") not in (None, "open_access", "self_referral", "referral_only"): e.append("access_type invalid")
        if x.get("access_type") == "referral_only":
            ref = (x.get("referral") or "").lower()
            if not any(w in ref for w in ("referral", "refer", "application", "agencies")):
                e.append("referral requirement not stated")
    if x.get("ended") not in (None, True, False): e.append("ended not boolean")
    if x.get("flag_closed"): e.append("flagged closed")
    return e

def published_hours(entry):
    h = entry.get("hours")
    if isinstance(h, dict): return bool(h)
    return bool(str(h or "").strip())

def norm_times(s):
    """'10.30am', '10:30', '10am' -> {'10:30','10:00'} in 24h (am/pm aware)."""
    out = set(); s = s.lower().replace("noon", "12pm").replace("midday", "12pm")
    for h, m, ap in re.findall(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", s):
        h = int(h); m = int(m or 0)
        if h > 24 or m > 59 or (not ap and not m and h < 7): continue
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        out.add(f"{h:02d}:{m:02d}")
    return out
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
def osm_only(entry):
    return str(entry.get("id", "")).startswith("osm-") or entry.get("source") == "OpenStreetMap"
def check(entry, ov, page, url=None, prev=None):
    """Run every check against the freshly fetched page; any failure -> ok False with the reason."""
    t = page["text"]; low = t.lower()
    res = {"http": page["http"], "final_url": page.get("final_url"), "etag": page.get("etag", ""),
           "last_modified": page.get("last_modified", ""), "sha256": page.get("sha256", "")}
    prev = prev or {}
    res["changed_since_last_run"] = bool(prev.get("sha256")) and prev.get("sha256") != res["sha256"]
    res["headers_changed"] = bool(prev) and (prev.get("etag"), prev.get("last_modified")) != (res["etag"], res["last_modified"])
    if page["http"] != 200:
        h = page["http"]
        return dict(res, ok=False, reason=("source did not return the page this run (HTTP %s; usually a bot check)" if isinstance(h, int) and 200 <= h < 300
                                           else "source unreachable this run (HTTP %s)") % h)
    if len(t) < 200:  # page loaded (HTTP 200) but held no readable text: bot challenge / JS-only page / empty body
        return dict(res, ok=False, reason="source page loaded (HTTP 200) but had no readable text this run (%d chars; likely a bot check or JavaScript-only page)" % len(t))
    if url and host(page.get("final_url")) != host(url):
        return dict(res, ok=False, reason="source URL now redirects to a different site (%s)" % host(page.get("final_url")))
    name_words = [w for w in re.findall(r"[a-z]{4,}", (ov.get("name") or entry.get("name", "")).lower()) if w not in ("church", "centre", "community", "house", "lodge", "space", "warm", "welcome", "hall", "salvation", "army")]
    res["name_found"] = (not name_words) or any(w in low for w in name_words)
    q = ov.get("day_time_quote") or ""
    want_t = norm_times(q); got_t = norm_times(t)
    res["times_quoted"] = sorted(want_t); res["times_found"] = sorted(want_t & got_t)
    want_d = [d for d in DAYS if d in q.lower() or d[:3] in q.lower().split()]
    res["days_found"] = [d for d in want_d if d in low or d[:3] + " " in low]
    pc = (ov.get("postcode") or entry.get("postcode") or "").upper().replace(" ", "")
    res["postcode_found"] = bool(pc) and pc in t.upper().replace(" ", "")
    res["closed_words"] = bool(re.search(r"(permanently closed|has closed|now closed|no longer (running|open|operating)|service (has )?ended)", low))
    acc = (ov.get("access") or entry.get("referral") or "").lower()
    res["referral_found"] = ("referral" in low or "refer" in low) if "referral" in acc else None
    if res["closed_words"]: return dict(res, ok=False, reason="source now says closed/ended")
    if not res["name_found"]: return dict(res, ok=False, reason="source no longer names this place")
    if published_hours(entry) and want_t and not (want_t & got_t): return dict(res, ok=False, reason="published times not found on source this run")
    if published_hours(entry) and want_d and not res["days_found"]: return dict(res, ok=False, reason="published days not found on source this run")
    if osm_only(entry):
        # '100% categorically' (Dean, 21 Oct 2026): an entry that came from OpenStreetMap is never published on OSM alone.
        # Its evidence page must be a real (non-OSM) page that shows THIS place's postcode or street address this run.
        street = re.sub(r"^\d+[a-z]?\s+", "", ((ov.get("address") or entry.get("address") or "").split(",")[0]).strip().lower())
        res["address_found"] = bool(street) and len(street) > 5 and street in low
        if host(url) in ("openstreetmap.org", "osm.org"):
            return dict(res, ok=False, reason="OpenStreetMap-only: no independent source page")
        if not (res["postcode_found"] or res["address_found"]):
            return dict(res, ok=False, reason="OpenStreetMap-only: own-site page does not show this place's postcode or street address this run")
    return dict(res, ok=True, reason="confirmed this run")
def recheck_all(fresh, verified, unverified, log_path, layer=None, fetcher=None):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    fetcher = fetcher or fetch
    layer = layer or ("sh" if "shelter" in log_path else "ws")
    prev = json.load(open(log_path)) if os.path.exists(log_path) else {}
    jobs = {}
    for x in fresh:
        ov = verified.get(x["id"]) or (unverified or {}).get(x["id"])
        if ov: jobs[x["id"]] = (x, ov, ov.get("evidence_url") if x["id"] in verified else ov.get("sign_url"))
    urls = sorted({u for i, (_, _, u) in jobs.items() if u and not ("warmwelcome.uk" in u and i not in verified)})
    with cf.ThreadPoolExecutor(16) as ex: pages = dict(zip(urls, ex.map(fetcher, urls)))
    for u in urls:  # one sequential retry for failed/short pages (rate limits, bot challenges) before omitting
        if pages[u].get("http") != 200 or len(pages[u].get("text", "")) < 200:
            pages[u] = fetcher(u)
        if fetcher is fetch and pages[u].get("http") == 200 and len(pages[u].get("text", "")) < 200:
            pages[u] = fetch_js(u) or pages[u]  # JS bot-challenge page (e.g. cambsacre.org.uk 'One moment, please'): real browser
    out = {}
    for i, (x, ov, u) in jobs.items():
        merged = dict(x); merged.update({k: ov[k] for k in ("address", "postcode", "lat", "lng", "hours", "access_type") if k in ov})
        if "access" in ov and not (x.get("referral") or "").strip():
            merged["referral"] = ov["access"]
        elif "access" in ov:
            merged["referral"] = x["referral"]
        if u and "warmwelcome.uk" in u and i not in verified:
            # Tier-2 warm space whose only sign of life is its Warm Welcome listing: the feed itself was re-downloaded
            # this run (the entry is in `fresh`), so the check is that it is still listed and not hidden/ended.
            r = {"ok": not x.get("ended"), "http": "feed", "final_url": u, "reason": "listed in this run's Warm Welcome feed" if not x.get("ended") else "feed says ended"}
        else:
            r = check(x, ov, pages.get(u, {"http": "no url", "text": ""}), u, prev.get(i)) if u else {"ok": False, "reason": "no source url"}
        errs = schema_errors(merged, layer); r["schema_errors"] = errs
        if r.get("ok") and errs: r.update(ok=False, reason="schema: " + "; ".join(errs[:3]))
        r.update(url=u, fetched_at=now); out[i] = r
    out["_run"] = {"fetched_at": now, "entries": len(jobs), "ok": sum(1 for k, v in out.items() if k != "_run" and v.get("ok")), "urls": len(urls)}
    json.dump(out, open(log_path, "w"), indent=1, ensure_ascii=False)
    return out
