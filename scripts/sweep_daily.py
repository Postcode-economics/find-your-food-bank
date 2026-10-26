"""Once-daily deep sweep of council and voluntary-sector warm space / shelter pages.

Separate from the 3x-daily refresh (which re-checks every published entry). This job only
DISCOVERS: it re-reads every council sitemap and every list page in sweep_sources.json, extracts
venue blocks (name, address with postcode, weekly times) and adds NEW entries under the two-tier rules:
  verified   = page is dated to the current season / updated in the last MAX_PAGE_AGE_DAYS,
               and the block gives a parseable weekly day+time.
  unverified = page dated as above but the times are missing or not a simple weekly pattern
               ('Unverified - call before you go').
  pending    = anything undated, unparseable or ambiguous: logged for a human, never put on the map.
Shelter blocks that say referral are flagged access_type=referral_only.
Only sources marked "auto_add": true in sweep_sources.json (layout checked by a human) are added to
the map automatically; council pages and other lists go to logs/sweep_pending.json with a proposed tier.
Fail-safe: never edits or removes an existing entry; per-source errors are logged and skipped;
if too many sources fail, or a run would add more than MAX_NEW entries, nothing is written to
the map files (everything goes to logs/sweep_pending.json). Files are written atomically after a
schema check. Every new entry carries source_url so the 3x-daily recheck can re-verify it.
"""
import os, re, sys, json, datetime, tempfile, urllib.request, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
from recheck import fetch, schema_errors
import learning
import auto_rules; RULES = auto_rules.load()  # owner 25 Oct 2026
from sweep_hours import parse as parse_hours
OV = os.path.join(ROOT, "overrides"); LOGS = os.path.join(ROOT, "logs")
MAX_NEW = int(os.environ.get("SWEEP_MAX_NEW", "150"))
MAX_FAIL_RATE = float(os.environ.get("SWEEP_MAX_FAIL_RATE", "0.5"))
MAX_PAGE_AGE_DAYS = int(os.environ.get("SWEEP_MAX_PAGE_AGE_DAYS", "120"))
KEY_URL = re.compile(r"warm-?(space|hub|place|welcome|bank)|welcoming-spaces|swep|severe-weather|cold-weather|night-?shelter|rough-sleep|emergency-accommodation|hybiau-cynnes|mannau-cynnes", re.I)
KEY_TXT = re.compile(r"warm (space|hub|place|bank|welcome)|welcoming space|night shelter|severe weather emergency|emergency accommodation", re.I)
PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b")
SHELTER = re.compile(r"night shelter|emergency accommodation|direct access|hostel|bed(s)? for the night", re.I)
REFERRAL = re.compile(r"referral (only|required|needed)|by referral|must be referred|referrals? (are )?(taken|accepted) (only )?(through|via|from)", re.I)
CLOSED = re.compile(r"\b(has|have|is now|permanently) closed\b|no longer (open|running)|closed for (the )?(season|winter)", re.I)
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"

def today(): return datetime.date.fromisoformat(os.environ["SWEEP_TODAY"]) if os.environ.get("SWEEP_TODAY") else datetime.date.today()

def season_label(d):
    y = d.year if d.month >= 7 else d.year - 1
    return y, y + 1

