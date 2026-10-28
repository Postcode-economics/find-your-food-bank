"""Discovery + own-site cross-check, shared by all three layers (Dean, 21 Oct 2026).
Every 3x-daily run:
 1. Pull each major directory in full (food banks: Give Food + IFAN; shelters: OSM + Homeless Link 'Find help';
    warm spaces: Warm Welcome + Open Innovations aggregator of council/VCS directories).
 2. dedupe(): anything not already on the map (postcode, distance, name) is a candidate.
 3. own_site_check(): the candidate's OWN website is fetched this run (HTTP 200, same site after redirects,
    sha256/ETag/Last-Modified recorded). It passes only if the site names it, shows its postcode, shows it is
    food aid / shelter / warm space, and does not say it has closed. Pass -> added; anything else -> flagged in logs.
 4. cross_check_times(): for every entry, re-read opening times from its own website (and from opening_times.source_url
    when that page is not already in the fetch). The hours the card shows are compared with a fresh per-postcode timetable.
    The same timetable -> confirmed. One different timetable -> replaced. Pages that disagree, or a block that is
    delivery-only / donation hours -> flagged (differs_review) and the published hours kept. Unreachable -> old hours
    kept and marked unconfirmed. A page merely being up is not confirmation: every stored clock time occurring
    somewhere on the site is not enough, because a Friday-only card stays "confirmed" while Monday and Wednesday
    are also listed (Chichester, 26 Oct).
Never invents data: everything published comes from a fetched page or a directory record."""
import re, os, sys, json, html, ssl, math, hashlib, datetime, threading, urllib.request, urllib.parse, concurrent.futures as cf
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
    within 150 m regardless of name (Dean's auto-add rule, 23 Oct 2026), or same website host within 2 km."""
    pc, ct, ch = norm_pc(c.get("postcode")), tokens(c.get("name")), host(c.get("website"))
    for e in existing:
        same_name = bool(ct & tokens(e.get("name")) or ct & tokens(e.get("foodbank")))
        if pc and pc == norm_pc(e.get("postcode")) and (same_name or not ct): return True
        if c.get("lat") is None or e.get("lat") is None: continue
        d = hav(c["lat"], c["lng"], e["lat"], e["lng"])
        if d < 0.15 or (d < 0.3 and same_name): return True
        if ch and ch == host(e.get("website")) and d < 2 and ch not in ("facebook.com", "linktr.ee", "salvationarmy.org.uk"): return True
    return False
def dedupe(cands, existing):
    new, dup = [], 0; seen = []
    for c in cands:
        if is_dup(c, existing) or is_dup(c, seen): dup += 1; continue
        seen.append(c); new.append(c)
    return new, dup

# ---------- fetching ----------
# _cache is only for closure/discovery sharing one fetch inside a single run. A check of opening times or
# open days must not read it (Rule 27, 26 Oct 2026): those checks call fetch_live, which never reads or
# writes this cache and never opens a saved page. If the live request fails, the listing is flagged and
# the hours already on the card are left as they are.
_cache, _lock = {}, threading.Lock()
def _request(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20, context=CTX)
        raw = r.read(8_000_000).decode("utf8", "ignore")
        return {"http": r.status, "final_url": r.geturl(), "html": raw, "etag": r.headers.get("ETag", ""),
                "last_modified": r.headers.get("Last-Modified", ""), "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    except Exception as e:
        return {"http": getattr(e, "code", None) or "error", "final_url": url, "html": "", "error": str(e)[:120]}
def fetch_raw(url):
    with _lock:
        if url in _cache: return _cache[url]
    res = _request(url)
    with _lock: _cache[url] = res
    return res
def fetch_live(url):
    """Open the page now. No cache read, no cache write, no saved or archived copy."""
    return _request(url)
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
    if home["http"] != 200:
        h = home["http"]
        out["reasons"].append(f"own site did not return the page (HTTP {h}; usually a bot check)" if isinstance(h, int) and 200 <= h < 300
                              else f"own site unreachable (HTTP {h})"); return out
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
TIMESPAN = re.compile(r"((?:\b(?:mon(?:day)?|tues?(?:day)?|wed(?:nesday)?|weds|thu(?:rs?)?(?:day)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)s?\b\.?(?:\s*(?:,|&|and|-|–|to)\s*)?)+)[\s:,(]*((?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon|midday)\s*(?:-|–|—|to|until|till)\s*(?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon|midday))", re.I)
def norm_times(s):
    """'10.30am', '10:30', '10am' -> {'10:30','10:00'} in 24h (am/pm aware). Same rule as recheck.norm_times, kept here so
    the food bank build has no dependency on the shelter/warm-space modules."""
    out = set(); s = (s or "").lower().replace("noon", "12pm").replace("midday", "12pm")
    for h, m, ap in re.findall(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", s):
        h = int(h); m = int(m or 0)
        if h > 24 or m > 59 or (not ap and not m and h < 7): continue
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        out.add(f"{h:02d}:{m:02d}")
    return out
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
NOT_CLIENT = re.compile(r"office|warehouse|donat|drop[- ]?off|admin|phone line|telephone|helpline|call us|volunteer|wheelie|\bbins?\b|collection point|donation point"
                        r"|phone ?lines? (?:is |are )?(?:open|monitored|answered)|phone answered|phoneline|manned|church services?|sunday services?|\bworship\b|\bmass\b", re.I)  # rule 27 (26 Oct): phone/office/donation/church-service hours
ORDINAL = re.compile(r"\b(?:first|second|third|fourth|last|1st|2nd|3rd|4th)\s+(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+(?:of\s+)?(?:the|each|every)\s+month", re.I)
ORD_SPAN = re.compile(r"(\b(?:first|second|third|fourth|last|1st|2nd|3rd|4th)\s+(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+(?:of\s+)?(?:the|each|every)\s+month)[\s:,(–-]*((?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon)\s*(?:-|–|—|to|until|till)\s*(?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?|noon))", re.I)
APPT = re.compile(r"by appointment|appointment only|appointments only|phone in advance|telephone request|by arrangement|on request", re.I)   # North Ayrshire St John's: 'only open upon a telephone request'
DONATION_PAGE = re.compile(r"donat|giv(e|ing)|volunteer|drop-?off|support-us|fundrais", re.I)
def not_client_context(t, at, prev_span_end=None):
    """Up to 160 chars before the times, but not past the previous time span (that belongs to another line/centre).
    Upper Eden (23 Oct): 'Wheelie Bins outside the Sands Methodist Church in Appleby on: Tuesdays 11 - 11:30am'."""
    lo = max(0, at - 160)
    if prev_span_end is not None and prev_span_end > lo: lo = prev_span_end
    k = max(t.rfind(". ", lo, at), t.rfind("; ", lo, at))   # rule 27 (26 Oct): context stops at the previous sentence
    if k >= 0: lo = k + 2
    return bool(NOT_CLIENT.search(t[lo:at]))
def postcode_block(text, postcode):
    """The slice of `text` that belongs to this postcode, or None when that slice cannot be fixed.
    Same window extract_times uses: one postcode keeps the page; several postcodes keep only the block that
    sits with this one, and an unclear layout is not guessed."""
    t = text or ""
    pc = norm_pc(postcode)
    if not pc: return t
    if pc not in t.upper().replace(" ", ""): return None
    pcs = list(PC_RE.finditer(t.upper()))
    if len({a + b for a, b in (m.groups() for m in pcs)}) <= 1: return t
    hit = [m for m in pcs if m.group(1) + m.group(2) == pc]
    if not hit: return None
    s = hit[0].start(); e = hit[0].end()
    ends = [m.end() for m in pcs if m.end() <= s]; starts = [m.start() for m in pcs if m.start() >= e]
    first, last = pcs[0], pcs[-1]
    after = bool(TIMESPAN.search(t[last.end():last.end() + 300]))
    before = bool(TIMESPAN.search(t[max(0, first.start() - 300):first.start()]))
    if after and not before: lo, hi = s, min([e + 500] + starts)
    elif before and not after: lo, hi = max([max(0, s - 500)] + ends), e
    else: return None
    return t[lo:hi]
def extract_times(text, postcode=None):
    """Pull 'day(s) time-time' phrases from own-site text; if the site lists several postcodes, only this entry's block.
    Recognised layouts (Trussell 2026 cards, Trussell /locations tables, day/value columns, '(Tues)/(Fri)' rows) are
    read by rule27_formats first; prose is cleaned (non-breaking spaces, '12 noon', 'between X and Y', '10-12am',
    'except bank holidays') and phone/office/donation/service sentences are dropped before reading."""
    import rule27_formats as R27
    lay = R27.read_centre(text, postcode)
    if lay is not None:
        if not lay.get("structured"): return None   # recognised layout, but this centre is unclear: never guess
        return {"raw": lay["raw"], "status": "TIMES_FOUND", "structured": lay["structured"], "layout": lay["layout"],
                "quote": lay["quote"], "unclear_days": lay.get("unclear_days") or {}}
    text = strip_phone_hours(R27.clean(text))
    t = postcode_block(text, postcode)
    if t is None: return None   # postcode not on the page, or the layout is unclear: never guess
    segs, seen, prev_end, prev_skipped = [], set(), None, False
    found = []
    for m in ORD_SPAN.finditer(t):   # 'first Saturday of the month 9:30 - 11:30' kept as written (shown as text)
        if not not_client_context(t, m.start()): found.append((m.start(), (m.group(1) + " " + m.group(2)).strip()))
    ords = [(a, a + len(x) + 20) for a, x in found]
    for m in TIMESPAN.finditer(t):
        if any(a <= m.start() < b for a, b in ords): continue
        follows = prev_end is not None and m.start() - prev_end < 40 and not re.search(r"[.;]\s", t[prev_end:m.start()])   # a list continuing straight on from the last line (a full stop ends it)
        skip = (prev_skipped and follows) or not_client_context(t, m.start(), prev_end)
        prev_end, prev_skipped = m.end(), skip
        if skip: continue   # office / warehouse / donation / bin hours are not client times
        seg = (m.group(1).strip(" ,&-–") + " " + m.group(2)).strip()
        nxt = t[m.end():m.end() + 40]; nxt = nxt[:min([len(nxt)] + [x.start() for x in TIMESPAN.finditer(nxt)])]
        if APPT.search(nxt) or APPT.search(t[max(0, m.start() - 30):m.start()]): seg += " (by appointment)"
        found.append((m.start(), seg))
    for _, seg in sorted(found):
        if seg.lower() not in seen: seen.add(seg.lower()); segs.append(seg)
    if not segs: return None
    from times import normalise
    raw = " | ".join(segs)
    ba = APPT.search(t)   # the centre's own block says appointment / phone first / on request (North Ayrshire St John's)
    if ba and not APPT.search(raw): raw += " (" + ba.group(0).lower() + ")"; segs = segs + ["(" + ba.group(0).lower() + ")"]
    if APPT.search(raw) or ORDINAL.search(raw):   # monthly / appointment-only: keep as written, never as a weekly table
        return {"raw": raw, "status": "TIMES_TEXT_ONLY", "structured": None, "lines": segs}
    return normalise({"raw": raw, "status": "TIMES_TEXT_ONLY", "structured": None})
# 'Our phone lines are monitored Monday - Friday 09:30-13:30' is printed on every Trussell centre card: office/phone
# hours, never client session times (Cardiff Foodbank, 27 Oct 2026: every centre showed Mon-Fri 09:30-13:30).
PHONE_HOURS = re.compile(r"(?:phone lines?|telephone lines?|lines are|office)\s+(?:are\s+)?(?:monitored|open|staffed|manned)\s*(?:on\s*)?[^|.]{0,80}?\d{1,2}[:.]\d{2}\s*(?:am|pm)?\s*(?:-|–|—|to|until)\s*\d{1,2}[:.]\d{2}\s*(?:am|pm)?", re.I)
def strip_phone_hours(t): return PHONE_HOURS.sub(" ", t or "")
def card_check(ot, texts, item, today=None, source_url=None):
    """Trussell centre-card pages (/emergency-food/i-have-a-food-voucher): read THIS centre's own card, matched by postcode
    or centre name (scripts/trussell_times.match), never a bag of times from the whole page. None = not a card page."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import trussell_times as TT
    cards = []
    for t in texts: cards += TT.parse_cards(t)
    if not cards: return None
    card, how = TT.match(item, cards)
    if card and how == "name" and "/" not in str(item.get("id", "/")):
        # a whole-food-bank entry may only borrow a card by name when it is that food bank's own card
        # ('Harrow Foodbank' must not take 'South Harrow Baptist Church', nor 'Thurrock' take 'Little Thurrock')
        strip = lambda s: TT.norm(re.sub(r"(?i)\(.*?\)|\bthe\b|foodbank|food bank|distribution centre|centre", "", s or ""))
        if strip(card["name"]) != strip(item.get("name")): card, how = None, "no card with this food bank's own name or postcode"
    if not card: return "unconfirmed", None, "centre card not found on own site (" + how + ")"
    new = TT.to_ot(card, source_url or (ot or {}).get("source_url"), today or datetime.date.today().isoformat())
    if not new: return "unconfirmed", None, "own centre card shows no sessions"
    old = ot if isinstance(ot, dict) else {}
    if old.get("structured") == new.get("structured") and (new.get("structured") or old.get("raw") == new.get("raw")):
        return "confirmed", ot, "matches this centre's own card (" + how + ")"
    return "changed", new, "this centre's own card now shows different times (" + how + ")"
COLLECT_ROLE = re.compile(r"collect your (?:food )?parcel|collection only|collect a parcel", re.I)
DELIVERY_ROLE = re.compile(r"delivery only|not open to the public", re.I)
DONATION_ROLE = re.compile(r"\b(?:donat(?:e|ion|ions)|warehouse|drop[- ]?off)\b", re.I)
def _same_url(a, b):
    """Ignore scheme, www, and a trailing slash. Query strings are not part of the source identity.
    Too loose for an opening-times check: use source_page_ok for that."""
    if not a or not b: return False
    def n(u):
        p = urllib.parse.urlparse(u)
        return (host(u), urllib.parse.unquote(p.path or "").rstrip("/").lower())
    return n(a) == n(b)
_CACHE_MARK = ("webcache", "archive.org", "googleusercontent", "bingj.com", "cdn-cgi", "cachedview", "/amp", "web.archive")
def source_page_ok(wanted, landed):
    """True only when `landed` is the source URL the listing shows.
    http→https, a leading www, and one trailing slash are the same page. A different host, path, or query
    is a different page. A cache, archive, amp, or cdn-cgi copy is not the live page."""
    if not wanted or not landed: return False
    def bits(u):
        p = urllib.parse.urlsplit((u or "").strip())
        h = (p.hostname or "").lower()
        if h.startswith("www."): h = h[4:]
        path = urllib.parse.unquote(p.path or "").rstrip("/").lower()
        q = tuple(sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True)))
        return (p.scheme or "").lower(), h, path, q, (p.query or "").lower()
    try: ws, wh, wp, wq, _wqs = bits(wanted); ls, lh, lp, lq, lqs = bits(landed)
    except Exception: return False
    if not wh or not lh or ws not in ("http", "https") or ls not in ("http", "https"): return False
    blob = " ".join((lh, lp, lqs))
    if any(mark in blob for mark in _CACHE_MARK): return False
    if any(k.lower() in ("cache", "cached") for k, _ in lq): return False
    return wh == lh and wp == lp and wq == lq
def live_hours_ok(table, text, postcode):
    """(ok, quote). ok only when every open day recorded in `table` is listed in this postcode's block
    and every clock time recorded there is written on that block, and every open day the block lists is
    in the table (a Monday–Friday range counts as each day in the range). quote is a short slice copied
    from `text`. Anything else is not confirmed."""
    import rule27_formats as R27
    lay = R27.read_centre(text or "", postcode)
    if lay is not None:   # a recognised layout decides on its own; its quote is copied from the cleaned page text
        if not lay.get("structured") or not isinstance(table, dict) or lay.get("unclear_days"): return False, ""
        rec = {d: [list(p) for p in v] for d, v in table.items() if v}
        return (rec == lay["structured"], lay["quote"] if rec == lay["structured"] else "")
    text = R27.clean(text or "")   # office/phone days are NOT dropped here: a day the page lists must be accounted for
    block = postcode_block(text or "", postcode)
    if block is None or not isinstance(table, dict): return False, ""
    from times import _days, DAYS, _range
    recorded = {d for d, slots in table.items() if slots}
    if not recorded: return False, ""
    spans = list(TIMESPAN.finditer(block))
    if not spans: return False, ""
    page_days, endpoints = set(), set()
    split = re.compile(r"\s*(?:-|–|—|\bto\b|\buntil\b|\btill\b)\s*", re.I)
    for m in spans:
        idxs = _days(m.group(1).lower())
        if idxs is None: return False, ""
        for i in idxs: page_days.add(DAYS[i])
        parts = split.split(m.group(2).strip(), maxsplit=1)
        if len(parts) != 2: return False, ""
        rng = _range(parts[0], parts[1])
        if not rng: return False, ""
        endpoints.update(rng)
    if page_days != recorded: return False, ""
    for slots in table.values():
        for pair in slots or []:
            if len(pair) != 2 or pair[0] not in endpoints or pair[1] not in endpoints: return False, ""
    base = (text or "").find(block)
    if base < 0: base = 0
    at = base + spans[0].start()
    quote = (text or "")[max(0, at - 60):at + 180].strip()
    if not quote or quote not in (text or ""): return False, ""
    return True, quote
def page_has_complete_times(text, postcode):
    """True when the plain text already shows one timetable and every day and time in it is on the page.
    A page that fails this may still be drawing the times with a script, so the reader renders it."""
    ext = extract_times(text, postcode)
    if not ext or ext.get("status") != "TIMES_FOUND" or not ext.get("structured"): return False
    table = {k: v for k, v in ext["structured"].items() if v}
    ok, quote = live_hours_ok(table, text, postcode)
    return bool(ok and quote and quote in (text or ""))
def render_live(url):
    """Render the live URL in a headless browser and wait for load. No cache and no saved page.
    The final URL is the address the browser landed on. If the browser cannot run, this is a failed
    open, not a static-HTML fallback."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "http": None, "final_url": url, "html": "", "error": "headless browser unavailable"}
    exe = os.environ.get("CHROME_PATH") or ("/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None)
    try:
        with sync_playwright() as p:
            kw = {"headless": True, "args": ["--no-sandbox", "--disable-gpu"]}
            if exe: kw["executable_path"] = exe
            browser = p.chromium.launch(**kw)
            try:
                page = browser.new_page(user_agent="Mozilla/5.0 (helpmap.uk times reader; hello@helpmap.uk)")
                resp = page.goto(url, wait_until="load", timeout=20000)
                page.wait_for_timeout(1000)
                status = resp.status if resp else 0
                return {"ok": status == 200 and bool(page.content()), "http": status, "final_url": page.url, "html": page.content()}
            finally:
                browser.close()
    except Exception as e:
        return {"ok": False, "http": None, "final_url": url, "html": "", "error": str(e)[:160]}
def centre_role(text, postcode):
    """What the words nearest this postcode say the address is: collection, delivery, donation, or None.
    Uses the first time the postcode appears (Chichester lists collection at PO19 8ET, then the warehouse
    at the same postcode further down). The nearest phrase wins, so a later 'Delivery only' for the next
    centre is not read onto this one."""
    pc = norm_pc(postcode)
    if not text or not pc: return None
    hits = [m for m in PC_RE.finditer(text.upper()) if m.group(1) + m.group(2) == pc]
    if not hits: return None
    m = hits[0]
    pre = text[max(0, m.start() - 240):m.start()]
    post = text[m.end():m.end() + 220]
    cands = []
    for rx, role in ((COLLECT_ROLE, "collection"), (DELIVERY_ROLE, "delivery"), (DONATION_ROLE, "donation")):
        for hit in rx.finditer(pre): cands.append((m.start() - hit.end(), role))
        for hit in rx.finditer(post): cands.append((hit.start() + 1, role))
    if not cands: return None
    cands.sort(key=lambda x: x[0])
    return cands[0][1]
def shown_table(ot):
    """Open-day table the card actually prints, or None when it does not print one (text-only, warehouse, missing)."""
    if isinstance(ot, dict) and ot.get("status") == "TIMES_FOUND" and isinstance(ot.get("structured"), dict):
        return {k: v for k, v in ot["structured"].items() if v}
    return None
def hours_match(published, new):
    """True when the card already shows this timetable. Text-only cards do not match a day table."""
    if not isinstance(new, dict) or new.get("status") != "TIMES_FOUND" or not new.get("structured"): return False
    table = shown_table(published)
    if table is not None:
        return json.dumps(table, sort_keys=True) == json.dumps({k: v for k, v in new["structured"].items() if v}, sort_keys=True)
    if isinstance(published, dict) and "status" not in published and published:
        got = hours_from_ot(new) or {}
        def n(h): return {str(k)[:3].lower(): re.sub(r"\s+", "", str(v)) for k, v in h.items() if v}
        return n(got) == n(published)
    return False
def _timed_readings(pairs, postcode):
    """Per page (never joined: joining mashes two centres into one string). TIMES_FOUND readings, plus any TEXT_ONLY."""
    found, messy = [], False
    for u, t in pairs:
        e = extract_times(t, postcode)
        if e and e.get("status") == "TIMES_FOUND" and e.get("structured"):
            e = dict(e, centre_role=centre_role(t, postcode), _page_text=t)
            if u: e["_source_url"] = u
            found.append(e)
        elif e and e.get("status") == "TIMES_TEXT_ONLY":
            messy = True
    return found, messy
def confirm_times(ot, texts, postcode=None, pages=None, source_url=None):
    """-> (status, new_ot, reason).
    status: confirmed | changed | differs_review | unconfirmed | none_published.
    Compares the open days on the card with a per-postcode re-read of the source page. Finding the published
    clock times somewhere on the page is not confirmation: a Friday-only card used to stay confirmed while the
    same page also listed Monday and Wednesday."""
    pairs = [(u, strip_phone_hours(t)) for u, t in (list(pages) if pages is not None else [(None, t) for t in (texts or [])])]
    def decide(found, messy, from_source):
        sigs = {}
        for e in found: sigs.setdefault(json.dumps(e["structured"], sort_keys=True), e)
        if len(sigs) > 1:
            return "differs_review", None, "source pages disagree on this postcode's opening times"
        if len(sigs) == 1:
            new = next(iter(sigs.values()))
            role = new.get("centre_role")
            if role == "delivery":
                return "differs_review", None, "source says delivery only or not open to the public; shown hours left unchanged"
            if role == "donation":
                return "differs_review", None, "nearest heading is donation or warehouse hours, not collection; shown hours left unchanged"
            table = {k: v for k, v in new["structured"].items() if v}
            ok, quote = live_hours_ok(table, new.get("_page_text") or "", postcode)
            if not ok:
                return "differs_review", None, "recorded days or times could not be confirmed on the live source page; shown hours left unchanged"
            if hours_match(ot, new):
                return "confirmed", {"_evidence": quote}, "shown hours match this postcode on the source page"
            if role == "collection": new = dict(new, collection=True)
            new = dict(new, _evidence=quote)
            return "changed", new, "shown hours differ from this postcode on the source page"
        if from_source and messy:
            return "differs_review", None, "source page lists hours that do not parse to one timetable; shown hours left unchanged"
        return None
    if source_url:
        # Only the URL the card shows. A redirect, another path, or a cached copy is not that page,
        # and a different page on the same site is not used to fill the gap.
        src_pairs = [(u, t) for u, t in pairs if u and source_page_ok(source_url, u)]
        if not src_pairs:
            return "differs_review", None, "source url redirected to a different page, domain or cached copy; shown hours left unchanged"
        found, messy = _timed_readings(src_pairs, postcode)
        decided = decide(found, messy, True)
        if decided: return decided
        return "differs_review", None, "source page did not confirm a day table; shown hours left unchanged"
    found, messy = _timed_readings(pairs, postcode)
    decided = decide(found, messy, False)
    if decided: return decided
    alltext = " ".join(t for _, t in pairs)
    low = alltext.lower()
    want, days = want_times(ot)
    if not want:
        new = extract_times(alltext, postcode)
        return ("changed", new, "times found on own site") if new and new.get("status") == "TIMES_FOUND" else ("none_published", None, "no times published or found")
    got = norm_times(alltext)
    days_ok = all(re.search(r"\b" + d, low) for d in days)
    # No per-postcode timetable could be read. Only then fall back to "the published clock times occur on the page".
    # This cannot confirm a shorter week: that case is handled above whenever a timetable was read.
    # A subset of the stored clock times somewhere on the page is not confirmation: the open days were not accounted for.
    if want <= got and days_ok:
        return "differs_review", None, "published clock times occur on the page but the day table could not be confirmed; shown hours left unchanged"
    return "unconfirmed", None, "published times not found on own site this run"
def hours_from_ot(ot):
    """times.normalise structured table -> shelter/warm-space hours dict, Mon..Sun, closed days included."""
    if not ot: return None
    order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if ot.get("all_closed"): return {d: "Closed" for d in order}
    if not ot.get("structured") and not ot.get("closed"): return None
    notes = ot.get("notes") or {}
    out = {}
    for d, r in (ot.get("structured") or {}).items():
        cell = " / ".join("%s - %s" % (a, b) for a, b in r)
        if notes.get(d): cell += " " + notes[d]
        out[d[:3].title()] = cell
    for d in ot.get("closed") or []:
        out.setdefault(d[:3].title(), "Closed")
    return {d: out[d] for d in order if d in out} or None

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
def client_week(ot):
    """A real open/close table. Empty, missing, or all-closed is not one: the stored week stays."""
    if not isinstance(ot, dict) or ot.get("all_closed"): return False
    st = ot.get("structured") or {}
    for rows in st.values():
        for span in rows or []:
            if isinstance(span, (list, tuple)) and len(span) >= 2 and span[0] and span[1] and span[0] != span[1]: return True
    return False
def read_listing_source(src, fetcher, render, postcode):
    """Open the exact source URL live. Render only when the plain HTML has no complete day/time set.
    Returns (final_url, text) or (None, reason). A redirect's body is discarded and never used as hours."""
    r = fetcher(src) or {}
    landed = r.get("final_url") or ""
    html = r.get("html") or ""
    if r.get("http") != 200 or not html:
        return None, "live source page could not be opened; shown hours left unchanged"
    if not source_page_ok(src, landed):
        return None, "source url redirected to a different page (%s); shown hours left unchanged" % landed
    text = text_of(html)
    if page_has_complete_times(text, postcode):
        return landed, text
    got = (render or render_live)(src) or {}
    rland = got.get("final_url") or ""
    rhtml = got.get("html") or ""
    if not rhtml or not (got.get("ok") or got.get("http") == 200):
        return landed, text
    if not source_page_ok(src, rland):
        return None, "rendered page redirected to a different page (%s); shown hours left unchanged" % rland
    return rland, got.get("text") or text_of(rhtml)
def cross_check_times(items, kind, field, fetcher=fetch_live, today=None, threads=24, render=None, seen=None):
    """Re-read every entry's times from the live site this run; mutates items. Returns {id: result} log.
    kind 'fb': field 'opening_times' (times.py dict). kind 'sh'/'ws': field 'hours' (dict or text).
    fetcher defaults to fetch_live (Rule 27): a saved page, including the per-run fetch cache, is never consulted.
    When a listing has source_url, only that URL is read. A redirect is not confirmed. Plain HTML with no
    complete timetable is rendered once. If the live page does not open, the card is flagged and its hours
    are left unchanged.
    Food banks: pass `seen` (id -> last run's pending table, from logs/foodbank_times_check.json). A clear table is
    written only when the postcode matched and the same table was already pending. The first sight is stored and
    the listing is not touched. A missing, unreadable, empty or all-closed reading never replaces the stored week."""
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
            src = (i.get(field) or {}).get("source_url") if kind == "fb" and isinstance(i.get(field), dict) else None
            rec = {"site": s, "http": home and home.get("http"), "sha256": home and home.get("sha256"),
                   "etag": home and home.get("etag"), "last_modified": home and home.get("last_modified"), "checked": today}
            hand = kind == "fb" and isinstance(i.get(field), dict) and str(i[field].get("reader") or "").startswith("hand-reviewed")
            def flag_kept(reason):
                # Protected hand-checked times are never overwritten. A page that cannot be confirmed
                # is the same flag as a page that disagrees (Dean, 23 Oct 23:37), not a generic review.
                if hand:
                    rec.update(status="differs_from_hand_checked", reason="own site now reads differently from the hand-checked times; kept, flagged for Dean")
                    i["times_status"] = "confirmed_by_hand"; i["times_checked"] = today
                else:
                    rec.update(status="differs_review", reason=reason)
                    i["times_status"] = "differs_review"; i["times_reason"] = reason; i["times_checked"] = today
                log[i["id"]] = rec
            if src:
                if not usable_site(src):
                    flag_kept("source url is not a live page; shown hours left unchanged"); continue
                landed, payload = read_listing_source(src, fetcher, render, i.get("postcode"))
                if not landed:
                    flag_kept(payload); continue
                page_pairs, texts = [(landed, payload)], [payload]
            else:
                page_pairs = [(u, t) for u, t in pages if not DONATION_PAGE.search(urllib.parse.urlparse(u).path)]   # never read client times from a giving/donation page
                texts = [t for _, t in page_pairs]
            if not src and (not s or not home or home.get("http") != 200 or not texts):
                rec.update(status="unreachable" if s else "no_website", reason="own site unreachable this run" if s else "no own website to check against")
                _unconfirm(i, kind, field, rec["reason"]); log[i["id"]] = rec; continue
            if not src and home and host(home["final_url"]) != host(s) and not host(home["final_url"]).endswith("." + host(s)) and not host(s).endswith("." + host(home["final_url"])):
                rec.update(status="unconfirmed", reason="own site redirects to a different site")
                _unconfirm(i, kind, field, rec["reason"]); log[i["id"]] = rec; continue
            ev = None
            for t in texts:
                ev = closure.detect(t, i.get("postcode"))
                if ev: break
            if ev: rec.update(status="closed", reason="own site says closed", evidence=ev); i["_own_site_closed"] = ev; log[i["id"]] = rec; continue
            i["_orig_times"] = i.get(field)
            cc = card_check(i.get(field), texts, i, today, src) if kind == "fb" else None
            st, new, why = cc or confirm_times(i.get(field) if kind == "fb" else i.get(field), texts, i.get("postcode"), pages=page_pairs, source_url=src if kind == "fb" else None)
            rec.update(status=st, reason=why)
            if st == "confirmed":
                if isinstance(new, dict): rec["evidence"] = new.get("_evidence") or ""
                i["times_status"] = "confirmed"; i["times_checked"] = today
                if kind == "fb" and isinstance(i.get(field), dict): i[field] = dict(i[field], checked_date=today)  # re-checked OK on own site: card date advances even when times unchanged (Dean, 23 Oct 10:39)
            elif st == "changed" and str((i.get(field) or {}).get("reader", "") if isinstance(i.get(field), dict) else "").startswith("hand-reviewed"):
                # Protected hand-checked times (Dean, 23 Oct 23:37): never overwritten by the robots, only flagged for review
                rec.update(status="differs_from_hand_checked", reason="own site now reads differently from the hand-checked times; kept, flagged for Dean",
                           new=new.get("structured") if isinstance(new, dict) else None)
                i["times_status"] = "confirmed_by_hand"; i["times_checked"] = today
            elif st == "changed":
                if kind == "fb" and isinstance(new, dict):
                    src_u = new.pop("_source_url", None); new.pop("centre_role", None); new.pop("_page_text", None)
                    rec["evidence"] = new.pop("_evidence", None) or ""
                    new = dict(new, checked_date=today, source_url=src_u or src or (home and home.get("final_url")) or "")
                    if not new.get("reader"): new["reader"] = "source_page"
                    if not client_week(new) or office_like(new.get("structured")):
                        rec.update(status="unconfirmed", reason="empty, closed or unreadable reading; stored week kept")
                        _unconfirm(i, kind, field, rec["reason"])
                    elif seen is None:
                        # Callers that do not pass last run's pending table keep the previous one-run write.
                        rec["undo"] = json.loads(json.dumps(i.get(field)))
                        i[field] = new
                        i["times_status"] = "updated"; i["times_checked"] = today; rec["new"] = new.get("structured")
                    else:
                        pc = norm_pc(i.get("postcode")); fp = new.get("structured")
                        prev = seen.get(i["id"]) or {}
                        if pc and prev.get("postcode") == pc and prev.get("structured") == fp:
                            rec["undo"] = json.loads(json.dumps(i.get(field)))
                            i[field] = new
                            i["times_status"] = "updated"; i["times_checked"] = today
                            rec["new"] = fp; rec["status"] = "changed"
                        else:
                            rec.update(status="seen_once", new=fp, pending={"structured": fp, "raw": new.get("raw"), "postcode": pc, "source_url": new.get("source_url")})
                elif kind == "fb":
                    rec.update(status="unconfirmed", reason="empty, closed or unreadable reading; stored week kept")
                    _unconfirm(i, kind, field, rec["reason"])
                else:
                    i[field] = hours_from_ot(new) or i.get(field)
                    i["times_status"] = "updated"; i["times_checked"] = today; rec["new"] = new.get("structured") if isinstance(new, dict) else None
            elif st == "differs_review":
                # The source page was re-read and does not agree with the card (or is not one walk-in timetable). Flag it; keep the hours.
                if hand:
                    rec.update(status="differs_from_hand_checked", reason="own site now reads differently from the hand-checked times; kept, flagged for Dean")
                    i["times_status"] = "confirmed_by_hand"; i["times_checked"] = today
                else:
                    i["times_status"] = "differs_review"; i["times_reason"] = why; i["times_checked"] = today; rec["flagged"] = True
            elif st == "unconfirmed":
                _unconfirm(i, kind, field, why)
            log[i["id"]] = rec
    if kind == "fb":
        orig = {i["id"]: i.get("_orig_times") for i in items}
        bysite = {}
        for i in items:
            if log.get(i["id"], {}).get("status") in ("changed", "seen_once"): bysite.setdefault((log[i["id"]]["site"], json.dumps(log[i["id"]].get("new"), sort_keys=True)), []).append(i)
        for (site, _), grp in bysite.items():
            for i in grp:
                why = None
                if office_like(log[i["id"]].get("new")): why = "new own-site times look like office/centre hours"
                elif len(grp) > 1 and len({norm_pc(x.get("postcode")) for x in grp}) < len(grp): why = "own site gives one table for several branches; cannot tell which branch"
                if why:
                    if log[i["id"]].get("status") == "changed": i["opening_times"] = orig.get(i["id"])
                    log[i["id"]].update(status="unconfirmed", reason=why, reverted=True); log[i["id"]].pop("pending", None); log[i["id"]].pop("undo", None)
                    _unconfirm(i, kind, field, why)
        hold_boilerplate(items, log, orig, field)
        for i in items: i.pop("_orig_times", None)
    return log
BOILER = re.compile(r"phone lines?|telephone|lines (?:are )?monitored|office hours|office (?:is )?open", re.I)
def _key(ot):
    if not isinstance(ot, dict): return None
    return json.dumps(ot.get("structured"), sort_keys=True) if ot.get("structured") else (ot.get("raw") or None)
def hold_boilerplate(items, log, orig, field="opening_times"):
    """Shared boilerplate is a red flag (Cardiff, 27 Oct 2026: phone-line hours on every centre). Hold for review, never
    auto-apply or auto-confirm: (a) every session/location of one food bank (2+, same site) ends with identical times;
    (b) the times' own text mentions phone lines / office hours."""
    live = [i for i in items if log.get(i["id"], {}).get("status") in ("confirmed", "changed")]
    bysite = {}
    for i in live:
        if "/" in i["id"]: bysite.setdefault(log[i["id"]]["site"], []).append(i)
    for site, grp in bysite.items():
        allsess = [i for i in items if "/" in i["id"] and log.get(i["id"], {}).get("site") == site]
        keys = {_key(i.get(field)) for i in grp}
        if len(grp) >= 2 and len(grp) == len(allsess) and len(keys) == 1 and None not in keys:
            for i in grp: _hold(i, log, orig, field, "every session of this food bank shows the same times (shared boilerplate?); held for review")
    for i in live:
        ot = i.get(field)
        if log[i["id"]].get("status") in ("confirmed", "changed") and isinstance(ot, dict) and BOILER.search(ot.get("raw") or ""):
            _hold(i, log, orig, field, "times text mentions phone lines / office hours; held for review")
def _hold(i, log, orig, field, why):
    i[field] = orig.get(i["id"]); log[i["id"]].update(status="held_for_review", reason=why, reverted=True)
    _unconfirm(i, "fb", field, why); i["times_status"] = "held_for_review"

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

GOV = re.compile(r"(\.gov\.uk|\.gov\.wales|\.gov\.scot|nidirect\.gov\.uk)$")
def pre_flags(c, kind):
    """'100% categorically' rules (Dean, 21 Oct 2026). A discovered candidate is never auto-added when:
    * its only source is OpenStreetMap: OSM finds go to the flagged list and need a human-checked own-site record
      in overrides/<layer>_verified.json or _unverified.json before they can appear;
    * the directory's 'website' is a council page, not the place's own site (it cannot confirm this place);
    * (shelters) the name says foyer / supported housing / day centre, which are not emergency shelters."""
    f = []
    if str(c.get("id", "")).startswith("osm-") or (c.get("source") == "OpenStreetMap" and not c.get("directory")):
        f.append("OpenStreetMap-only: needs verification on the place's own site before it can be added")
    n = (c.get("name") or "").lower()
    if GOV.search(host(c.get("website"))) and not re.search(r"council|borough|county|city of", n):
        f.append("directory link is a council page, not the place's own site")
    if kind == "sh" and re.search(r"\bfoyer\b|supported housing|day centre", n):
        f.append("name says foyer / supported housing / day centre, not an emergency shelter")
    return f
def discover_layer(cands, existing, kind, run_day, unverified, log_path, fetcher=fetch_raw, threads=24, geocoder=None):
    """Shelters / warm spaces: dedupe directory candidates against what we already have, own-site check the rest.
    Passing candidates are added to `unverified` (tier 2, 'Unverified - call before you go', sign_url = own site),
    so the verification gate and recheck.py re-fetch and re-confirm them on every run like any other entry.
    Returns (new_candidates_to_append_to_fresh, log)."""
    import discovery_rules as DR
    cands = [dict(c) for c in cands]
    for c in cands:  # keep the directory's own pin so the area check can compare it with the postcode
        if c.get("lat") is not None and c.get("src_lat") is None: c["src_lat"], c["src_lng"] = c["lat"], c["lng"]
        c.setdefault("source_live", bool(c.get("directory") or c.get("directory_url")))  # record came from a directory fetched this run
    try: G = (geocoder or geocode)([c["postcode"] for c in cands if c.get("postcode")])
    except Exception: G = {}
    geo = {norm_pc(k): v for k, v in G.items()}
    for c in cands:
        if c.get("lat") is None and norm_pc(c.get("postcode")) in geo: c["lat"], c["lng"] = geo[norm_pc(c["postcode"])]
    new, dup = dedupe(cands, existing)
    log = {"run": run_day, "candidates": len(cands), "already_on_map": dup, "new": len(new), "added": [], "flagged": [], "rejected": []}
    def one(c):
        if c.get("lat") is None: return c, {"result": "flag", "reasons": ["no postcode/coordinates in directory, cannot pin without guessing"]}, ("queue", ["no valid postcode"])
        pre = pre_flags(c, kind)
        if DR.held(c): r = {"result": "flag", "reasons": []}
        else: r = own_site_check(c, kind, fetcher)
        if pre: r = dict(r, result="flag", reasons=pre + r.get("reasons", []))
        dec = DR.assess(c, r, geo, run_day)
        return c, r, dec
    with cf.ThreadPoolExecutor(threads) as ex: res = list(ex.map(one, new))
    add_cap = int(os.environ.get("DISCOVERY_MAX_NEW", "150"))  # fail-safe: a flood of adds in one run means a source changed - hold them all
    if sum(1 for x in res if x[2][0] == "add") > add_cap:
        res = [(c, r, ("queue", ["held: more than %d new in one run (source may have changed)" % add_cap]) if d[0] == "add" else d) for c, r, d in res]
    add = []
    for c, r, (decision, why) in res:
        ev = {k: r.get(k) for k in ("url", "final_url", "http", "sha256", "etag", "last_modified")}
        if decision == "reject":
            log["rejected"].append({"id": c["id"], "name": c["name"], "postcode": c.get("postcode"), "website": c.get("website"),
                                    "directory": c.get("directory"), "directory_url": c.get("directory_url"), "reasons": why}); continue
        if decision == "add":
            r = dict(r, final_url=r.get("final_url") or c.get("directory_url") or c.get("source_url"))
            if not r.get("final_url"): decision, why = "queue", ["no working source page to cite"]
        if decision == "add":
            c = {k: v for k, v in c.items() if k not in ("src_lat", "src_lng")}
            DR.apply_dates(c, run_day)
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
                                   "directory": c.get("directory"), "directory_url": c.get("directory_url"), "reasons": why or r["reasons"], **ev})
    json.dump(log, open(log_path, "w"), indent=1, ensure_ascii=False)
    DR.record({"sh": "shelters", "ws": "warmspaces", "fb": "foodbanks"}[kind], run_day,
              [dict(a, upcoming=next((x.get("upcoming") for x in add if x["id"] == a["id"]), False),
                    scheme_start=next((x.get("scheme_start") for x in add if x["id"] == a["id"]), ""),
                    referral_only=next((bool(x.get("referral", "").startswith("Referral only")) for x in add if x["id"] == a["id"]), False)) for a in log["added"]],
              log["flagged"], log["rejected"], source=os.path.basename(log_path),
              root=None if not os.path.isabs(log_path) else os.path.dirname(os.path.dirname(log_path)) if os.path.basename(os.path.dirname(log_path)) == "logs" else os.path.dirname(log_path))
    return add, log
