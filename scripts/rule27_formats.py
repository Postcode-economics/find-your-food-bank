"""Rule 27 page formats (Dean, 26 Oct 2026). Reads one centre's collection timetable from a live page's text.

Layouts it recognises (detected per page, never guessed):
  trussell_new  - 2026 Trussell cards: '<name> Part of X Foodbank ... <POSTCODE> Get directions ... Collection times
                  Monday-Tuesday Closed Wednesday 10:30 am to 12:30 pm ... Delivery times ...'. Times come AFTER the postcode.
  trussell_old  - /locations tab table: '<name> Opening times Mon Closed Tue 10:00 - 12:00 ... Address ... <POSTCODE>
                  Directions via Google Maps'. Times come BEFORE the address.
  columns       - all day labels first, then all values ('Monday: Tuesday: ... 10:00am - 4:00pm Closed ...').
  prose         - anything else: the existing discover.extract_times reader, after clean().
Excluded: phone/office/donation/church-service hours, delivery-time blocks, end <= start, 12:00am-12:00am placeholders.
read_centre() -> None (layout not recognised: caller falls back to prose), or a dict:
  {layout, structured {mon:[[HH:MM,HH:MM]]}, raw, quote, unclear_days {day: why}} or {layout, unclear: why}."""
import re
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FULL = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?) ?(\d[A-Z]{2})\b")
DAYW = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|weds|thu(?:rs?(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
T = r"\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?"
NOT_CLIENT = re.compile(r"phone ?lines?|telephone|phone answered|helpline|call us|office|manned|monitored|donat|drop[- ]?off|warehouse|volunteer"
                        r"|\bservices?\b|worship|\bmass\b|sunday school|caf[eé]", re.I)

def clean(text):
    """Whitespace incl. non-breaking spaces, '12 noon', 'between 12pm and 2pm', '10-12am', 'except bank holidays'."""
    t = (text or "").replace("&amp;", "&").replace("&nbsp;", " ")
    t = re.sub(r"[\u00a0\u202f\u2007\u200b\s]+", " ", t)
    t = re.sub(r"(?i)a\.m\.?", "am", t); t = re.sub(r"(?i)p\.m\.?", "pm", t)
    t = re.sub(r"(?i)\b12(?:[:.]00)?\s*(?:noon|midday)\b", "12pm", t)
    t = re.sub(r"(?i)\b(?:noon|midday)\b", "12pm", t)
    t = re.sub(r"(?i)\bbetween\s+(" + T + r")\s+and\s+(" + T + r")", r"\1 - \2", t)
    t = re.sub(r"(?i)\b(\d{1,2}(?:[:.]\d{2})?)\s*(-|–|—|to)\s*12(?:[:.]00)?\s*am\b",
               lambda m: (m.group(1) + "am " + m.group(2) + " 12pm") if int(re.split(r"[:.]", m.group(1))[0]) < 12 else m.group(0), t)
    t = re.sub(r"(?i)\b(" + DAYW + r")(s?)\s+(?:from|at)\s+(?=\d)", r"\1\2 ", t)
    t = re.sub(r"(?i)\(?\s*(?:except|not open on|closed on)\s+(?:all\s+)?bank holidays?\s*\)?", " ", t)
    return re.sub(r" +", " ", t).strip()

def to24(s):
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", s.strip().lower())
    if not m: return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h > 23 or mi > 59: return None
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    return h * 60 + mi, ap

def rng(a, b):
    """('10:30 am','12:30 pm') -> ['10:30','12:30'], or None when invalid: end <= start, 00:00 start, 12am-12am."""
    x, y = to24(a), to24(b)
    if not x or not y: return None
    (s, ap1), (e, ap2) = x, y
    if ap1 is None and ap2 == "pm" and s < 12 * 60 and s + 12 * 60 < e: s += 12 * 60
    if s == 0 or e == 0 or e <= s or s < 5 * 60: return None
    return ["%02d:%02d" % divmod(s, 60), "%02d:%02d" % divmod(e, 60)]

def day_span(spec):
    """'Monday-Wednesday' / 'Tue' / 'Mon & Fri' / 'Tuesday, Friday' -> ['mon', ...] or None."""
    out = []
    for part in re.split(r"\s*(?:,|&|\band\b)\s*", spec.strip().lower()):
        m = re.fullmatch(r"(" + DAYW + r")s?\.?(?:\s*(?:-|–|to)\s*(" + DAYW + r")s?\.?)?", part.strip())
        if not m: return None
        i, j = DAYS.index(m.group(1)[:3]), DAYS.index((m.group(2) or m.group(1))[:3])
        if j < i: return None
        out += [d for d in DAYS[i:j + 1] if d not in out]
    return out or None

def _pc_hits(t, pc):
    n = (pc or "").upper().replace(" ", "")
    return [m for m in PC.finditer(t.upper()) if m.group(1) + m.group(2) == n]

def _table(rows):
    st = {}
    for days, r in rows:
        for d in days: st.setdefault(d, []).append(r)
    return {d: st[d] for d in DAYS if d in st}

def trussell_new(t, pc):
    if "Collection times" not in t and "Delivery times" not in t: return None
    hits = [m for m in _pc_hits(t, pc) if t[m.end():m.end() + 40].strip().startswith("Get directions")]
    if not hits:
        return {"layout": "trussell_new", "unclear": "no card for this postcode"} if "Get directions" in t else None
    if len(hits) > 1: return {"layout": "trussell_new", "unclear": "several cards share this postcode"}
    m = hits[0]
    end = re.search(r"\bPart of [^0-9]{3,80}?(?:Foodbank|Food Bank)|See more information", t[m.end():])
    card = t[m.end(): m.end() + (end.start() if end else 1500)]
    # the next card's name sits just before 'Part of': cut back to the last 'Closed'/time row
    head = card[:200]
    if "Collection times" not in card:
        if re.search(r"Delivery only", head, re.I): return {"layout": "trussell_new", "unclear": "delivery only, no collection times"}
        return {"layout": "trussell_new", "unclear": "no collection times on this card"}
    seg = card[card.index("Collection times") + len("Collection times"):]
    seg = re.split(r"Delivery times", seg)[0]
    seg = re.sub(r"(?i)Open today until " + T + r"|Closed today|Opens? (?:today|tomorrow|on \w+) at " + T, " ", seg)
    RX = re.compile(r"\b(" + DAYW + r"(?:\s*(?:,|&|\band\b|-)\s*" + DAYW + r")*)\s+(Closed|" + T + r" to " + T + r"(?:\s*(?:,|and|&)\s*" + T + r" to " + T + r")*)", re.I)
    rows, seen, quote = [], set(), []
    for dm in RX.finditer(seg):
        days = day_span(dm.group(1))
        if not days: return {"layout": "trussell_new", "unclear": "unreadable day %r" % dm.group(1)}
        if any(d in seen for d in days): break  # the next card's table began
        seen.update(days); quote.append(dm.group(0))
        if dm.group(2).lower() == "closed": continue
        for a, b in re.findall("(" + T + ") to (" + T + ")", dm.group(2), re.I):
            r = rng(a, b)
            if not r: return {"layout": "trussell_new", "unclear": "invalid time %s to %s" % (a, b)}
            rows.append((days, r))
    if not quote: return {"layout": "trussell_new", "unclear": "collection times block has no rows"}
    if not rows: return {"layout": "trussell_new", "unclear": "every day Closed (no published sessions)"}
    return {"layout": "trussell_new", "structured": _table(rows), "raw": "; ".join(quote), "quote": " ".join(quote), "unclear_days": {}}

OLD_ROW = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Closed|\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})", re.I)
def trussell_old(t, pc):
    if not re.search(r"Opening times\s+Mon\s+(?:Closed|\d)", t): return None
    blocks = re.split(r"Report a map error|Directions via Google Maps", t)
    found = []
    for b in blocks:
        if "Opening times" not in b or "Address" not in b: continue
        oi, ai = b.index("Opening times"), b.rindex("Address")
        if oi > ai: continue  # times must come before the address in this layout
        if not _pc_hits(b[ai:], pc): continue
        found.append(b)
    if not found: return {"layout": "trussell_old", "unclear": "no table whose address has this postcode"}
    if len(found) > 1: return {"layout": "trussell_old", "unclear": "several tables share this postcode"}
    b = found[0]; seg = b[b.index("Opening times"):b.rindex("Address")]
    rows, quote, seen = [], [], set()
    for m in OLD_ROW.finditer(seg):
        d = m.group(1).lower()
        if d in seen: return {"layout": "trussell_old", "unclear": "day listed twice"}
        seen.add(d); quote.append(m.group(0))
        if m.group(2).lower() == "closed": continue
        a, c = re.split(r"\s*-\s*", m.group(2))
        r = rng(a, c)
        if not r: return {"layout": "trussell_old", "unclear": "invalid time %s" % m.group(2)}
        rows.append(([d], r))
    if len(seen) != 7: return {"layout": "trussell_old", "unclear": "table does not list all 7 days"}
    if not rows: return {"layout": "trussell_old", "unclear": "every day Closed"}
    return {"layout": "trussell_old", "structured": _table(rows), "raw": "; ".join(quote), "quote": " ".join(quote), "unclear_days": {}}

