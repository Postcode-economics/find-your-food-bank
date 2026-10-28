"""Own-site locations pages (overrides/own_location_pages.json) -> food bank location pins.
The page is the authority: matched Give Food pins take the page's address/postcode (their times change only through discover.times_gate_apply,
which reads this page), missing centres are added
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

def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if d.startswith("44"): d = "0" + d[2:]
    return d if len(d) == 11 and d[0] == "0" else ""

def phone_line(x):
    """A centre block's phone line, e.g. '01271 329902,' (Northern Devon's Barnstaple line ends in a comma)."""
    return bool(re.match(r"^[\d\s()+-]{10,}$", x.strip().rstrip(",;.").strip()))

def parse(page):
    L = lines_of(page); out = []
    for k, x in enumerate(L):
        if x != "Opening times": continue
        j = k - 1; phones = []
        while j > 0 and (phone_line(L[j]) or "@" in L[j] or "[email" in L[j]):
            p = norm_phone(L[j]) if phone_line(L[j]) else ""
            if p and p not in phones: phones.insert(0, p)
            j -= 1
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
            out.append({"name": name, "address": ", ".join(parts + [pc]), "postcode": pc, "raw": raw, "structured": rows,
                        "phone": phones[0] if len(phones) == 1 else "", "phones": phones})
    return out

CENTRE_PHONES = os.path.join("reports", "own_centre_phones.json")
def centre_phone_record(old, centre, pin_id, parent, url, run_at):
    """The phone a centre block gives for one pin, with the previous run's reading for the 2-run rule.
    A block with no number, or more than one, records no phone."""
    old = old if isinstance(old, dict) else {}
    rec = {"parent": parent, "id": pin_id, "name": centre["name"], "postcode": centre["postcode"], "phone": centre.get("phone") or "",
           "phones": centre.get("phones") or [], "source_url": url, "run_at": run_at}
    if old.get("run_at") and old.get("run_at") != run_at:
        rec["prev_phone"], rec["prev_run_at"] = old.get("phone") or "", old.get("run_at")
    elif old.get("prev_run_at"):
        rec["prev_phone"], rec["prev_run_at"] = old.get("prev_phone") or "", old.get("prev_run_at")
    return rec

def centre_phone_confirmed(rec):
    """The same single number in this centre's block on 2 separate runs."""
    return bool(isinstance(rec, dict) and rec.get("phone") and rec.get("prev_phone") == rec["phone"]
                and rec.get("prev_run_at") and rec.get("prev_run_at") != rec.get("run_at"))

def load_centre_phones(root):
    try: return json.load(open(os.path.join(root, CENTRE_PHONES), encoding="utf-8"))
    except Exception: return {}

def slug(s): return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", ""))).strip("-")

def geocode(pcs):
    req = urllib.request.Request("https://api.postcodes.io/postcodes", json.dumps({"postcodes": pcs}).encode(), dict(UA, **{"Content-Type": "application/json"}))
    r = json.load(urllib.request.urlopen(req, timeout=30))
    return {x["query"]: (round(x["result"]["latitude"], 6), round(x["result"]["longitude"], 6)) for x in r["result"] if x["result"]}

def words(s): return {w for w in re.findall(r"[a-z]{4,}", s.lower().replace("'", "")) if w not in ("church", "centre", "foodbank", "coventry", "england", "evangelical", "baptist", "christian")}

ALL_CLOSED_RE = re.compile(r"^\s*(opening times\s*)?((mon|tue|wed|thu|fri|sat|sun)\w*\s+closed\s*){7}$", re.I)
def all_closed(raw):
    """True when the page lists all seven days, every one 'Closed' (e.g. a paused Coventry centre)."""
    return bool(raw) and bool(ALL_CLOSED_RE.match(raw.strip()))

def _sig(ot): return json.dumps((ot or {}).get("structured") if isinstance(ot, dict) else None, sort_keys=True)

