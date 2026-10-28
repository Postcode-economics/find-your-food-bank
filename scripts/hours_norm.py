"""Stored opening-times normaliser for ALL layers (Dean, 21 Oct 2026). Runs inside every 3x-daily build, after the
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

# --- unambiguous day tables (Dean, 26 Oct 2026) ---
# Convert free text to Mon..Sun ONLY when every day and every clock time is written in the source.
# Never infer a missing am/pm. Anything unclear stays as the place's own words.
FB_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_WORD = (r"mon(?:day)?s?|tues(?:day)?s?|tue|wed(?:nesday)?s?|thurs(?:day)?s?|thu|"
            r"fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?")
_AP = r"a\.?m\.?|p\.?m\.?"
CLOCK = (r"(?:\d{1,2}(?::\d{2}|\.\d{2})\s*(?:" + _AP + r")|\d{1,2}\s*(?:" + _AP +
         r")|midday|noon|midnight|\d{1,2}:\d{2}\s*noon|\d{1,2}:\d{2})")
_DASH = r"\s*(?:-|–|—|to|until|till|til|and|&)\s*"
_RANGE = r"(?P<a>" + CLOCK + r")" + _DASH + r"(?P<b>" + CLOCK + r")"
_RANGE2 = r"(?P<c>" + CLOCK + r")" + _DASH + r"(?P<d>" + CLOCK + r")"
_DAYGROUP = r"(?:" + DAY_WORD + r")(?:\s*(?:,|&|/|\band\b|\bor\b|to|-|–|—)\s*(?:" + DAY_WORD + r"))*"
# Words that may sit between a day and its time ('between the hours of', 'currently only open on').
# 'and' is not here: 'Wednesday and 9am' is not a range.
_LEAD = (r"from|between|the|hours|hour|of|morning|afternoon|evening|currently|only|session|sessions|"
         r"our|operates|operate|operating|runs|run|available|open|is|are|on|a|an|foodbank|food|bank|just|each|every|we|at")
_CHUNK = re.compile(
    r"(?P<days>" + _DAYGROUP + r")(?:[\s:,.\-–—]+|\b(?:" + _LEAD + r")\b)+(?P<body>closed|(?:" +
    _RANGE + r")(?:\s*(?:,|and|&)\s*" + _RANGE2 + r")?)", re.I)
_CLOSED_RX = re.compile(r"\b(" + _DAYGROUP + r")\s*:?\s*closed\b", re.I)
_OPEN_RX = re.compile(r"\b(" + _DAYGROUP + r")\s*:?\s*(?:(?:from|between)\s+)?(?:" + CLOCK + r")", re.I)
_FILL = re.compile(r"[\s,;:|.\-–—()/’']+|\b(?:from|the|open|opening|times|time|on|between|each|every|are|is|we|hours|"
                   r"at|our|a|an|foodbank|food|bank|weekly|week|of|for|hold|holds|held|morning|afternoon|evening|"
                   r"currently|only|session|sessions|operates|operate|operating|runs|run|available|just|and)\b", re.I)
_HARD = re.compile(r"\b(?:month|fortnight|alternat\w*|except|unless|appoint\w*|term|holiday|donation|referral|referred|"
                   r"young|aged|centre|center|hub)\b|\*|–\s*–|—\s*—|-\s*-|\bonly\s+when\b|"
                   r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.I)
_NOTE_BAD = re.compile(r"term|except|appoint|holiday|month|fortnight|alternat|only\s+when|weather|referral", re.I)

def _day_i(word):
    w = word.lower()
    for i, pfx in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
        if w.startswith(pfx): return i
    return None

def expand_days(spec):
    """'Mon to Wed' / 'Tue, Thu, Mon' -> day indexes, or None if the list is not only day names."""
    spec = re.sub(r"[’']s\b", "", spec.lower())
    rx = re.compile(r"(" + DAY_WORD + r")|(-|–|—|\bto\b|\bthrough\b|\bthru\b)|(,|&|/|\band\b|\bor\b)|(\S+)", re.I)
    out, pend = [], False
    for m in rx.finditer(spec):
        word, dash, sep, junk = m.groups()
        if junk: return None
        if word:
            i = _day_i(word)
            if i is None: return None
            if pend:
                if not out or i <= out[-1]: return None
                out += list(range(out[-1] + 1, i + 1)); pend = False
            else: out.append(i)
        elif dash:
            if pend or not out: return None
            pend = True
    return out if out and not pend else None

def _mins(tok):
    """A clock written in the source -> minutes, or None. No am/pm is not guessed."""
    t = tok.lower().replace("a.m.", "am").replace("p.m.", "pm").replace(" ", "")
    t = re.sub(r"noon$", "", t)
    if t in ("midday", "noon", ""): return 12 * 60
    if t == "midnight": return 0
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(am|pm)", t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if h > 12 or h == 0 or mi > 59: return None
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        return h * 60 + mi
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59: return None
        return h * 60 + mi
    return None

def _pair(a, b):
    s, e = _mins(a), _mins(b)
    if s is None or e is None or s == e: return None
    if e < s:
        if s < 12 * 60: return None  # '10am-12am' is not a clear same-day range
        return ["%02d:%02d" % divmod(s, 60), "%02d:%02d" % divmod(e, 60)]
    if e - s > 16 * 60: return None
    return ["%02d:%02d" % divmod(s, 60), "%02d:%02d" % divmod(e, 60)]

def _overlap(spans):
    spans = sorted(spans)
    return any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1))

def _dirty(gap):
    return bool(_FILL.sub("", gap or ""))

def _pull_notes(s):
    notes = []
    def paren(m):
        t = m.group(1).strip()
        if re.fullmatch(r"monthly", t, re.I): notes.append("Monthly")
        elif re.fullmatch(r"fortnightly", t, re.I): notes.append("Fortnightly")
        else: notes.append(t)
        return " "
    s = re.sub(r"\(([^)]*)\)", paren, s)
    for m in re.finditer(r"\b(monthly|fortnightly)\b", s, re.I):
        notes.append("Monthly" if m.group(1).lower() == "monthly" else "Fortnightly")
    s = re.sub(r"\b(?:monthly|fortnightly)\b", " ", s, flags=re.I)
    return s, notes

def _note_text(notes):
    bits = []
    for n in notes:
        if n in ("Monthly", "Fortnightly"): bits.append(n)
        elif n: bits.append("(" + n.strip("()") + ")")
    return " ".join(bits)

def parse_segment(seg):
    """One '|' piece -> {day: [[HH:MM,HH:MM], ...] or []} and a note, or None."""
    seg, notes = _pull_notes(seg)
    if any(n not in ("Monthly", "Fortnightly") and (_NOTE_BAD.search(n or "") or re.search(r"\d|\bam\b|\bpm\b", n or "", re.I)) for n in notes): return None
    if _HARD.search(seg): return None
    res, pos = {}, 0
    for m in _CHUNK.finditer(seg):
        if _dirty(seg[pos:m.start()]): return None
        pos = m.end()
        days = expand_days(m.group("days"))
        if not days: return None
        body = m.group("body") or ""
        if body.lower() == "closed":
            rng = []
        else:
            r1 = _pair(m.group("a"), m.group("b"))
            if not r1: return None
            rng = [r1]
            if m.group("c"):
                r2 = _pair(m.group("c"), m.group("d"))
                if not r2: return None
                rng.append(r2)
            if _overlap(rng): return None
        for i in days:
            d = FB_DAYS[i]
            if d not in res: res[d] = rng
            elif res[d] == rng: continue
            elif res[d] and rng and not _overlap(res[d] + rng):
                res[d] = sorted(res[d] + [r for r in rng if r not in res[d]])
            else: return None
    if pos == 0 or _dirty(seg[pos:]): return None
    return res, _note_text(notes)

def _segments(raw):
    """Every '|' piece, in order, duplicates dropped. Nothing is thrown away for being a café or an address:
    if any piece is not a plain day and time, the whole record stays as written."""
    out, seen = [], set()
    for p in re.split(r"\s*\|\s*", raw or ""):
        p = re.sub(r"\s+", " ", p).strip(" ;,")
        k = re.sub(r"[^a-z0-9]", "", p.lower())
        if p and k not in seen:
            seen.add(k); out.append(p)
    return out

def try_convert(text):
    """Free text -> {'structured','closed','notes'} or (None, reason). Times are copied, never invented."""
    raw = str(text or "").strip()
    if not raw: return None, "no times are written"
    if _HARD.search(raw) and not re.search(r"\b(?:monthly|fortnightly)\b", raw, re.I):
        return None, _hard_reason(raw)
    segs = _segments(raw)
    if not segs: return None, "no times are written"
    parsed = []
    for seg in segs:
        # monthly/fortnightly inside a segment is a note, so the hard-word check runs after notes are lifted
        p = parse_segment(seg)
        parsed.append(p)
    if any(p is None for p in parsed):
        if _HARD.search(_pull_notes(raw)[0]): return None, _hard_reason(raw)
        if any(p is not None for p in parsed): return None, "part of the wording is not a clear day and time"
        return None, "the wording is not a clear day and time"
    merged, notes = {}, {}
    for res, note in parsed:
        for d, rng in res.items():
            if d not in merged: merged[d] = rng
            elif merged[d] == rng: pass
            elif merged[d] and rng and not _overlap(merged[d] + rng):
                merged[d] = sorted(merged[d] + [r for r in rng if r not in merged[d]])
            elif not merged[d] or not rng: return None, "a day is both open and closed"
            else: return None, "different times are given for the same day"
        if note:
            for d, rng in res.items():
                if rng and d not in notes: notes[d] = note
                elif rng and notes.get(d) not in (None, note): return None, "two different notes for the same day"
    structured = {d: merged[d] for d in FB_DAYS if merged.get(d)}
    closed = [d for d in FB_DAYS if d in merged and not merged[d]]
    if not structured:
        if len(closed) == 7: return {"structured": {}, "closed": closed, "notes": {}, "all_closed": True}, None
        return None, "every listed day says closed and no opening time is written"
    return {"structured": structured, "closed": closed, "notes": notes}, None

def _hard_reason(raw):
    s = raw.lower()
    if re.search(r"\b(?:month|fortnight|alternat|term)\b", s): return "the hours only apply some weeks (monthly, term-time or similar)"
    if re.search(r"\b(?:appoint|except|unless|only when|referral|donation)\b", s): return "the hours depend on something else (an appointment, an exception or a referral)"
    if re.search(r"\b[a-z]{1,2}\d[a-z\d]?\s?\d[a-z]{2}\b", s): return "an address is mixed in with the times"
    if re.search(r"[–—-]\s*[–—-]", raw): return "a blank or broken time is in the text"
    if "*" in raw: return "a star or footnote is attached to the time"
    if re.search(r"\b(?:centre|center|hub|young|aged|holiday)\b", s): return "the wording mixes the time with other details"
    return "the wording is not a clear day and time"

def scan_closed(raw, structured):
    """Days the source explicitly marks closed, ignoring days it also gives a time for."""
    if not raw or not isinstance(raw, str): return []
    closed, opened = set(), set(structured or {})
    for m in _CLOSED_RX.finditer(raw):
        days = expand_days(m.group(1))
        if days: closed.update(FB_DAYS[i] for i in days)
    for m in _OPEN_RX.finditer(raw):
        days = expand_days(m.group(1))
        if days: opened.update(FB_DAYS[i] for i in days)
    return [d for d in FB_DAYS if d in closed and d not in opened]

def closed_days_for(ot):
    """Explicit closed days for a timetable we already publish. Empty when the source never says closed."""
    if not isinstance(ot, dict) or ot.get("all_closed"): return []
    st = ot.get("structured") or {}
    raw = ot.get("raw") if isinstance(ot.get("raw"), str) else ""
    conv, _ = try_convert(raw) if raw else (None, None)
    if conv and not conv.get("all_closed") and conv.get("structured") == {d: st[d] for d in FB_DAYS if d in st}:
        return [d for d in conv.get("closed") or [] if d not in st]
    return scan_closed(raw, st)

def _cell(val):
    """One shelter/warm-space cell -> 'HH:MM - HH:MM[ / ...][ Monthly|(note)]' or 'Closed' or '24 hours'."""
    v = str(val or "").strip()
    if re.fullmatch(r"24 hours", v, re.I): return "24 hours"
    if re.fullmatch(r"closed", v, re.I): return "Closed"
    v, notes = _pull_notes(v)
    if any(n not in ("Monthly", "Fortnightly") and (_NOTE_BAD.search(n or "") or re.search(r"\d|\bam\b|\bpm\b", n or "", re.I)) for n in notes): return None
    if _HARD.search(v): return None
    parts = [p for p in re.split(r"\s*/\s*", v) if p.strip()]
    spans = []
    for p in parts:
        m = re.fullmatch(r"\s*(?P<a>" + CLOCK + r")" + _DASH + r"(?P<b>" + CLOCK + r")\s*", p, re.I)
        if not m: return None
        pr = _pair(m.group("a"), m.group("b"))
        if not pr: return None
        spans.append(pr)
    if not spans or _overlap(spans): return None
    note = _note_text(notes)
    return " / ".join("%s - %s" % (a, b) for a, b in spans) + ((" " + note) if note else "")

def convert_day_dict(h):
    """{'Monday': '8:45am to 9:30am (Parents Group)'} -> {'Mon': '08:45 - 09:30 (Parents Group)'} or None."""
    if not isinstance(h, dict) or not h: return None
    out = {}
    for k, v in h.items():
        d = _day_key(k)
        if d is None: return None
        cell = _cell(v)
        if cell is None: return None
        if d in out and out[d] != cell: return None
        out[d] = cell
    return {d: out[d] for d in DAYS if d in out}

def struct_to_hours(conv):
    """Food-bank structured result -> shelter/warm-space hours dict, Mon..Sun, closed days included."""
    if not conv: return None
    if conv.get("all_closed"): return {d: "Closed" for d in DAYS}
    out = {}
    for d, spans in (conv.get("structured") or {}).items():
        key = d[:3].title()
        cell = " / ".join("%s - %s" % (a, b) for a, b in spans)
        note = (conv.get("notes") or {}).get(d)
        out[key] = cell + ((" " + note) if note else "")
    for d in conv.get("closed") or []:
        out.setdefault(d[:3].title(), "Closed")
    return {d: out[d] for d in DAYS if d in out} or None

def _am_pm_or_fullname(v):
    return bool(re.search(r"\d\s*(?:a\.?m\.?|p\.?m\.?)\b|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tues|weds|thurs)\b", str(v), re.I))
def normalise_hours(h):
    """Shelter / warm-space hours. A day table only when every day and time is unambiguous; otherwise the place's own words."""
    if h in (None, "", {}): return h
    if isinstance(h, dict):
        conv = convert_day_dict(h)
        if conv: return conv
        if any(_am_pm_or_fullname(v) for v in h.values()):
            return clean_text(" | ".join("%s %s" % (k, v) for k, v in h.items()))
        o = order(h)
        return o if o is not None else clean_text(" | ".join("%s %s" % (k, v) for k, v in h.items()))
    conv, _ = try_convert(h)
    table = struct_to_hours(conv) if conv and (conv.get("structured") or conv.get("all_closed")) else None
    if table: return table
    t = osm_to_table(str(h))
    if t: return t
    return clean_text(h)