VAL = r"(Closed|" + T + r"\s*(?:-|–|to)\s*" + T + r"|" + T + r"(?:\s*\([^)]{1,40}\))?)"
def columns(t, pc):
    m = re.search(r"((?:\b(?:" + "|".join(FULL) + r"):\s*){3,7})", t, re.I)
    if not m: return None
    labels = re.findall(r"(" + "|".join(FULL) + r"):", m.group(1), re.I)
    vals = []; rest = t[m.end():]
    for _ in labels:
        v = re.match(r"\s*" + VAL, rest, re.I)
        if not v: return {"layout": "columns", "unclear": "values do not line up with the day labels"}
        vals.append(v.group(1)); rest = rest[v.end():]
    if len({a + b for a, b in PC.findall(t.upper())}) > 1 and not _pc_hits(t[max(0, m.start() - 400):m.end() + 400], pc):
        return {"layout": "columns", "unclear": "several postcodes on the page; table not tied to this one"}
    if not _pc_hits(t, pc): return {"layout": "columns", "unclear": "postcode not on the page"}
    rows, unclear = [], {}
    for lab, v in zip(labels, vals):
        d = lab[:3].lower()
        if v.lower() == "closed": continue
        p = re.split(r"\s*(?:-|–|to)\s*", v, maxsplit=1)
        r = rng(p[0], p[1]) if len(p) == 2 and not re.search(r"\(", v) else None
        if r: rows.append(([d], r))
        else: unclear[d] = "no end time or not a session: %r" % v
    quote = t[m.start():m.end() + (len(t) - m.end() - len(rest))]
    if not rows: return {"layout": "columns", "unclear": "no complete session", "unclear_days": unclear}
    return {"layout": "columns", "structured": _table(rows), "raw": quote, "quote": quote, "unclear_days": unclear}