def page_dated(text, last_modified="", d=None):
    """True only if the page itself shows it is current: a current-season reference (e.g. 'winter 2026-27'),
    an explicit 'updated/reviewed <date>' within MAX_PAGE_AGE_DAYS, or dated session ranges this season.
    A copyright year alone does NOT count. Returns (bool, reason)."""
    d = d or today(); y1, y2 = season_label(d)
    t = re.sub(r"(©|copyright)\s*(\w+\s*)?\d{4}", " ", text, flags=re.I)
    if re.search(rf"(winter|season)\s*{y1}\s*[-–/]\s*(20)?{str(y2)[2:]}\b|{y1}\s*[-–/]\s*(20)?{str(y2)[2:]}\s*(winter|season)", t, re.I):
        return True, f"current season {y1}-{str(y2)[2:]} named on page"
    for m in re.finditer(rf"(updated|reviewed|published|last edited|modified)[^0-9]{{0,25}}(\d{{1,2}})(st|nd|rd|th)?\s+({MONTHS})\s+(20\d\d)", t, re.I):
        try:
            dt = datetime.datetime.strptime(f"{m.group(2)} {m.group(4)} {m.group(5)}", "%d %B %Y").date()
        except ValueError:
            continue
        if 0 <= (d - dt).days <= MAX_PAGE_AGE_DAYS: return True, f"page says {m.group(1)} {dt}"
    for m in re.finditer(r"(20\d\d)-(\d\d)-(\d\d)[ T]\d\d:\d\d", t):  # WordPress published/modified stamps
        try: dt = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: continue
        if 0 <= (d - dt).days <= MAX_PAGE_AGE_DAYS: return True, f"page timestamp {dt}"
    return False, "no current date on page (copyright year ignored)"

def blocks(text):
    """Split page text into venue blocks: 'Name – address ... POSTCODE. times ...'. One block per postcode."""
    pcs = list(PC.finditer(text)); out = []
    for i, m in enumerate(pcs):
        before = text[(pcs[i-1].end() if i else max(0, m.start()-300)):m.start()]
        after = text[m.end():(pcs[i+1].start() if i+1 < len(pcs) else m.end()+400)]
        cut = [x.end() for x in re.finditer(r"(\d\s?(am|pm)|\d{4})\.?\)?\s", before)]
        head = before[cut[-1]:] if cut else before[-220:]
        head = re.sub(r"^\s*(Opens?:?|Address:?)\s*", "", head.strip())
        mm = re.match(r"(.{3,200}?)\s*(?: – | - |, )(.*)$", head)
        if not mm: continue
        name, addr = mm.group(1), mm.group(2).strip(" ,")
        name = re.split(r"(?<!\bSt)(?<!\bSt\.)[.:!?]\s+", name)[-1].strip(" .:")
        times = re.sub(r"^\W*(Opens?:?|Opening times:?)\s*", "", after.strip(" .,"))[:220]
        nxt = list(re.finditer(r"(\d\s?(am|pm)|\d{4})\.?\)?\s", times))
        out.append({"name": name, "address": (addr + ", " if addr else "") + m.group(1), "postcode": m.group(1), "times": times, "context": before[-300:] + m.group(0) + after[:300]})
    return out

VENUE = re.compile(r"\b(hub|centre|center|church|chapel|library|hall|caf[eé]|room|house|club|pavilion|lounge|space|shelter|hostel|project|community|trust|mission|institute|association|pantry|kitchen|museum|cathedral|parish|quaker|methodist|baptist|salvation army|ymca|foyer|living room|coffee)\b", re.I)
JUNK = re.compile(r"\b(contact|e-?mail|website|information|accessibility|registered office|address|telephone|phone|opening|monday|tuesday|wednesday|thursday|friday|saturday|sunday|closed|cookies?|privacy|vendor|support email|support provided|food ?bank)\b", re.I)
GENERIC = re.compile(r"^(the )?(meeting room|county hall|town hall|main hall|council chamber|reception|civic cent(re|er)|community cent(re|er)|church hall|library)$", re.I)
PAST = re.compile(rf"(until|ends?|ending|to|closes?)\s+(\w+day,?\s+)?(\d{{1,2}})(st|nd|rd|th)?\s+({MONTHS})\s+(20\d\d)", re.I)
def ended(ctx, d=None):
    d = d or today()
    for m in PAST.finditer(ctx):
        try:
            if datetime.datetime.strptime(f"{m.group(3)} {m.group(5)} {m.group(6)}", "%d %B %Y").date() < d: return True
        except ValueError: pass
    return False
def excluded():
    f = os.path.join(OV, "sweep_exclude.json")
    return {(x["postcode"].replace(" ", "").upper()) for x in json.load(open(f))} if os.path.exists(f) else set()
