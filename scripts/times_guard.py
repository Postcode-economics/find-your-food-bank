"""Root-cause rules for times shown on a food bank card (27 Oct 2026 times audit, 111 wrong listings).
Runs inside classify.classify() on every build, after opening_times are set, so the refresh can never re-add them.
Hand-reviewed times (reader 'hand-reviewed ...') are never touched.

1. Joined centre times: a parent / office / warehouse listing never carries its centres' times joined together
   ('Mon Closed Tue 13:00 - 15:00 | Mon 13:00 - 15:00 | ...'). Segments that are a centre's own times, or a whole
   'Mon .. Sun' card copied from a locations page when the parent has centres, are removed; if nothing is left the
   card shows no times (call for times), never 'Closed'.
2. Salvation Army corps pages list church activities next to the food bank. A Salvation Army listing keeps a time
   segment only when the segment itself mentions food / food bank / parcels / pantry, the day is written before the
   time on that same segment (a day that only follows the time belongs to the next line), and the source page is
   that corps' own page (salvationarmy.org.uk/<corps>)."""
import re
FOOD = re.compile(r"\b(food\s*bank|foodbank|food|parcels?|pantry|larder)\b", re.I)
DAY = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b", re.I)
SPAN = re.compile(r"\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?\s*[-–]\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|noon)?", re.I)
CARD = re.compile(r"^\s*(opening times\s+)?mon\b.*\bsun\b", re.I)  # a whole 7-day card from a Trussell locations page
def _hand(ot): return str((ot or {}).get("reader", "")).startswith("hand-reviewed")
def _norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
def _segs(ot): return [s.strip() for s in str((ot or {}).get("raw") or "").split(" | ") if s.strip()]
def _none(ot, why):
    return {"status": "NO_TIMES", "structured": None, "raw": "", "source_url": (ot or {}).get("source_url"),
            "checked_date": (ot or {}).get("checked_date"), "guard": why}
CARDSEG = re.compile(r"^\s*(opening times\s+)?(mon|tue|wed|thu|fri|sat|sun)\s+(closed|\d{1,2}:\d{2})", re.I)  # Trussell card line
CARDSTART = re.compile(r"^\s*(opening times\s+)?mon\s+(closed|\d{1,2}:\d{2})", re.I)
NOT_CLIENT_PAGE = re.compile(r"vacanc|volunteer|donat|/jobs?\b|career|support-us|give", re.I)
ZERO = re.compile(r"\b(\d{1,2}:\d{2})\s*-\s*\1\b")
_DO = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
def _days(x): return [_DO.index(m.lower()[:3]) for m in re.findall(r"\b(mon|tue|wed|thu|fri|sat|sun)", x, re.I)]
def _first_day(x): d = _days(x); return d[0] if d else -1
def _last_day(x): d = _days(x); return d[-1] if d else 99
def _groups(segs):
    """Join split Trussell cards back together: a card starts at 'Mon ..' and runs to the next 'Mon ..'. Prose lines stay alone."""
    g = []
    for x in segs:
        if CARDSEG.search(x) and g and CARDSEG.search(g[-1][0]) and not CARDSTART.search(x) and _first_day(x) > _last_day(g[-1][-1]): g[-1].append(x)
        else: g.append([x])
    return [" | ".join(y) for y in g]
OFFICE = re.compile(r"\bp\.?\s?o\.?\s?box\b|\bc/o\b|postal|warehouse|head office|\boffice\b", re.I)
_OWN = None
def own_lines():
    """overrides/own_centre_lines.json: the listing's own centre hours line, quoted from the organisation's own page."""
    global _OWN
    if _OWN is None:
        import os, json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overrides", "own_centre_lines.json")
        try: _OWN = {k: v for k, v in json.load(open(p)).items() if not k.startswith("_")}
        except Exception: _OWN = {}
    return _OWN
def _office(i):
    """An office, warehouse or PO-box/postal listing: classified warehouse/drop-off, or its own address says so."""
    return i.get("kind") in ("warehouse", "dropoff") or bool(OFFICE.search(" ".join(str(i.get(k) or "") for k in ("name", "address"))))
