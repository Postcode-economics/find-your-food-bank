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
def joined_centre_times(i, centres):
    """-> new opening_times for parent i, or None when unchanged."""
    ot = i.get("opening_times")
    if not ot or _hand(ot) or i.get("type") != "foodbank" or not centres: return None
    segs = _segs(ot)
    cen = set()
    for c in centres:
        for s in _segs(c.get("opening_times")): cen.add(_norm(s.replace("Opening times", "")))
    from times import normalise
    def st(x):
        o = normalise({"raw": x, "status": "TIMES_TEXT_ONLY", "structured": None}) or {}
        return o.get("structured") if o.get("status") == "TIMES_FOUND" else None
    cst = [c["opening_times"]["structured"] for c in centres if (c.get("opening_times") or {}).get("structured")]
    def centre_owned(x):
        a = st(x)
        return bool(a) and any(all(cs.get(d) and all(r in cs[d] for r in rr) for d, rr in a.items()) for cs in cst)
    segs_all = segs
    keep = [s for s in segs if not centre_owned(s) and _norm(s.replace("Opening times", "")) not in cen and not CARD.search(s)
            and not any(_norm(s) and _norm(s) in x for x in cen)]
    # several segments giving the same day different hours = several centres' times joined together (Woodley)
    seen = {}; clash = 0
    for x in keep:
        for d, rr in (st(x) or {}).items():
            if d in seen and seen[d] != rr: clash += 1
            seen.setdefault(d, rr)
    if clash >= 2: keep = []
    if len(keep) == len(segs) and not (len(segs) > 1 and i.get("kind") in ("warehouse", "dropoff")): return None
    if i.get("kind") in ("warehouse", "dropoff") and len(segs) > 1: keep = []  # office/warehouse: never centres' joined times
    if not keep: return _none(ot, "centres' joined times removed")
    from times import normalise
    return normalise({"raw": " | ".join(keep), "status": "TIMES_TEXT_ONLY", "structured": None,
                      "source_url": ot.get("source_url"), "checked_date": ot.get("checked_date")})
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
        if m and re.match(r"\s*(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*$", s[m.end():], re.I) and not DAY.search(s[:m.start()]):
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
        if new is not None:
            log[i["id"]] = new.get("guard") or "trimmed"; i["opening_times"] = new
    return log
