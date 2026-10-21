"""Discovery + own-site cross-check, shared by all three layers (Dean, 21 Oct 2026).
Every 3x-daily run:
 1. Pull each major directory in full (food banks: Give Food + IFAN; shelters: OSM + Homeless Link 'Find help';
    warm spaces: Warm Welcome + Open Innovations aggregator of council/VCS directories).
 2. dedupe(): anything not already on the map (postcode, distance, name) is a candidate.
 3. own_site_check(): the candidate's OWN website is fetched this run (HTTP 200, same site after redirects,
    sha256/ETag/Last-Modified recorded). It passes only if the site names it, shows its postcode, shows it is
    food aid / shelter / warm space, and does not say it has closed. Pass -> added; anything else -> flagged in logs.
 4. cross_check_times(): for every entry found or refreshed, the published times are re-confirmed on its own
    website THIS run. Confirmed -> kept; different times found -> replaced (via times.normalise); site says closed
    -> closure removal; unreachable / not confirmable -> times dropped and flagged (never carried over).
Never invents data: everything published comes from a fetched page or a directory record."""
import re, os, json, html, ssl, math, hashlib, datetime, threading, urllib.request, urllib.parse, concurrent.futures as cf
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "Mozilla/5.0 (FindYourFoodBank refresh; own-site check)"}
PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s?(\d[A-Z]{2})\b")
STOP = {"food", "bank", "foodbank", "the", "and", "of", "community", "church", "centre", "center", "trust", "project", "st", "uk",
        "network", "hub", "pantry", "larder", "cic", "ltd", "charity", "group", "warm", "space", "spaces", "welcome", "hall", "house",
        "night", "shelter", "winter", "ltd.", "limited", "association", "services", "service", "support", "at", "in", "for"}
FOOD_WORDS = re.compile(r"food ?bank|food parcel|food aid|emergency food|food pantry|community pantry|community larder|food share|foodshare|social supermarket|food hub", re.I)
SHELTER_WORDS = re.compile(r"night ?shelter|winter shelter|emergency accommodation|emergency bed|direct access|hostel|rough sleep|homeless", re.I)
WARM_WORDS = re.compile(r"warm (space|hub|welcome|room|bank|place)|warm and welcoming|cost of living|keep warm", re.I)
CLOSED = re.compile(r"(permanently closed|closed permanently|closed down|has (?:now )?closed|is now closed|no longer (?:operating|open|running|operational)|ceased (?:operating|trading)|service (?:has )?ended)", re.I)

def norm_pc(p): return (p or "").upper().replace(" ", "")
def find_pcs(text): return {a + b for a, b in PC_RE.findall((text or "").upper())}
def hav(a, b, c, d):
    p = math.radians; x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(x))
def tokens(n): return {w for w in re.findall(r"[a-z0-9]+", (n or "").lower().replace("&", " and ")) if w not in STOP and len(w) > 2}
def host(u):
    h = urllib.parse.urlparse(u or "").netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h

def is_dup(c, existing):
    """True if candidate c is already on the map: same postcode + shared name word, within 300 m + shared name word,
    within 50 m regardless of name, or same website host within 2 km."""
    pc, ct, ch = norm_pc(c.get("postcode")), tokens(c.get("name")), host(c.get("website"))
    for e in existing:
        same_name = bool(ct & tokens(e.get("name")) or ct & tokens(e.get("foodbank")))
        if pc and pc == norm_pc(e.get("postcode")) and (same_name or not ct): return True
        if c.get("lat") is None or e.get("lat") is None: continue
        d = hav(c["lat"], c["lng"], e["lat"], e["lng"])
        if d < 0.05 or (d < 0.3 and same_name): return True
        if ch and ch == host(e.get("website")) and d < 2 and ch not in ("facebook.com", "linktr.ee", "salvationarmy.org.uk"): return True
    return False
def dedupe(cands, existing):
    new, dup = [], 0; seen = []
    for c in cands:
        if is_dup(c, existing) or is_dup(c, seen): dup += 1; continue
        seen.append(c); new.append(c)
    return new, dup