def blocks_numbered(text):
    """'12. Name Address: ... POSTCODE Email: .. Telephone: .. Opening times: ...' (Voluntary Action Islington layout)."""
    out = []
    for m in re.finditer(r"(?:^| )\d+\. (.{3,80}?) Address: (.+?)(?: Email: .+?)?(?: Telephone: .+?)? Opening (?:times|hours): (.+?)(?= \d+\. | [A-Z][a-z]+(?: [A-Za-z&]+){0,4} 1\. |$)", text):
        pc = PC.search(m.group(2))
        if not pc: continue
        times = re.split(r" Additional information| Services & advice", m.group(3))[0]
        out.append({"name": m.group(1).replace("Squa re", "Square").strip(), "address": m.group(2).strip(), "postcode": pc.group(1), "times": times, "context": m.group(0)})
    return out

def blocks_location_fields(text):
    """'Name [This space opens on <dates>] Location <address POSTCODE> Opening [dates and] hours <times> Activity ...' (Tewkesbury layout)."""
    out = []
    for m in re.finditer(r"([A-Z][^.]{2,70}?) (?:This space opens on (.{5,60}?) )?Location (.+?\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b Opening (?:dates and )?hours (.+?) (?=Activity|Food & drink|Support|Contact)", text):
        pc = PC.search(m.group(3)); st = m.group(2) or ""
        if st:
            mm = re.match(rf"(\d{{1,2}}) ({MONTHS}) (20\d\d)", st, re.I)
            if mm and datetime.datetime.strptime(" ".join(mm.groups()), "%d %B %Y").date() > today():
                continue  # not open yet
        out.append({"name": m.group(1).strip(), "address": m.group(3).strip(), "postcode": pc.group(1), "times": m.group(4).strip(), "context": m.group(0)})
    return out

PARSERS = {"dash": None, "numbered_fields": blocks_numbered, "location_fields": blocks_location_fields}

def name_ok(n):
    if GENERIC.match(n.strip()): return False
    if re.match(r"\(?[a-z]", n) or JUNK.search(n) or not VENUE.search(n): return False
    return 3 <= len(n) <= 80 and (n[0].isupper() or n[0] == "(") and not re.search(r"\d{3,}|cookie|javascript|menu|skip to", n, re.I)

def weekly_hours(times):
    if re.search(r"fortnight|month|first|second|third|fourth|last|except|term time|bank holiday|clocks|from \w+ \d", times, re.I): return None
    first = re.split(r"(?<=[ap]m)\.\s|(?<=[ap]m)\s(?=[A-Z(])", times)[0]
    h = parse_hours(re.sub(r"^Every ", "", first))
    if h and len(set(re.findall(r"(?:mon|tues|wednes|thurs|fri|satur|sun)day", first, re.I))) > len(h) and " to " not in first and "–" not in first.split(",")[0]:
        return None
    return h

def slug(prefix, n): return prefix + "-" + re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")[:40]
def words(n): return {w for w in re.findall(r"[a-z]{4,}", n.lower())} - {"community", "centre", "church", "space", "warm", "hall", "the", "library", "room", "welcome"}

def existing(layer):
    items = []
    js = os.path.join(ROOT, layer + ".js")
    if os.path.exists(js):
        try: items = json.loads(open(js).read().split("=", 1)[1].strip().rstrip(";"))["items"]
        except Exception: items = []
    man = json.load(open(os.path.join(OV, layer + "_manual.json")))
    return items + man, man

def is_dup(n, pc, pool):
    """Fail-safe duplicate test: ANY existing entry at the same postcode counts as a duplicate."""
    k = pc.replace(" ", "").upper()
    return any((b.get("postcode") or "").replace(" ", "").upper() == k for b in pool)

def geo(pcs, opener=urllib.request.urlopen):
    G = {}; pcs = sorted(set(pcs))
    for k in range(0, len(pcs), 100):
        req = urllib.request.Request("https://api.postcodes.io/postcodes", json.dumps({"postcodes": pcs[k:k+100]}).encode(), {"Content-Type": "application/json"})
        for x in json.load(opener(req, timeout=30))["result"]:
            if x["result"]: G[x["query"]] = x["result"]
    return G

