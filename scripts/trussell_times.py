"""Trussell food bank sites (*.foodbank.org.uk) moved to a new template in 2026: the centre list is at
/emergency-food/i-have-a-food-voucher (paged ?page=N), one card per distribution centre:
  <name> Part of <X> Foodbank ... <address> <POSTCODE> Get directions ... Collection times  [Open/Closed today]
  Monday-Tuesday Closed  Wednesday 10:30 am to 12:30 pm ... Delivery times ...
The old reader looked for a /locations/ table (now a redirect or 404), so these centres got no times.
This module reads the cards. Conservative: times are taken only from the card whose postcode matches the
entry (or, if no postcode match, an exact name match); fortnightly/monthly/alternate wording is kept
'as written' (TIMES_TEXT_ONLY), never turned into a weekly table."""
import re, html, time, urllib.request, urllib.parse, ssl, datetime
PATH = "/emergency-food/i-have-a-food-voucher"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?) ?(\d[A-Z]{2})\b")
T = r"\d{1,2}(?::\d{2})? ?[ap]m"
# A day spec is one day, a hyphen range (Monday-Tuesday), or a list (Monday, Wednesday and Friday / & / &amp;).
# The list must stop before the clock time: "Monday 2:00 pm to 4:00 pm and Wednesday 9:30 am to 11:30 am"
# is two rows, not one dayspec. The old pattern kept only the last day of a list, so
# "Monday, Wednesday and Friday 2:00 pm to 4:00 pm" became Friday alone (Chichester, 26 Oct).
_DAY = "(?:" + "|".join(DAYS) + ")"
_SEP = r"(?:\s*(?:,|&(?:amp;)?|\band\b|-)\s*)"
ROW = re.compile(r"\b(" + _DAY + "(?:" + _SEP + _DAY + r")*)\s+(Closed|" + T + r" to " + T + r"(?:\s*(?:,|and|&(?:amp;)?)\s*" + T + r" to " + T + r")*)", re.I)
def expand_days(spec):
    """'Friday' / 'Tuesday-Wednesday' / 'Monday, Wednesday and Friday' -> ['monday', ...] or None."""
    parts = re.split(r"\s*(?:,|&(?:amp;)?|\band\b)\s*", (spec or "").strip(), flags=re.I)
    out = []
    for p in parts:
        m = re.fullmatch(r"(" + _DAY + r")(?:\s*-\s*(" + _DAY + r"))?", p.strip(), re.I)
        if not m: return None
        a = m.group(1).lower(); b = (m.group(2) or a).lower()
        i, j = DAYS.index(a), DAYS.index(b)
        if j < i: return None
        for d in DAYS[i:j + 1]:
            if d not in out: out.append(d)
    return out or None
def _label(days):
    idxs = [DAYS.index(d) for d in days]
    if len(days) > 1 and idxs == list(range(idxs[0], idxs[-1] + 1)):
        return days[0].title() + "-" + days[-1].title()
    return ", ".join(d.title() for d in days)