def normalise_fb(ot):
    """Food bank opening_times: day order, explicit closed days, and free text converted only when it is unambiguous."""
    if not isinstance(ot, dict): return ot
    ot = dict(ot)
    if isinstance(ot.get("structured"), dict):
        s = {str(k)[:3].lower(): v for k, v in ot["structured"].items()}
        ot["structured"] = {d: sorted(v) for d, v in ((d, s[d]) for d in LOW if d in s) if v}
    raw = ot.get("raw") if isinstance(ot.get("raw"), str) else ""
    # protected means a person checked these words: still safe to lay out when every day and time is explicit
    if ot.get("status") == "TIMES_TEXT_ONLY" and (raw or ot.get("lines")):
        src = raw or " | ".join(ot.get("lines") or [])
        conv, _ = try_convert(src)
        if conv and conv.get("all_closed"):
            ot.update(status="TIMES_FOUND", structured=None, all_closed=True, parsed_from_text=True)
            ot.pop("closed", None); ot.pop("notes", None)
            if not raw: ot["raw"] = src
        elif conv and conv.get("structured"):
            ot.update(status="TIMES_FOUND", structured=conv["structured"], parsed_from_text=True)
            ot.pop("all_closed", None)
            if conv.get("closed"): ot["closed"] = conv["closed"]
            else: ot.pop("closed", None)
            if conv.get("notes"): ot["notes"] = conv["notes"]
            else: ot.pop("notes", None)
            if not raw: ot["raw"] = src
    elif ot.get("status") == "TIMES_FOUND" and not ot.get("all_closed"):
        # no raw (already compacted): keep a closed list the pipeline stored earlier
        if raw or "closed" not in ot:
            closed = closed_days_for(ot)
            if closed: ot["closed"] = closed
            elif raw: ot.pop("closed", None)
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