def council_pages(c, fetcher):
    """Known relevant pages plus any new relevant URLs in the council's sitemap(s)."""
    urls = list(c.get("known_pages", []))
    base = c["site"].rstrip("/")
    seen = set(); todo = [base + "/sitemap.xml"]
    rb = fetcher(base + "/robots.txt")
    todo += re.findall(r"(?im)^sitemap:\s*(\S+)", rb.get("raw", "") or rb.get("text", ""))
    n = 0
    while todo and n < 30:
        u = todo.pop(0)
        if u in seen: continue
        seen.add(u); n += 1
        r = fetcher(u); body = r.get("raw") or r.get("text", "")
        for loc in re.findall(r"https?://[^\s<>\"']+", body):
            if loc.endswith(".xml") or "sitemap" in loc.lower(): todo.append(loc)
            elif KEY_URL.search(loc): urls.append(loc)
    return sorted(set(urls))[:40]

def section(text, start, end=None):
    """Cut a page down to one titled section. Returns '' if the start marker is missing (fail-safe: no entries)."""
    i = text.find(start)
    if i < 0: return ""
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j] if j > 0 else text[i:]

def extract(page_text, url, source_name, layer_hint, last_modified="", trusted=False, parser="dash", sect=None):
    """Return candidate entries (dicts) from one page with tier decided by the two-tier rules."""
    if not KEY_TXT.search(page_text): return []
    dated, why = page_dated(page_text, last_modified)
    if sect: page_text = section(page_text, sect.get("start", ""), sect.get("end"))
    out = []
    for b in (PARSERS.get(parser) or blocks)(page_text):
        ctx = b["context"]
        if CLOSED.search(b["times"][:160]) or ended(ctx): continue
        layer = "shelters" if SHELTER.search(ctx) and (layer_hint == "shelters" or re.search(r"shelter|emergency accommodation", b["name"], re.I)) else "warmspaces"
        e = dict(name=b["name"], address=b["address"], postcode=b["postcode"], source_url=url, source=source_name, times_text=b["times"][:200], layer=layer, page_date=why)
        if layer == "shelters": e["access_type"] = "referral_only" if REFERRAL.search(ctx) else None
        structured = parser != "dash"   # name comes from a labelled field, so the venue-word test is not needed
        if not (name_ok(b["name"]) or (structured and not JUNK.search(b["name"]) and not re.match(r"\(?[a-z]", b["name"]) and len(b["name"]) <= 80)): e.update(tier="pending", reason="name not clear"); out.append(e); continue
        if re.search(r"Contact:?\s*$", ctx[:ctx.find(b["name"])] if b["name"] in ctx else "", re.I): e.update(tier="pending", reason="name taken from a contact line"); out.append(e); continue
        if not trusted and not KEY_TXT.search(ctx) and not SHELTER.search(ctx): e.update(tier="pending", reason="block itself does not say warm space/shelter"); out.append(e); continue
        h = weekly_hours(b["times"])
        if not dated: e.update(tier="pending", reason=why)
        elif h: e.update(tier="verified", hours=h)
        else: e.update(tier="unverified", hours={})
        if layer == "shelters": e["access_type"] = "referral_only" if REFERRAL.search(ctx) else None
        out.append(e)
    return out

