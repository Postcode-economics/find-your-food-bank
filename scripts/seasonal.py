"""Seasonal start/end dates for warm spaces and shelters (pop-ups, winter night shelters).
Reads dates only from the source's own wording (never guessed). Sets on each item:
  scheme_start / scheme_end (ISO), upcoming (opens later), ended (past end date),
  scheme_dates (shown in the existing 'Scheme dates' row: 'Opens 7 Dec 2026', 'Until 31 Mar 2027', or both).
A hand-checked note (scheme_dates_lock: true, from overrides) is never replaced by the date label.
Ended entries are kept greyed (existing behaviour) for EXPIRE_DAYS, then moved to recently_closed."""
import re, datetime
MON = ["january","february","march","april","may","june","july","august","september","october","november","december"]
MRE = "|".join(MON + [m[:3] for m in MON] + ["sept"])
D = r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + MRE + r")\.?,?\s+(20\d\d)"
EXPIRE_DAYS = 14
def _d(day, mon, yr):
    m = mon.lower()[:3]; i = [x[:3] for x in MON].index(m) + 1
    try: return datetime.date(int(yr), i, int(day))
    except ValueError: return None
def _all(t): return [x for x in (_d(*g) for g in re.findall(D, t or "", re.I)) if x]
def parse(text):
    """Return {'start': iso|'', 'end': iso|''} from the source's own wording."""
    t = re.sub(r"\s+", " ", text or "")
    start = end = None
    m = re.search(r"(?:space )?opening on\s+" + D, t, re.I) or re.search(r"(?:opens?|opening|starts?|starting|beginning|from)\s+(?:on\s+)?(?:\w+day\s+)?" + D, t, re.I)
    if m: start = _d(*m.groups()[-3:])
    m = re.search(r"(?:until|till|to|–|-|through)\s+(?:the\s+)?(?:\w+day\s+)?" + D, t, re.I)
    if m:
        e = _d(*m.groups()[-3:])
        if e and (not start or e > start): end = e
    if not end:
        m = re.search(r"(?:until|till|to|through) (?:the )?end of (" + MRE + r")\s+(20\d\d)", t, re.I)
        if m:
            e = _d(1, m.group(1), m.group(2))
            if e: end = (e.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    return {"start": start.isoformat() if start else "", "end": end.isoformat() if end else ""}
def fmt(iso):
    d = datetime.date.fromisoformat(iso); return f"{d.day} {MON[d.month-1][:3].title()} {d.year}"
def label(start, end, run):
    parts = []
    if start and start > run: parts.append("Opens " + fmt(start))
    if end: parts.append(("until " if parts else "Until ") + (fmt(end) if parts else end))
    return " ".join(parts)
def apply(items, run, closed=None, expire_days=EXPIRE_DAYS):
    """Mutates items; returns (items_kept, newly_expired). Existing 'Until YYYY-MM-DD' wording kept for the Welsh date formatter."""
    rd = run if isinstance(run, str) else run.isoformat()
    keep, gone = [], []
    for x in items:
        s, e = x.get("scheme_start") or "", x.get("scheme_end") or ""
        x["upcoming"] = bool(s and s > rd)
        if e or "ended" in x: x["ended"] = bool(e and e < rd)
        if s or e:
            lab = label(s, e, rd)
            if lab and not x.get("scheme_dates_lock") and not (not x["upcoming"] and str(x.get("scheme_dates", "")).startswith(lab)): x["scheme_dates"] = lab
        if not x["upcoming"]: x.pop("upcoming", None)
        if x.get("ended") and (datetime.date.fromisoformat(rd) - datetime.date.fromisoformat(e)).days > expire_days:
            x["closed_on"] = rd; x["closed_reason"] = f"Season ended {fmt(e)} (source's stated end date)"; gone.append(x)
        else: keep.append(x)
    if closed is not None: closed.extend(gone)
    return keep, gone
