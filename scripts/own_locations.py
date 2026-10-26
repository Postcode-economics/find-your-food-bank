"""Own-site locations pages (overrides/own_location_pages.json) -> food bank location pins.
The page is the authority: matched Give Food pins take the page's address/postcode/times, missing centres are added
(snapshot in overrides/foodbank_own_pages.json, read by classify.add_extra_locations), Give Food pins not on the page are dropped.
opening_times uses the same schema as overrides/opening_times.json: {checked_date, raw, source_url, status, structured{mon..sun:[[HH:MM,HH:MM]]}}."""
import datetime, html, json, os, re, urllib.request
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
UA = {"User-Agent": "Mozilla/5.0 (helpmap.uk food bank map refresh)"}
PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf8", "ignore")

def lines_of(page):
    t = re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [re.sub(r"\s+", " ", x).strip() for x in t.split("\n") if x.strip()]

def parse(page):
    L = lines_of(page); out = []
    for k, x in enumerate(L):
        if x != "Opening times": continue
        j = k - 1
        while j > 0 and (re.match(r"^[\d ]{10,}$", x := L[j]) or "@" in L[j] or "[email" in L[j]): j -= 1
        name = L[j].strip(); m = k + 1; rows = {}; raw = "Opening times "
        for d in DAYS:
            if m + 1 >= len(L) or L[m] != d: break
            v = L[m + 1]; raw += "%s %s " % (d, v); m += 2
            rng = re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", v)
            if rng: rows[d.lower()] = [[a.zfill(5), b.zfill(5)] for a, b in rng]
        else:
            if L[m] != "Address": continue
            addr = []; m += 1
            while m < len(L) and not L[m].startswith("Directions"): addr.append(L[m].rstrip(".")); m += 1
            pcs = [p for p in (PC.search(a.upper()) for a in addr) if p]
            if not pcs: continue
            pc = "%s %s" % pcs[-1].groups()
            parts = []
            for a in addr:
                a = PC.sub("", a.upper()) and re.sub(PC.pattern, "", a, flags=re.I).strip(" ,")
                if a and a not in parts: parts.append(a)
            out.append({"name": name, "address": ", ".join(parts + [pc]), "postcode": pc, "raw": raw, "structured": rows})
    return out

def slug(s): return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", ""))).strip("-")

DAYLINE = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*:?\s*(.+)$", re.I)
SPAN = re.compile(r"(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)\s*[-–—]\s*(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)", re.I)

def _hours(lines):
    """Day lines ('Monday: 10am-12.30pm', 'Friday: Closed') -> (raw, structured or None). Closed days are omitted."""
    from times import _range
    raw, rows = [], {}
    for ln in lines:
        m = DAYLINE.match(ln.strip())
        if not m: continue
        day, rest = m.group(1)[:3].lower(), m.group(2).strip()
        raw.append(ln.strip())
        if re.search(r"\bclosed\b", rest, re.I): continue
        sm = SPAN.search(rest)
        if not sm: return " | ".join(raw), None
        got = _range(sm.group(1), sm.group(2))
        if not got: return " | ".join(raw), None
        rows.setdefault(day, []).append(list(got))
    return " | ".join(raw), (rows or None)