def to_records(e, g, d):
    i = slug("sw", e["name"] + "-" + e["postcode"].replace(" ", ""))
    q = e["times_text"].split(". ")[0]
    if e["layer"] == "warmspaces":
        man = {"id": i, "name": e["name"], "address": e["address"], "postcode": e["postcode"], "lat": g["latitude"], "lng": g["longitude"], "phone": "", "website": e["source_url"], "hours": e.get("hours", {}), "provided": [], "booking": "Not stated", "notes": e["source"], "scheme_end": "", "scheme_dates": "Not stated by source", "ended": False, "source": e["source"] + " (daily sweep)", "source_url": e["source_url"], "last_verified": d, "stale": False}
        if e["tier"] == "verified":
            ov = {"name": e["name"], "evidence_url": e["source_url"], "evidence_name": e["source_url"].split("/")[2].replace("www.", ""), "quote": e["name"] + " – " + q, "day_time_quote": q, "hours": e["hours"], "address": e["address"], "postcode": e["postcode"], "lat": g["latitude"], "lng": g["longitude"], "verified_on": d, "bar": "Daily sweep: " + e["page_date"] + "; weekly day/time stated"}
        else:
            ov = {"name": e["name"], "sign_url": e["source_url"], "sign": "Daily sweep: listed on " + e["source"] + " (" + e["page_date"] + "); " + (q or "no times given"), "day_time_quote": q, "checked_on": d}
    else:
        acc = "Referral only (stated on source page)" if e.get("access_type") == "referral_only" else "Access not stated – call before you go"
        man = {"id": i, "name": e["name"], "address": e["address"], "postcode": e["postcode"], "lat": g["latitude"], "lng": g["longitude"], "phone": "", "website": e["source_url"], "hours": "", "referral": acc, "beds": "", "groups": [], "season": "", "operator": "", "flag_closed": False, "source": e["source"] + " (daily sweep)", "source_url": e["source_url"], "last_verified": d, "stale": False, "access_type": e.get("access_type")}
        if e["tier"] == "verified":
            ov = {"name": e["name"], "access": acc, "evidence_url": e["source_url"], "evidence_name": e["source_url"].split("/")[2].replace("www.", ""), "quote": e["name"] + " – " + q, "day_time_quote": q, "verified_on": d, "access_type": man["access_type"]}
        else:
            ov = {"name": e["name"], "sign_url": e["source_url"], "sign": "Daily sweep: listed on " + e["source"] + " (" + e["page_date"] + ")", "checked_on": d, "access_type": man["access_type"], "access": acc}
    return i, man, ov

def atomic_dump(obj, path):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f: json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)

import discovery_rules as DR
def write_shelter_review(items, d, pd=None):
    """Shelter candidates found by the sweep go ONLY to the review section of reports/pending_owner.md (never the map)."""
    import re as _re
    pd = pd or os.path.join(ROOT, "reports", "pending_owner.md")
    L = ["<!-- sweep shelters -->", "## Shelter candidates from the sweep (review only)", "", f"Run {d}. Nothing here is on the map. Each needs a hand check before it is added.", ""]
    L += [f"- {e.get('name')} ({e.get('postcode', '')}) - {e.get('source_url', '')}" for e in items] or ["- none this run"]
    L.append("<!-- /sweep shelters -->")
    prev = open(pd).read() if os.path.exists(pd) else "# Pending for owner\n"
    prev = _re.sub(r"(?s)\n*<!-- sweep shelters -->.*?<!-- /sweep shelters -->\n*", "\n", prev).rstrip("\n")
    os.makedirs(os.path.dirname(pd), exist_ok=True)
    open(pd, "w").write(prev + "\n\n" + "\n".join(L) + "\n")