def joined_centre_times(i, centres):
    """-> new opening_times for parent i, or None when unchanged.
    Bot 3 review of #232 (28 Oct 00:10): a single block is the listing's own (dundonald, wythenshawe, weston, cheltenham, hart, vale,
    lichfield): never removed. Several centres -> trim to the listing's own block (bestwood-bulwell, dumbarton, watford keeps Thu).
    Trims drop phone-line / volunteer / donation times (chesterfield, north-lakes, north-belfast). A warehouse pin whose only
    centre's card it carries (rugby, middlewich) is held for review, never wiped."""
    ot = i.get("opening_times")
    if not ot or _hand(ot) or i.get("type") != "foodbank" or not centres: return None
    src = str(ot.get("source_url") or ""); path = src.split("://", 1)[-1].split("/", 1)[-1] if "/" in src.split("://", 1)[-1] else ""
    if NOT_CLIENT_PAGE.search(path): return _none(ot, "times came from a vacancies/volunteer/donation page")
    segs = _segs(ot)
    from times import normalise
    ev = own_lines().get(i["id"])
    if ev:  # Bot 3 re-sample 2 (28 Oct): the page gives this listing's own centre a separate hours line -> keep exactly that line
        want = {_norm(x) for x in ev.get("lines", [])}; groups0 = _groups(segs)
        mine = [g for g in groups0 if _norm(g) in want] or [x for x in segs if _norm(x) in want]
        if mine:
            if " | ".join(mine) == " | ".join(segs): return None
            return dict(normalise({"raw": " | ".join(mine), "status": "TIMES_TEXT_ONLY", "structured": None, "source_url": ot.get("source_url"),
                                   "checked_date": ot.get("checked_date")}), guard="kept the listing's own centre line (quoted on its own page)")
    def st(x):
        o = normalise({"raw": x, "status": "TIMES_TEXT_ONLY", "structured": None}) or {}
        return o.get("structured") if o.get("status") == "TIMES_FOUND" else None
    groups = _groups(segs)
    if len(groups) == 1:
        if i.get("kind") in ("warehouse", "dropoff") and len(centres) == 1 and len(segs) > 1:
            return {"_held": "warehouse pin carrying its only centre's times: held for review (rugby, middlewich)"}
        return None  # one block: the listing's own (matched by name/postcode when it was read)
    trussell = "foodbank.org.uk" in src
    keep = []
    for g in groups:
        if ZERO.search(g): g = " | ".join(x for x in g.split(" | ") if not ZERO.search(x))  # 'Thu 10:00 - 10:00': not a session
        if not g: continue
        if trussell and not CARDSEG.search(g): continue  # prose on a Trussell locations page = donation / phone-line notes
        keep.append(g)
    cen_norm = set(); cen_st = []; names = []
    for c in centres:
        r = str((c.get("opening_times") or {}).get("raw") or "")
        if r: cen_norm.add(_norm(r.replace("Opening times", ""))); cen_norm.update(_norm(x.replace("Opening times", "")) for x in _segs(c.get("opening_times")))
        if (c.get("opening_times") or {}).get("structured"): cen_st.append(c["opening_times"]["structured"])
        n = re.sub(r"\(.*?\)", "", c.get("name") or "").strip()
        if len(n) >= 6: names.append(n.lower())
    def owned(g):
        a = st(g)
        return (_norm(g.replace("Opening times", "")) in cen_norm or (a and a in cen_st) or any(n in g.lower() for n in names))
    keep = [g for g in keep if not owned(g)]
    seen = {}; clash = 0
    for x in keep:
        for d, rr in (st(x) or {}).items():
            if d in seen and seen[d] != rr: clash += 1
            seen.setdefault(d, rr)
    cards = [g for g in keep if CARDSEG.search(g)]
    if clash >= 2 or len(cards) > 1: keep = []  # still several centres' blocks: cannot tell which is this listing's
    if i.get("kind") in ("warehouse", "dropoff") and len(keep) > 1: keep = []
    if " | ".join(keep) == " | ".join(segs): return None
    if not keep: return _none(ot, "centres' joined times removed")
    if _office(i):  # Bot 3 re-sample 2: a leftover block on an office / warehouse / PO-box listing is another site's (or the warehouse's own donation hours)
        return _none(ot, "office/warehouse/postal listing: another site's times not kept")
    return dict(normalise({"raw": " | ".join(keep), "status": "TIMES_TEXT_ONLY", "structured": None,
                           "source_url": ot.get("source_url"), "checked_date": ot.get("checked_date")}), guard="trimmed to the listing's own block")
def salvation_army(i):
    ot = i.get("opening_times")
    if not ot or _hand(ot) or not i["id"].startswith("salvation-army/"): return None
    corps = i["id"].split("/", 1)[1]; src = str(ot.get("source_url") or "")
    if src and "salvationarmy.org.uk" in src and not (corps.startswith(src.rstrip("/").rsplit("/", 1)[-1]) or src.rstrip("/").rsplit("/", 1)[-1].startswith(corps)):
        return _none(dict(ot, source_url=None), "times came from another corps' page")
    keep = []
    for s in _segs(ot) or [str(ot.get("raw") or "")]:
        if not FOOD.search(s): continue
        m = SPAN.search(s); d = DAY.search(s)
        if m and re.match(r"\s*(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*$", s[m.end():], re.I) and not DAY.search(s[:m.start()]) \
                and len(s[:m.start()].split()) <= 2:  # bare heading 'Foodbank 9am - 1pm Thursday' (Inverness); 'Foodbank is operating from ... Saturday' (Birkenhead) is one sentence
            continue  # 'Foodbank 9am - 1pm Thursday': the trailing day starts the next line (Inverness), not this one
        keep.append(s)
    if keep == _segs(ot): return None
    if not keep: return _none(ot, "no food bank time on its own line next to food bank wording")
    from times import normalise
    return normalise({"raw": " | ".join(keep), "status": "TIMES_TEXT_ONLY", "structured": None,
                      "source_url": ot.get("source_url"), "checked_date": ot.get("checked_date")})
def apply(items):
    """Mutates items; returns {id: reason} of what changed."""
    locs = {}
    for i in items:
        if i.get("type") == "location": locs.setdefault(i["id"].split("/")[0], []).append(i)
    log = {}
    for i in items:
        new = salvation_army(i)
        if new is None and i.get("type") == "foodbank": new = joined_centre_times(i, locs.get(i["id"], []))
        if new is not None and new.get("_held"):
            log[i["id"]] = "held for review: " + new["_held"]; continue  # times kept as they are
        if new is not None:
            log[i["id"]] = new.get("guard") or "trimmed"; i["opening_times"] = new
    return log
