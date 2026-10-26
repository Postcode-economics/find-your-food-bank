"""Own-site closure check for food bank pins (owner, 21 Oct 2026). The food bank's OWN site beats Give Food.
Each refresh fetches every pin's own website (home page plus a few same-site location/contact pages). A pin is omitted only
when the text block that holds THAT pin's postcode clearly says it has closed (e.g. "CLOSED 27TH AUGUST 2026",
"permanently closed", "no longer operating"), with any stated date already passed. Routine wording ("Wed Closed",
"closed on bank holidays", "temporarily closed", "closed for Christmas") never counts. Unreachable sites change nothing.
Manual confirmations live in overrides/foodbank_closed.json. Omitted pins are logged to logs/foodbank_closed.json and
kept there for 30 days as the 'recently closed' list."""
import re, os, sys, json, html, ssl, datetime, urllib.request, urllib.parse, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # owner 25 Oct 2026
CTX = ssl._create_unverified_context()
PC_ANY = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b")
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
DATE = r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d\d)"
CLOSED = re.compile(r"(permanently closed|closed permanently|closed down|has (?:now )?closed|have (?:now )?closed|is now closed|now closed|no longer (?:operating|open|running|operational)|ceased (?:operating|trading)|will be closing|closed (?:on |from |as of )?" + DATE + r"|closing (?:on |from )?" + DATE + ")", re.I)
NOT = re.compile(r"(exceptionally|between|december|temporar\w*|bank holiday|christmas|easter|new year|half[- ]term|summer|for the holiday|until further|weather|today|this week)", re.I)
def text_of(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
def _date(m):
    g = [x for x in m.groups() if x]
    for i in range(len(g) - 2):
        if g[i].isdigit() and g[i + 1].lower() in MONTHS and g[i + 2].isdigit():
            try: return datetime.date(int(g[i + 2]), MONTHS[g[i + 1].lower()], int(g[i]))
            except ValueError: return None
    return None
def detect(text, postcode, today=None):
    """Return the quoted evidence if the block of `text` holding `postcode` says the place has closed, else None."""
    today = today or datetime.date.today()
    pc = (postcode or "").upper().replace(" ", "")
    if len(pc) < 5: return None
    up = text.upper(); spans = [(m.start(), m.end(), m.group(0).replace(" ", "")) for m in PC_ANY.finditer(up)]
    for k, (s, e, p) in enumerate(spans):
        if p != pc: continue
        a = spans[k - 1][1] if k else max(0, s - 400); b = spans[k + 1][0] if k + 1 < len(spans) else min(len(text), e + 200)
        a = max(a, s - 400); b = min(b, e + 200)  # this pin's own block only
        tail = text[e:b]; cut = re.search(r"directions|opening times|get directions|address", tail, re.I)
        if cut: b = e + cut.start()                # the next location's block starts here
        head = text[a:s]; starts = [m.end() for m in re.finditer(r"directions via google maps|get directions", head, re.I)]
        if starts: a = a + starts[-1]              # ... and the previous one ended here
        blk = text[a:b]
        for m in CLOSED.finditer(blk):
            ctx = blk[max(0, m.start() - 60):m.end() + 60]
            if NOT.search(ctx): continue
            d = _date(m)
            if d and d > today: continue           # announced for the future: not closed yet
            if m.group(0).lower().startswith(("will be closing", "closing")) and not d: continue
            return blk.strip()[:400]
    return None
def fetch(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (FindYourFoodBank closure check)"}), timeout=20, context=CTX)
        return r.geturl(), r.read(1_500_000).decode("utf8", "ignore")
    except Exception: return u, ""
LINK = re.compile(r"locat|contact|find|get-?help|visit|open|centre|where|need|news", re.I)
def site_pages(site, fetcher=fetch, maxpages=6):
    base, h = fetcher(site); pages = [(base, h)]
    if not h: return pages
    links = []
    for m in re.findall(r'href="([^"#]+)"', h):
        u = urllib.parse.urljoin(base, m)
        if LINK.search(m) and urllib.parse.urlparse(u).netloc == urllib.parse.urlparse(base).netloc and u not in links: links.append(u)
    if "foodbank.org.uk" in base: links.insert(0, urllib.parse.urljoin(base, "/locations/"))
    for u in links[:maxpages]: pages.append(fetcher(u))
    return pages
def check_all(items, fetcher=fetch, today=None, threads=16):
    """Fetch each distinct own website once; return {pin id: {"url", "evidence"}} for pins whose own site says closed."""
    sites = {}
    for i in items:
        s = (i.get("website") or "").strip()
        if s.startswith("http") and "facebook.com" not in s and "salvationarmy.org.uk" not in s: sites.setdefault(s, []).append(i)
    def one(s):
        out = {}
        pages = [(u, text_of(h)) for u, h in site_pages(s, fetcher) if h]
        for i in sites[s]:
            for u, t in pages:
                ev = detect(t, i.get("postcode"), today)
                if ev: out[i["id"]] = {"url": u, "evidence": ev}; break
        return out
    res = {}
    with cf.ThreadPoolExecutor(threads) as ex:
        for o in ex.map(one, list(sites)): res.update(o)
    return res
def apply(items, root, today=None, fetcher=fetch, auto=True):
    """Omit closed pins (manual list + own-site detections), log them, keep the 30-day recently-closed list. Returns removed ids."""
    today = today or datetime.date.today()
    mp = os.path.join(root, "overrides", "foodbank_closed.json")
    raw = json.load(open(mp)) if os.path.exists(mp) else {}
    man = {k: v for k, v in raw.items() if not k.startswith("_")}
    hold = set(raw.get("_hold_for_review", []))   # detected closed but awaiting owner: logged, not removed
    found = check_all(items, fetcher, today) if auto else {}
    lp = os.path.join(root, "logs", "foodbank_closed.json")
    log = json.load(open(lp)) if os.path.exists(lp) else {"recently_closed": []}
    keep = [r for r in log.get("recently_closed", []) if (today - datetime.date.fromisoformat(r["closed_on"])).days <= 30]
    seen = {r["id"] for r in keep}; gone = []; held = []
    for i in items:
        hit = man.get(i["id"]) or found.get(i["id"])
        if not hit: continue
        if i["id"] not in man and not RULES["remove_confirmed_closures"]:  # owner 25 Oct 2026: never auto-removed; pin kept with note, listed for owner
            i["notice"] = RULES["closure_card_note"]
            held.append({"id": i["id"], "name": i["name"], "url": hit.get("url"), "evidence": hit.get("evidence"), "why": "auto-detected closure - kept with note, awaiting owner"}); continue
        if i["id"] not in man and i["id"] in hold:
            held.append({"id": i["id"], "name": i["name"], "url": hit.get("url"), "evidence": hit.get("evidence")}); continue
        gone.append(i["id"])
        if i["id"] not in seen:
            keep.append({"id": i["id"], "name": i["name"], "address": i.get("address"), "postcode": i.get("postcode"), "closed_on": today.isoformat(),
                         "source": "manual (own site)" if i["id"] in man else "own site", "url": hit.get("url"), "evidence": hit.get("evidence")})
    items[:] = [i for i in items if i["id"] not in set(gone)]
    log = {"checked": today.isoformat(), "recently_closed": keep, "removed_this_run": gone, "held_for_review": held}
    json.dump(log, open(lp, "w"), indent=1, ensure_ascii=False)
    return gone