def parse_kirkcaldy(page):
    """Kirkcaldy Foodbank get-food page: named distribution points, then 'Opening hours:' and day lines.
    https://www.kirkcaldyfoodbankcharity.org.uk/get-food"""
    L = lines_of(page)
    out = []
    for k, x in enumerate(L):
        if x.lower().rstrip(":") != "opening hours": continue
        hours, j, back = [], k - 1, []
        m = k + 1
        while m < len(L) and DAYLINE.match(L[m].strip()):
            hours.append(L[m].strip()); m += 1
        while j >= 0:
            t = L[j].strip().strip("\u200b")
            j -= 1
            if not t or t in ("*", "Agency referrals only"): continue
            if DAYLINE.match(t) or t.lower().rstrip(":") == "opening hours": break
            back.append(t)
            if re.search(r"(centre|house|living)\b", t, re.I) and not PC.search(t.upper()): break
        back = [t for t in reversed(back)]
        if not back: continue
        name = re.sub(r"\s*\(cabin\)\s*", "", back[0], flags=re.I).strip()
        addr = [re.sub(r"\s+", " ", a).strip(" ,") for a in back[1:]]
        pcs = [p for p in (PC.search(a.upper()) for a in addr) if p]
        if not pcs: continue
        pc = "%s %s" % pcs[-1].groups()
        raw, structured = _hours(hours)
        if not structured: continue
        address = re.sub(r"\s*,?\s*([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\s*$", r", \1 \2", ", ".join(addr), flags=re.I)
        out.append({"name": name, "address": address, "postcode": pc, "raw": raw, "structured": structured})
    return out

SOUTHEND_ROW = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm))\s*[-–—]\s*(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm))\s+"
    r"(.+?)\s*(?:\(\s*Please check for changes on bank holidays\s*\))?\s*$", re.I)

def parse_southend(page):
    """Southend Foodbank locations page: one voucher centre per line, Friendship House excluded (donations only).
    https://southend.foodbank.org.uk/about-us/locations"""
    from times import _range
    out = []
    for x in lines_of(page):
        m = SOUTHEND_ROW.match(x.strip())
        if not m: continue
        body = m.group(4).strip().rstrip(".")
        pcs = list(PC.finditer(body.upper()))
        if not pcs: continue
        pc = "%s %s" % pcs[-1].groups()
        before = body[:pcs[-1].start()].strip(" ,")
        # "40 Hedingham Place" / "90 Thorpedene Gardens" starts the street; otherwise the first comma does
        bits = re.split(r",?\s+(?=\d)", before, maxsplit=1) if re.search(r"\d", before) else [p.strip() for p in before.split(",", 1)]
        nm = bits[0].strip(" ,")
        if not nm: nm = before
        got = _range(m.group(2), m.group(3))
        if not got: continue
        day = m.group(1)[:3].lower()
        out.append({"name": nm, "address": before + ", " + pc, "postcode": pc,
                    "raw": "%s %s-%s" % (m.group(1), m.group(2), m.group(3)),
                    "structured": {day: [list(got)]}})
    return out

PARSERS = {"trussell_table": None, "kirkcaldy_distribution": parse_kirkcaldy, "southend_locations": parse_southend}

def geocode(pcs):
    req = urllib.request.Request("https://api.postcodes.io/postcodes", json.dumps({"postcodes": pcs}).encode(), dict(UA, **{"Content-Type": "application/json"}))
    r = json.load(urllib.request.urlopen(req, timeout=30))
    return {x["query"]: (round(x["result"]["latitude"], 6), round(x["result"]["longitude"], 6)) for x in r["result"] if x["result"]}

def words(s): return {w for w in re.findall(r"[a-z]{4,}", s.lower().replace("'", "")) if w not in ("church", "centre", "foodbank", "coventry", "england", "evangelical", "baptist", "christian")}

ALL_CLOSED_RE = re.compile(r"^\s*(opening times\s*)?((mon|tue|wed|thu|fri|sat|sun)\w*\s+closed\s*){7}$", re.I)
def all_closed(raw):
    """True when the page lists all seven days, every one 'Closed' (e.g. a paused Coventry centre)."""
    return bool(raw) and bool(ALL_CLOSED_RE.match(raw.strip()))