IRREG = re.compile(r"fortnight|monthly|alternate|every other|1st|2nd|3rd|4th|first|second|third|last (mon|tue|wed|thu|fri|sat|sun)", re.I)
def text_of(h):
    h = re.sub(r"(?is)<(script|style|svg).*?</\1>", " ", h or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
def _24(s):
    m = re.match(r"(\d{1,2})(?::(\d{2}))? ?([ap]m)", s.strip(), re.I); h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    return f"{h:02d}:{mi:02d}"
def parse_cards(text):
    """-> [{'name','postcode','rows':[(['monday','wednesday','friday'],'Closed'|'10:30 am to 12:30 pm')], 'raw', 'irregular'}]"""
    cards = []
    chunks = re.split(r"\bGet directions\b", text)
    for i in range(len(chunks) - 1):
        head = chunks[i]
        # card header = last '<name> Part of ' in this chunk
        hs = list(re.finditer(r"([^|]{3,90}?) Part of [^0-9@]{3,80}?(?:Foodbank|Food Bank|food bank)", head))
        if not hs: continue
        name = re.split(r"(?:results See map Close|Closed|\d [ap]m|[.!:]|challenges)\s+", " " + hs[-1].group(1))[-1].strip()
        pcs = PC.findall(head[hs[-1].end():].upper())
        if not pcs: continue
        body = chunks[i + 1]
        m = re.search(r"Collection times(.*?)(?:Delivery times|Part of [^0-9]{3,80}?(?:Foodbank|Food Bank)|See more information|$)", body, re.S)
        if not m: continue
        seg = re.sub(r"(Open today until " + T + r"|Closed today|Opens? (?:today|tomorrow) at " + T + ")", " ", m.group(1), flags=re.I)
        rows = []
        for spec, v in ROW.findall(seg):
            days = expand_days(spec)
            if days: rows.append((days, v))
        # placeholder rows such as '12:00 am to 12:00 am' (appointment-only centres) are not opening times
        rows = [r for r in rows if r[1].lower() == "closed" or all(_24(x) != _24(y) for x, y in re.findall("(" + T + ") to (" + T + ")", r[1], re.I))]
        if not rows and not re.search(r"appointment", name, re.I): continue
        raw = "; ".join(f"{_label(days)} {v}" for days, v in rows if v.lower() != "closed")
        cards.append({"name": name, "postcode": pcs[-1][0] + " " + pcs[-1][1], "rows": rows, "raw": raw,
                      "irregular": bool(IRREG.search(name + " " + seg))})
    return cards
def to_ot(card, source_url, run_day):
    if not card["raw"]:
        if re.search(r"appointment", card["name"], re.I):
            return {"status": "TIMES_TEXT_ONLY", "raw": "By appointment only (own site)", "structured": None, "source_url": source_url, "checked_date": run_day, "reader": "trussell_cards"}
        return None  # every day 'Closed' = no published sessions; leave for review
    if card["irregular"]:
        return {"status": "TIMES_TEXT_ONLY", "raw": card["raw"] + (" (" + re.search(r"\(([^)]*)\)", card["name"]).group(1) + ")" if "(" in card["name"] else ""),
                "structured": None, "source_url": source_url, "checked_date": run_day, "reader": "trussell_cards"}
    st = {}
    for days, v in card["rows"]:
        if v.lower() == "closed": continue
        rng = [[_24(x), _24(y)] for x, y in re.findall("(" + T + ") to (" + T + ")", v, re.I)]
        for d in days: st.setdefault(d[:3], []).extend(rng)
    return {"status": "TIMES_FOUND", "structured": {d: st[d] for d in [x[:3] for x in DAYS] if d in st}, "raw": card["raw"],
            "source_url": source_url, "checked_date": run_day, "reader": "trussell_cards"}
CTX = ssl.create_default_context()
def fetch(url, tries=3):
    for k in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (helpmap.uk times reader; hello@helpmap.uk)"}), timeout=25, context=CTX)
            return r.status, r.geturl(), r.read(4_000_000).decode("utf8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410, 403): return e.code, url, ""
        except Exception: pass
        time.sleep(2 * 2 ** k)  # backoff 2s, 4s, 8s
    return None, url, ""
def site_cards(base, fetcher=fetch, maxpages=12, delay=1.0):
    base = base.rstrip("/"); out, seen = [], set()
    for p in range(1, maxpages + 1):
        u = base + PATH + (f"?page={p}" if p > 1 else "")
        code, final, h = fetcher(u)
        if code != 200 or not h: break
        cs = [c for c in parse_cards(text_of(h)) if (c["name"], c["postcode"]) not in seen]
        if not cs: break
        for c in cs: seen.add((c["name"], c["postcode"])); c["url"] = final; out.append(c)
        if f"page={p + 1}" not in h: break
        time.sleep(delay)
    return out
def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def match(item, cards):
    pc = norm(item.get("postcode"))
    hit = [c for c in cards if norm(c["postcode"]) == pc]
    if len(hit) == 1: return hit[0], "postcode"
    pool = hit or cards
    nm = norm(re.sub(r"(?i)foodbank|food bank|distribution centre|centre", "", item.get("name", "")))
    byname = [c for c in pool if nm and (nm in norm(c["name"]) or norm(re.sub(r"(?i)\(.*?\)|distribution centre|centre", "", c["name"])) in nm)]
    if len(byname) == 1: return byname[0], "postcode+name" if hit else "name"
    return None, ("several centres share this postcode" if len(hit) > 1 else "no card for this postcode/name")