def run(sources=None, fetcher=fetch, geocoder=geo, write=True):
    d = today().isoformat()
    S = sources or json.load(open(os.path.join(HERE, "sweep_sources.json")))
    jobs = [(l["url"], l["name"], l.get("layer", "warmspaces"), bool(l.get("auto_add")), l.get("parser", "dash"), l.get("section")) for l in S.get("lists", [])]
    errors = []
    def cp(c):
        try: return [(u, c["name"], "warmspaces", False, "dash", None) for u in council_pages(c, fetcher)]
        except Exception as ex: errors.append((c["name"], "sitemap: " + str(ex)[:80])); return []
    with cf.ThreadPoolExecutor(16) as ex:
        for r in ex.map(cp, S.get("councils", [])): jobs += r
    try:  # the council severe-weather / rough sleeping pages found by swep.py: new shelter pages listed there are discovered too
        jobs += [(x["url"], x.get("council", "council"), "shelters", False, "dash", None) for x in json.load(open(os.path.join(OV, "swep_sources.json"))) if x.get("url")]
    except Exception as ex: errors.append(("swep_sources", str(ex)[:80]))
    jobs = list({(j[0], j[1]): j for j in jobs}.values())
    # owner 25 Oct 08:01: self-learning order (scripts/learning.py). Pages that keep failing rest (back-off, never past the
    # weekly floor); productive pages go first. Only order/selection - the discovery rules and guards below are unchanged.
    LS = learning.load() if (write and sources is None) else learning.load(os.devnull)
    order, resting_urls, _ = learning.plan(LS, [j[0] for j in jobs], d)
    pos = {u: n for n, u in enumerate(order)}; jobs = sorted((j for j in jobs if j[0] in pos), key=lambda j: pos[j[0]])
    def one(j):
        u, name, hint, auto, parser, sect = j
        try:
            r = fetcher(u)
            if r.get("http") != 200 or not r.get("text"): return ("fail", u, r.get("http"))
            c = extract(r["text"], r.get("final_url") or u, name, hint, r.get("last_modified", ""), trusted=auto, parser=parser, sect=sect)
            if not auto:  # layout not proven for this source: auto-add only as tier 2 ('Unverified - call before you go') and only
                # if owner's auto-add rule passes below (valid postcode, not within 150 m of anything, dated page, not held)
                c = [dict(e, proposed_tier=e["tier"], tier="unverified", auto_rule=True) if e["tier"] in ("verified", "unverified") else e for e in c]
            return ("ok", u, c)
        except Exception as ex: return ("fail", u, str(ex)[:80])
    with cf.ThreadPoolExecutor(16) as ex: R = list(ex.map(one, jobs))
    fails = [r for r in R if r[0] == "fail"]; cands = [e for r in R if r[0] == "ok" for e in r[2]]
    report = {"run": d, "pages": len(jobs), "failed": len(fails), "errors": errors[:200] + [[f[1], f[2]] for f in fails][:300], "added": [], "pending": [], "status": "ok"}
    if jobs and len(fails) / len(jobs) > MAX_FAIL_RATE:
        report["status"] = f"ABORTED: {len(fails)}/{len(jobs)} pages failed (> {MAX_FAIL_RATE:.0%}); nothing written"
        cands = [dict(e, tier="pending", reason="run aborted") for e in cands]
    state = {}
    for layer in ("warmspaces", "shelters"):
        pool, man = existing(layer)
        state[layer] = dict(pool=pool, man=man, ver=json.load(open(os.path.join(OV, layer + "_verified.json"))), unv=json.load(open(os.path.join(OV, layer + "_unverified.json"))), new=0)
    good = [e for e in cands if e["tier"] in ("verified", "unverified")]
    try: G = geocoder([e["postcode"] for e in good]) if good else {}
    except Exception as ex: G = {}; report["status"] = "geocoder failed: " + str(ex)[:80]
    adds = []; EX = excluded()
    shelter_review = []
    for e in cands:
        if e["postcode"].replace(" ", "").upper() in EX: continue
        if e["layer"] == "shelters":  # owner's rule (24 Oct): the sweep never adds shelters to the map, not even as 'Unverified'
            shelter_review.append(e); continue
        st = state[e["layer"]]
        if e["tier"] == "pending": report["pending"].append(e); continue
        if is_dup(e["name"], e["postcode"], st["pool"]): continue
        g = G.get(e["postcode"])
        if not g: report["pending"].append(dict(e, reason="postcode not found")); continue
        if e.get("auto_rule"):
            h = DR.held(e)
            if h: report["pending"].append(dict(e, reason="on hold: " + h.get("reason", ""))); continue
            near = [b for b in st["pool"] if b.get("lat") is not None and DR.hav(g["latitude"], g["longitude"], b["lat"], b["lng"]) < 0.15]
            if near: continue  # within 150 m of something already on the map = duplicate
            ds, s0, e0 = DR.dates_state({"notes": e.get("times_text", "")}, d)
            if ds == "past": report.setdefault("rejected", []).append(dict(e, reasons=["dates all in the past"])); continue
        i, man, ov = to_records(e, g, d)
        if e.get("auto_rule"):
            ds, s0, e0 = DR.dates_state({"notes": e.get("times_text", "")}, d)
            if s0: man["scheme_start"] = s0
            if e0: man["scheme_end"] = e0
        errs = schema_errors(dict(man, hours=man["hours"] if isinstance(man["hours"], dict) else {}), "ws" if e["layer"] == "warmspaces" else "sh")
        if errs: report["pending"].append(dict(e, reason="schema: " + "; ".join(map(str, errs))[:120])); continue
        if not auto_rules.may_add(e["layer"], RULES) and i not in auto_rules.approved(e["layer"], ROOT):  # owner 25 Oct 2026: new places wait for his OK
            report["pending"].append(dict(e, id=i, reason="new place - waiting for owner's OK (overrides/approved_new_places.json)")); continue
        st["pool"].append(man); adds.append((e, i, man, ov))
    if len(adds) > MAX_NEW:
        report["status"] = f"HELD: {len(adds)} new entries > SWEEP_MAX_NEW={MAX_NEW}; nothing written, all pending review"
        report["pending"] += [dict(a[0], reason="held: too many new in one run") for a in adds]; adds = []
    for e, i, man, ov in adds:
        st = state[e["layer"]]; st["man"].append(man); (st["ver"] if e["tier"] == "verified" else st["unv"])[i] = ov; st["new"] += 1
        report["added"].append({"id": i, "layer": e["layer"], "tier": e["tier"], "name": e["name"], "postcode": e["postcode"], "source_url": e["source_url"]})
    if write:
        if adds:
            for layer, st in state.items():
                if st["new"]:
                    atomic_dump(st["man"], os.path.join(OV, layer + "_manual.json"))
                    atomic_dump(st["ver"], os.path.join(OV, layer + "_verified.json"))
                    atomic_dump(st["unv"], os.path.join(OV, layer + "_unverified.json"))
        os.makedirs(LOGS, exist_ok=True)
        atomic_dump({k: v for k, v in report.items() if k != "pending"}, os.path.join(LOGS, "sweep_log.json"))
        atomic_dump({"run": d, "items": report["pending"][:2000]}, os.path.join(LOGS, "sweep_pending.json"))
        write_shelter_review(shelter_review, d)
    report["shelter_review"] = len(shelter_review)
    useful = {e.get("source_url") for e in report["added"]} | {e.get("source_url") for e in report["pending"]} | {e.get("source_url") for e in shelter_review}
    for (u, name, hint, auto, parser, sect), r in zip(jobs, R):
        learning.record(LS, u, d, r[0] == "ok", finds=int(u in useful), method=("list_page:" + parser) if auto else ("swep_page" if hint == "shelters" else "council_page"), kind="sweep_page")
    report["learning"] = {"resting": len(resting_urls), "planned": len(jobs)}
    if write and sources is None: learning.snapshot(LS, d); learning.save(LS)
    if write:
        DR.record("sweep", d, [dict(a, upcoming=bool(a.get("scheme_start", "") > d)) for a in report["added"]],
                  [dict(x, id=x.get("name"), reasons=[x.get("reason", "")]) for x in report["pending"] if x.get("auto_rule") or x.get("reason", "").startswith(("on hold", "postcode"))],
                  report.get("rejected", []), source="council pages + SWEP pages", root=ROOT)
    return report

if __name__ == "__main__":
    r = run()
    print(r["status"], "pages", r["pages"], "failed", r["failed"], "added", len(r["added"]), "pending", len(r["pending"]))
    try:  # food bank own locations pages (overrides/own_location_pages.json, e.g. Coventry): re-scrape, refresh the snapshot
        import own_locations
        js = open(os.path.join(ROOT, "data.full.js")).read(); fb = json.loads(js[js.index("{"):js.rindex("}") + 1])["items"]
        print("own locations pages:", json.dumps(own_locations.refresh(fb, ROOT)))
    except Exception as e: print("own locations pages: skipped", repr(e))
    sys.exit(0)