# ---------- fetching (cached per run, so closure / times / discovery share one fetch per page) ----------
_cache, _lock = {}, threading.Lock()
def fetch_raw(url):
    with _lock:
        if url in _cache: return _cache[url]
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20, context=CTX)
        raw = r.read(8_000_000).decode("utf8", "ignore")
        res = {"http": r.status, "final_url": r.geturl(), "html": raw, "etag": r.headers.get("ETag", ""),
               "last_modified": r.headers.get("Last-Modified", ""), "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    except Exception as e:
        res = {"http": getattr(e, "code", None) or "error", "final_url": url, "html": "", "error": str(e)[:120]}
    with _lock: _cache[url] = res
    return res
def closure_fetcher(u):  # signature closure.py expects: (final_url, html)
    r = fetch_raw(u); return r["final_url"], (r["html"] if r["http"] == 200 else "")
def text_of(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
LINK = re.compile(r"locat|contact|find|get-?help|visit|open|centre|where|need|time|hour|about", re.I)
def site_pages(url, fetcher=fetch_raw, maxpages=4):
    """Home page + up to `maxpages` same-site location/contact/times pages. Returns (home_result, [(url, text)])."""
    home = fetcher(url)
    if home["http"] != 200 or not home["html"]: return home, []
    pages = [(home["final_url"], text_of(home["html"]))]; links = []
    for m in re.findall(r'href="([^"#]+)"', home["html"]):
        u = urllib.parse.urljoin(home["final_url"], m)
        if LINK.search(m) and host(u) == host(home["final_url"]) and u not in links and u != home["final_url"]: links.append(u)
    for u in links[:maxpages]:
        r = fetcher(u)
        if r["http"] == 200 and r["html"]: pages.append((r["final_url"], text_of(r["html"])))
    return home, pages

def usable_site(u):
    return bool(u) and u.startswith("http") and not any(x in u for x in ("facebook.com", "instagram.com", "twitter.com", "x.com/", "linktr.ee"))

def own_site_check(c, kind, fetcher=fetch_raw, today=None):
    """kind: 'fb' | 'sh' | 'ws'. Returns dict(result='add'|'flag', reasons=[...], evidence)."""
    words = {"fb": FOOD_WORDS, "sh": SHELTER_WORDS, "ws": WARM_WORDS}[kind]
    out = {"result": "flag", "reasons": [], "url": c.get("website", "")}
    if not usable_site(c.get("website")): out["reasons"].append("no own website in directory"); return out
    home, pages = site_pages(c["website"], fetcher)
    out.update({k: home.get(k) for k in ("http", "final_url", "etag", "last_modified", "sha256")})
    if home["http"] != 200: out["reasons"].append(f"own site unreachable (HTTP {home['http']})"); return out
    if host(home["final_url"]) != host(c["website"]) and not host(home["final_url"]).endswith("." + host(c["website"])) \
            and not host(c["website"]).endswith("." + host(home["final_url"])):
        out["reasons"].append(f"own site redirects to a different site ({host(home['final_url'])})"); return out
    alltext = " ".join(t for _, t in pages)
    if len(alltext) < 200: out["reasons"].append("own site has no readable text"); return out
    low = alltext.lower(); pc = norm_pc(c.get("postcode"))
    nt = tokens(c.get("name"))
    if nt and not any(w in low for w in nt): out["reasons"].append("own site does not name it")
    if not pc: out["reasons"].append("no postcode in directory")
    elif pc not in alltext.upper().replace(" ", ""): out["reasons"].append("postcode not on own site")
    if not words.search(alltext): out["reasons"].append({"fb": "own site does not show food aid", "sh": "own site does not show it is a shelter/emergency accommodation", "ws": "own site does not mention a warm space"}[kind])
    m = CLOSED.search(alltext)
    if m: out["reasons"].append("own site says closed: " + alltext[max(0, m.start() - 60):m.end() + 60])
    if kind == "sh" and re.search(r"referral (only|required|needed)|by referral|must be referred|referred by", low): out["referral_only"] = True
    out["pages"] = [u for u, _ in pages]
    if not out["reasons"]: out["result"] = "add"
    out["_text"] = alltext
    return out

# ---------- times cross-check ----------
DAYN = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TIMESPAN = re.compile(r"((?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?(?:\s*(?:,|&|and|-|–|to)\s*)?)+)[\s:,(]*((?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon|midday)\s*(?:-|–|—|to|until|till)\s*(?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon|midday))", re.I)
def norm_times(s):
    from recheck import norm_times as nt
    return nt(s or "")
def want_times(ot):
    """Times + days we publish for an entry (food bank opening_times dict, or shelter/warm-space hours)."""
    if not ot: return set(), set()
    if isinstance(ot, dict) and "status" in ot:
        if ot.get("structured"):
            return {t for r in ot["structured"].values() for rng in r for t in rng}, set(ot["structured"])
        return norm_times(ot.get("raw") or " ".join(ot.get("lines") or [])), {d for d in DAYN if d in (ot.get("raw") or "").lower()}
    if isinstance(ot, dict):
        return norm_times(" ".join(map(str, ot.values()))), {k[:3].lower() for k in ot}
    return norm_times(str(ot)), {d for d in DAYN if d in str(ot).lower()}
NOT_CLIENT = re.compile(r"office|warehouse|donat|drop[- ]?off|admin|phone line|telephone|helpline|call us|volunteer", re.I)
def extract_times(text, postcode=None):
    """Pull 'day(s) time-time' phrases from own-site text; if the site lists several postcodes, only this entry's block."""
    t = text or ""; pc = norm_pc(postcode)
    if pc and pc not in t.upper().replace(" ", ""): return None   # never take times from a page that doesn't show this place
    pcs = list(PC_RE.finditer(t.upper()))
    if pc and len({a + b for a, b in (m.groups() for m in pcs)}) > 1:
        hit = [m for m in pcs if m.group(1) + m.group(2) == pc]
        if not hit: return None
        s = hit[0].start(); t = t[max(0, s - 500):s + 500]
    segs, seen = [], set()
    for m in TIMESPAN.finditer(t):
        if NOT_CLIENT.search(t[max(0, m.start() - 80):m.start()]): continue   # office / warehouse / donation hours are not client times
        seg = (m.group(1).strip(" ,&-–") + " " + m.group(2)).strip()
        if seg.lower() not in seen: seen.add(seg.lower()); segs.append(seg)
    if not segs: return None
    from times import normalise
    return normalise({"raw": " | ".join(segs), "status": "TIMES_TEXT_ONLY", "structured": None})
def confirm_times(ot, texts, postcode=None):
    """-> (status, new_ot, reason). status: confirmed | changed | unconfirmed | none_published."""
    alltext = " ".join(texts); low = alltext.lower()
    want, days = want_times(ot)
    if not want:
        new = extract_times(alltext, postcode)
        return ("changed", new, "times found on own site") if new and new.get("status") == "TIMES_FOUND" else ("none_published", None, "no times published or found")
    got = norm_times(alltext)
    days_ok = all(re.search(r"\b" + d, low) for d in days)
    if want <= got and days_ok: return "confirmed", ot, "all published days/times found on own site this run"
    new = extract_times(alltext, postcode)
    if new and new.get("status") == "TIMES_FOUND":
        nw, _ = want_times(new)
        if nw != want: return "changed", new, "own site now shows different times"
    return "unconfirmed", None, "published times not found on own site this run"
def hours_from_ot(ot):
    """times.normalise structured table -> shelter/warm-space hours dict {'Mon': '10:00 - 14:00 / 18:00 - 20:00'}."""
    if not ot or not ot.get("structured"): return None
    return {d.title(): " / ".join(f"{a} - {b}" for a, b in r) for d, r in ot["structured"].items()}

# Dean's standing default (21 Oct 2026): the place's OWN website is the main source. Where it gives times or says closed,
# it overrides Give Food and every directory. Directory times are only a fallback, kept but marked unconfirmed.
UNCONF_NOTE_UNUSED = {"fb": "Times from Give Food – not confirmed on the food bank's own site, call ahead",
               "sh": "Times from the directory listing – not confirmed on the shelter's own site, call before you go",
               "ws": "Times from the directory listing – not confirmed on the warm space's own site, call before you go"}
def _unconfirm(i, kind, field, reason):
    """Own site could not confirm: keep the main database's times (Give Food / listing directory) and show them normally
    (Dean, 21 Oct 17:31). Source/confirmation is logged internally only (times_source / times_status), never displayed."""
    i["times_status"] = "unconfirmed"; i["times_reason"] = reason
    i["times_source"] = "main database" if i.get(field) else ""
    i.pop("times_note", None)
def office_like(st):
    """Changed times that look like office/warehouse/centre hours: same block on 4+ weekdays lasting 4h+."""
    if not st: return False
    wk = [tuple(map(tuple, st.get(d, []))) for d in ("mon", "tue", "wed", "thu", "fri") if st.get(d)]
    if len(wk) < 4 or len(set(wk)) > 2: return False
    def mins(t): h, m = t.split(":"); return int(h) * 60 + int(m)
    return all(mins(b) - mins(a) >= 240 for blk in wk for a, b in blk)
def cross_check_times(items, kind, field, fetcher=fetch_raw, today=None, threads=24):
    """Re-confirm every entry's times on its OWN website this run; mutates items. Returns {id: result} log.
    kind 'fb': field 'opening_times' (times.py dict). kind 'sh'/'ws': field 'hours' (dict or text)."""
    import closure
    today = (today or datetime.date.today()).isoformat()
    sites = {}
    for i in items:
        s = (i.get("website") or "").strip()
        sites.setdefault(s if usable_site(s) else "", []).append(i)
    def one(s):
        if not s: return s, None, []
        home, pages = site_pages(s, fetcher)
        return s, home, pages
    with cf.ThreadPoolExecutor(threads) as ex: got = list(ex.map(one, list(sites)))
    log = {}
    for s, home, pages in got:
        for i in sites[s]:
            texts = [t for _, t in pages]
            src = (i.get(field) or {}).get("source_url") if isinstance(i.get(field), dict) else None
            if src and usable_site(src) and src not in [u for u, _ in pages]:
                r = fetcher(src)
                if r["http"] == 200: texts.append(text_of(r["html"]))
            rec = {"site": s, "http": home and home.get("http"), "sha256": home and home.get("sha256"),
                   "etag": home and home.get("etag"), "last_modified": home and home.get("last_modified"), "checked": today}
            if not s or not home or home.get("http") != 200 or not texts:
                rec.update(status="unreachable" if s else "no_website", reason="own site unreachable this run" if s else "no own website to check against")
                _unconfirm(i, kind, field, rec["reason"]); log[i["id"]] = rec; continue
            if host(home["final_url"]) != host(s) and not host(home["final_url"]).endswith("." + host(s)) and not host(s).endswith("." + host(home["final_url"])):
                rec.update(status="unconfirmed", reason="own site redirects to a different site")
                _unconfirm(i, kind, field, rec["reason"]); log[i["id"]] = rec; continue
            ev = None
            for t in texts:
                ev = closure.detect(t, i.get("postcode"))
                if ev: break
            if ev: rec.update(status="closed", reason="own site says closed", evidence=ev); i["_own_site_closed"] = ev; log[i["id"]] = rec; continue
            i["_orig_times"] = i.get(field)
            st, new, why = confirm_times(i.get(field) if kind == "fb" else i.get(field), texts, i.get("postcode"))
            rec.update(status=st, reason=why)
            if st == "confirmed": i["times_status"] = "confirmed"; i["times_checked"] = today
            elif st == "changed":
                if kind == "fb": new = dict(new, checked_date=today, source_url=home["final_url"]); i[field] = new
                else: i[field] = hours_from_ot(new) or i.get(field)
                i["times_status"] = "updated"; i["times_checked"] = today; rec["new"] = new.get("structured") if new else None
            elif st == "unconfirmed":
                _unconfirm(i, kind, field, why)
            log[i["id"]] = rec
    if kind == "fb":
        orig = {i["id"]: i.get("_orig_times") for i in items}
        bysite = {}
        for i in items:
            if log.get(i["id"], {}).get("status") == "changed": bysite.setdefault((log[i["id"]]["site"], json.dumps(log[i["id"]].get("new"), sort_keys=True)), []).append(i)
        for (site, _), grp in bysite.items():
            for i in grp:
                why = None
                if office_like(log[i["id"]].get("new")): why = "new own-site times look like office/centre hours"
                elif len(grp) > 1: why = "own site gives one table for several branches; cannot tell which branch"
                if why:
                    i["opening_times"] = orig.get(i["id"]); log[i["id"]].update(status="unconfirmed", reason=why, reverted=True)
                    _unconfirm(i, kind, field, why)
        for i in items: i.pop("_orig_times", None)
    return log

def summary(log):
    from collections import Counter
    return dict(Counter(v["status"] for v in log.values()))

def geocode(pcs, fetcher=None):
    """Postcode -> (lat, lng) via postcodes.io bulk lookup. Unknown postcodes are simply absent (never guessed)."""
    out, pcs = {}, sorted({p for p in pcs if p})
    for s in range(0, len(pcs), 100):
        try:
            req = urllib.request.Request("https://api.postcodes.io/postcodes", json.dumps({"postcodes": pcs[s:s + 100]}).encode(),
                                         headers=dict(UA, **{"Content-Type": "application/json"}))
            for x in json.load(urllib.request.urlopen(req, timeout=60, context=CTX))["result"]:
                if x["result"]: out[x["query"]] = (x["result"]["latitude"], x["result"]["longitude"])
        except Exception: pass
    return out

def discover_layer(cands, existing, kind, run_day, unverified, log_path, fetcher=fetch_raw, threads=24):
    """Shelters / warm spaces: dedupe directory candidates against what we already have, own-site check the rest.
    Passing candidates are added to `unverified` (tier 2, 'Unverified - call before you go', sign_url = own site),
    so the verification gate and recheck.py re-fetch and re-confirm them on every run like any other entry.
    Returns (new_candidates_to_append_to_fresh, log)."""
    need = [c for c in cands if c.get("lat") is None and c.get("postcode")]
    if need:
        g = geocode([c["postcode"] for c in need])
        for c in need:
            if c["postcode"] in g: c["lat"], c["lng"] = g[c["postcode"]]
    new, dup = dedupe(cands, existing)
    log = {"run": run_day, "candidates": len(cands), "already_on_map": dup, "new": len(new), "added": [], "flagged": []}
    def one(c): return c, (own_site_check(c, kind, fetcher) if c.get("lat") is not None else {"result": "flag", "reasons": ["no postcode/coordinates in directory, cannot pin without guessing"]})
    with cf.ThreadPoolExecutor(threads) as ex: res = list(ex.map(one, new))
    add = []
    for c, r in res:
        ev = {k: r.get(k) for k in ("url", "final_url", "http", "sha256", "etag", "last_modified")}
        if r["result"] == "add":
            c = dict(c); c.setdefault("source", c.get("directory")); c["last_verified"] = run_day
            c.setdefault("groups", []); c.setdefault("season", "Not stated")
            if kind == "ws" and c.get("hours_text") and not c.get("hours"):
                from times import normalise
                c["hours"] = hours_from_ot(normalise({"raw": c["hours_text"], "status": "TIMES_TEXT_ONLY"})) or {}
            u = {"name": c["name"], "sign_url": r["final_url"], "checked_on": run_day, "discovered_via": c.get("directory"),
                 "sign": "Own site names it, shows its postcode and describes the service (auto-discovered, %s)" % run_day}
            if kind == "sh" and (r.get("referral_only") or re.search(r"referral", c.get("referral") or "", re.I)):
                u["access_type"] = "referral_only"; c["referral"] = "Referral only. " + (c.get("referral") or "Referral needed, per own site")
            unverified[c["id"]] = u; add.append(c)
            log["added"].append({"id": c["id"], "name": c["name"], "postcode": c.get("postcode"), "directory": c.get("directory"), **ev})
        else:
            log["flagged"].append({"id": c["id"], "name": c["name"], "postcode": c.get("postcode"), "website": c.get("website"),
                                   "directory": c.get("directory"), "directory_url": c.get("directory_url"), "reasons": r["reasons"], **ev})
    json.dump(log, open(log_path, "w"), indent=1, ensure_ascii=False)
    return add, log