def refresh(items, root, today=None, fetcher=fetch, geo=geocode, run_at=None):
    """Mutates items. Returns a log dict. Never raises.
    Each centre block's own phone is recorded in reports/own_centre_phones.json for the phone gate (full_check.py);
    no phone is written here."""
    run_at = run_at or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    today = (today or datetime.date.today()).isoformat()
    cp_path = os.path.join(root, CENTRE_PHONES)
    old_cp = load_centre_phones(root); new_cp = dict(old_cp)
    cfg = {k: v for k, v in json.load(open(os.path.join(root, "overrides", "own_location_pages.json"))).items() if not k.startswith("_")}
    sp = os.path.join(root, "overrides", "foodbank_own_pages.json")
    snap = json.load(open(sp)) if os.path.exists(sp) else {"_comment": "Generated by scripts/own_locations.py from own locations pages; last good scrape. Read by classify.add_extra_locations."}
    log = {}
    for parent, c in cfg.items():
        try: cs = parse(fetcher(c["url"]))
        except Exception as e: cs = []; log[parent] = {"status": "fetch failed: %r" % e}
        if len(cs) < c.get("min_centres", 1):
            log.setdefault(parent, {"status": "parsed only %d centres" % len(cs)}); log[parent]["kept_snapshot"] = True; continue
        gf = [i for i in items if i["type"] == "location" and i["id"].split("/")[0] == parent]
        for k in [k for k, v in new_cp.items() if isinstance(v, dict) and v.get("parent") == parent]: del new_cp[k]
        # A centre at the food bank's own pin postcode is that pin (Bournemouth St George's Hub, Northern Devon Bideford), not a new place.
        pa = next((i for i in items if i["type"] == "foodbank" and i["id"] == parent), None)
        own = [x for x in cs if pa and (pa.get("postcode") or "").replace(" ", "") == x["postcode"].replace(" ", "")][:1]
        for x in own: new_cp[parent] = centre_phone_record(old_cp.get(parent), x, parent, parent, c["url"], run_at)
        cs = [x for x in cs if x not in own]
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
                if hit["postcode"].replace(" ", "") == x["postcode"].replace(" ", ""):  # a centre's line is tied to its pin by postcode only
                    new_cp[hit["id"]] = centre_phone_record(old_cp.get(hit["id"]), x, hit["id"], parent, c["url"], run_at)
                hit.update(name=x["name"], address=x["address"], postcode=x["postcode"])
                # The stored times stay. Only discover.times_gate_apply may change them (2 identical runs, log, undo);
                # pointing the stored times at this page makes the gate read exactly this page for the centre.
                old = hit.get("opening_times")
                if isinstance(old, dict) and not old.get("source_url"): old["source_url"] = c["url"]
                if ot and _sig(ot) != _sig(old): log.setdefault(parent, {}).setdefault("times_for_gate", []).append(hit["id"])
                if ot is None and all_closed(x["raw"]): hit["_own_all_closed"] = {"checked_date": today, "raw": x["raw"], "source_url": c["url"]}
                if x["postcode"] in ll: hit["lat"], hit["lng"] = ll[x["postcode"]]
                continue
            if x["postcode"] not in ll: log.setdefault(parent, {}).setdefault("ungeocoded", []).append(x["name"]); continue
            k = "%s/%s" % (parent, slug(x["name"]))
            snap[k] = {"parent": parent, "name": x["name"], "address": x["address"], "postcode": x["postcode"], "lat": ll[x["postcode"]][0], "lng": ll[x["postcode"]][1],
                       "evidence": "%s locations page: %s, %s" % (parent, x["name"], x["raw"].strip()), "evidence_url": c["url"], "opening_times": ot}
            if x.get("phone"): snap[k]["phone"] = x["phone"]
            added.append(k)
        dropped = [i["id"] for i in gf if i["id"] not in used]
        items[:] = [i for i in items if i["id"] not in set(dropped)]
        log[parent] = {"status": "ok", "url": c["url"], "centres": len(cs) + len(own), "matched": matched, "added": added, "dropped_not_on_page": dropped,
                       "times_for_gate": (log.get(parent) or {}).get("times_for_gate", [])}
        if own: log[parent]["parent_centre"] = own[0]["name"]
    json.dump(snap, open(sp, "w"), indent=1, ensure_ascii=False)
    try:
        os.makedirs(os.path.dirname(cp_path), exist_ok=True)
        json.dump(new_cp, open(cp_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
    except Exception as e: log["_centre_phones"] = "not written: %r" % e
    return log