SPLIT = re.compile(r"(" + T + r")\s*(?:-|–|to)\s*(" + T + r")\s*\((" + DAYW + r"(?:\s*(?:&|,|and|-)\s*" + DAYW + r")*)\)", re.I)
def split_rows(t, pc):
    """'Tuesday, Friday 12pm - 2.00pm (Tues) 11.00am -1.00pm (Fri)': each range carries its own day(s)."""
    hits = _pc_hits(t, pc)
    if not hits or not SPLIT.search(t): return None
    m = hits[0]
    nxt = [x.start() for x in PC.finditer(t.upper()) if x.start() > m.end()]
    seg = t[m.end(): min(nxt) if nxt else m.end() + 400]
    ms = list(SPLIT.finditer(seg))
    if not ms: return None
    rows, quote = [], []
    for x in ms:
        days, r = day_span(x.group(3)), rng(x.group(1), x.group(2))
        if not days or not r: return {"layout": "split_rows", "unclear": "unreadable row %r" % x.group(0)}
        rows.append((days, r)); quote.append(x.group(0))
    head = seg[:ms[0].start()]
    listed = day_span(re.sub(r"[^A-Za-z,& -]", " ", head).strip(" ,")) if head.strip() else None
    got = {d for ds, _ in rows for d in ds}
    if listed and set(listed) != got: return {"layout": "split_rows", "unclear": "days listed %s but rows cover %s" % (listed, sorted(got))}
    return {"layout": "split_rows", "structured": _table(rows), "raw": seg[:ms[-1].end()].strip(), "quote": seg[:ms[-1].end()].strip(), "unclear_days": {}}

def read_centre(text, postcode):
    t = clean(text)
    for f in (trussell_new, trussell_old, columns, split_rows):
        r = f(t, postcode)
        if r is not None: return r
    return None

def drop_non_client(t):
    """Remove sentences that give phone/office/donation/service hours, so the prose reader never sees them."""
    parts = re.split(r"(?<=[.!?])\s+|\s+(?=(?:Our|The) (?:phone|office|centre phone))", t)
    return " ".join(p for p in parts if not (NOT_CLIENT.search(p) and re.search(T + r"\s*(?:-|–|to|until)\s*" + T, p, re.I)))