def refresh(items, root, today=None, fetcher=fetch, geo=geocode):
    """Mutates items. Returns a log dict. Never raises."""
    today = (today or datetime.date.today()).isoformat()
    cfg = {k: v for k, v in json.load(open(os.path.join(root, "overrides", "own_location_pages.json"))).items() if not k.startswith("_")}
    sp = os.path.join(root, "overrides", "foodbank_own_pages.json")
    snap = json.load(open(sp)) if os.path.exists(sp) else {"_comment": "Generated by scripts/own_locations.py from own locations pages; last good scrape. Read by classify.add_extra_locations."}
    log = {}
    for parent, c in cfg.items():
        try:
            fn = PARSERS.get(c.get("format") or "trussell_table") or parse
            cs = fn(fetcher(c["url"]))
        except Exception as e: cs = []; log[parent] = {"status": "fetch failed: %r" % e}
        if len(cs) < c.get("min_centres", 1):
            log.setdefault(parent, {"status": "parsed only %d centres" % len(cs)}); log[parent]["kept_snapshot"] = True; continue
        gf = [i for i in items if i["type"] == "location" and i["id"].split("/")[0] == parent]
        try: ll = geo(sorted({x["postcode"] for x in cs}))
        except Exception: ll = {}
        for k in [k for k, v in snap.items() if not k.startswith("_") and v.get("parent") == parent]: del snap[k]
        used, matched, added = set(), [], []
        def sim(a, b): A, B = words(a), words(b); return len(A & B) / max(1, len(A | B))
        pairs = {}  # pass 1: same postcode; pass 2: clearly the same name (>=50% word overlap)
        for x in cs:
            h = next((i for i in gf if i["id"] not in used and i["postcode"].replace(" ", "") == x["postcode"].replace(" ", "")), None)
            if h: used.add(h["id"]); pairs[id(x)] = h
        for x in cs:
            if id(x) in pairs: continue
            h = max((i for i in gf if i["id"] not in used), key=lambda i: sim(i["name"], x["name"]), default=None)
            if h and sim(h["name"], x["name"]) >= 0.5: used.add(h["id"]); pairs[id(x)] = h
        for x in cs:
            ot = {"checked_date": today, "raw": x["raw"], "source_url": c["url"], "status": "TIMES_FOUND", "structured": x["structured"]} if x["structured"] else None
            hit = pairs.get(id(x))
            if hit:
                matched.append(hit["id"])
                hit.update(name=x["name"], address=x["address"], postcode=x["postcode"], opening_times=ot)
                if ot is None and all_closed(x["raw"]): hit["_own_all_closed"] = {"checked_date": today, "raw": x["raw"], "source_url": c["url"]}
                if x["postcode"] in ll: hit["lat"], hit["lng"] = ll[x["postcode"]]
                continue
            if x["postcode"] not in ll: log.setdefault(parent, {}).setdefault("ungeocoded", []).append(x["name"]); continue
            k = "%s/%s" % (parent, slug(x["name"]))
            snap[k] = {"parent": parent, "name": x["name"], "address": x["address"], "postcode": x["postcode"], "lat": ll[x["postcode"]][0], "lng": ll[x["postcode"]][1],
                       "evidence": "%s locations page: %s, %s" % (parent, x["name"], x["raw"].strip()), "evidence_url": c["url"], "opening_times": ot}
            added.append(k)
        dropped = [i["id"] for i in gf if i["id"] not in used]
        items[:] = [i for i in items if i["id"] not in set(dropped)]
        log[parent] = {"status": "ok", "url": c["url"], "centres": len(cs), "matched": matched, "added": added, "dropped_not_on_page": dropped}
    json.dump(snap, open(sp, "w"), indent=1, ensure_ascii=False)
    return log

def protect_times(items, root):
    """Put hand-checked opening times back after the locations scrape and the own-site times pass.
    overrides/opening_times.json entries marked protected, or whose reader starts 'hand-reviewed', win:
    the next refresh cannot replace them with a scraped table from the wrong centre. Returns how many were set."""
    p = os.path.join(root, "overrides", "opening_times.json")
    if not os.path.exists(p): return 0
    times = json.load(open(p))
    from times import normalise
    n = 0
    for i in items:
        ot = times.get(i["id"])
        if isinstance(ot, dict) and (ot.get("protected") or str(ot.get("reader") or "").startswith("hand-reviewed")):
            i["opening_times"] = normalise(ot); n += 1
    return n
