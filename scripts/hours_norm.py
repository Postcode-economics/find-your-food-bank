"""Stored opening-times normaliser for ALL layers (owner, 21 Oct 2026). Runs inside every 3x-daily build, after the
own-site times check, so the data written to data.js / shelters.js / warmspaces.js is always:
  * a day table in Mon..Sun order (food banks: structured {mon..sun: [[HH:MM, HH:MM]]}; shelters / warm spaces:
    {"Mon": "HH:MM - HH:MM[ / ...][ Monthly|Fortnightly]"} or "24 hours");
  * OSM-style raw text ('Mo-We,Fr 20:00-21:30', 'Mo-Su 17:00-10:00', '24/7') converted into that day table;
  * anything that cannot be laid out by day ('Fortnightly', 'only when severe weather provision is open') kept as the
    place's own wording, once, whitespace-cleaned and de-duplicated. Never guessed."""
import re, json
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LOW = [d.lower() for d in DAYS]
OSM = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
ALL_DAY = "24 hours"
def _day_key(k):
    k3 = str(k).strip()[:3].lower()
    return DAYS[LOW.index(k3)] if k3 in LOW else None
def _span(a, b):
    def hm(t):
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", t.strip())
        if not m or int(m.group(1)) > 24 or int(m.group(2)) > 59: return None
        return int(m.group(1)), int(m.group(2))
    x, y = hm(a), hm(b)
    if not x or not y or x == y: return None
    if y == (24, 0): y = (23, 59)
    if x[0] == 24: return None
    return f"{x[0]:02d}:{x[1]:02d} - {y[0]:02d}:{y[1]:02d}"
def osm_to_table(s):
    """OSM opening_hours -> {'Mon': 'HH:MM - HH:MM', ...} in Mon..Sun order, or None if any part is not understood."""
    s = re.sub(r"\s+", " ", (s or "").strip()).rstrip(";")
    if not s: return None
    if s in ("24/7", "Mo-Su 00:00-24:00", "Mo-Su 00:00-23:59"): return {d: ALL_DAY for d in DAYS}
    out = {}
    for rule in [r.strip() for r in s.split(";") if r.strip()]:
        m = re.fullmatch(r"((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)\s+(off|closed|\d{1,2}:\d{2}-\d{1,2}:\d{2}(?:,\d{1,2}:\d{2}-\d{1,2}:\d{2})*)", rule)
        if not m: return None
        days = []
        for part in m.group(1).split(","):
            a, _, b = part.partition("-")
            i, j = OSM[a.lower()], OSM[(b or a).lower()]
            days += list(range(i, j + 1)) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
        if m.group(2) in ("off", "closed"):
            for d in days: out.pop(DAYS[d], None)
            continue
        spans = [_span(*t.split("-")) for t in m.group(2).split(",")]
        if None in spans: return None
        for d in days: out[DAYS[d]] = " / ".join(spans)  # later OSM rules override earlier ones (OSM semantics)
    return order(out) if out else None
def order(h):
    """dict with any day spelling -> Mon..Sun ordered dict with 3-letter keys. Unknown keys -> None (caller keeps text)."""
    if not isinstance(h, dict): return h
    out = {}
    for k, v in h.items():
        d = _day_key(k)
        if d is None: return None
        out[d] = v
    return {d: out[d] for d in DAYS if d in out}
def clean_text(s):
    parts, seen = [], set()
    for p in re.split(r"\s*[|\n]\s*", str(s or "")):
        p = re.sub(r"\s+", " ", p).strip(" ;,")
        k = re.sub(r"[^a-z0-9]", "", p.lower())
        if p and k not in seen: seen.add(k); parts.append(p)
    return "; ".join(parts)
def normalise_hours(h):
    """Shelter / warm-space `hours`: dict -> ordered dict; OSM string -> ordered dict; other text -> cleaned text once."""
    if h in (None, "", {}): return h
    if isinstance(h, dict):
        o = order(h)
        return o if o is not None else clean_text(" | ".join(f"{k} {v}" for k, v in h.items()))
    t = osm_to_table(str(h))
    if t: return t
    return clean_text(h)
def normalise_fb(ot):
    """Food bank opening_times: structured -> mon..sun order; text lines de-duplicated and cleaned."""
    if not isinstance(ot, dict): return ot
    ot = dict(ot)
    if isinstance(ot.get("structured"), dict):
        s = {str(k)[:3].lower(): v for k, v in ot["structured"].items()}
        ot["structured"] = {d: sorted(s[d]) for d in LOW if d in s}
    if ot.get("lines"):
        seen, lines = set(), []
        for l in ot["lines"]:
            l = re.sub(r"\s+", " ", str(l)).strip(" ;,"); k = re.sub(r"[^a-z0-9]", "", l.lower())
            if l and k not in seen: seen.add(k); lines.append(l)
        ot["lines"] = lines
    return ot
def apply(items, field):
    """Normalise every item in place; returns number changed."""
    n = 0
    for x in items:
        old = x.get(field)
        new = normalise_fb(old) if field == "opening_times" else normalise_hours(old)
        if json.dumps(new) != json.dumps(old): n += 1  # order-sensitive: key order is what the map shows
        x[field] = new
    return n
