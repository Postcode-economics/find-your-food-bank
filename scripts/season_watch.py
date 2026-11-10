"""Season watcher for the held Lancashire council list (plan 1.4, 9 Nov 2026). Reporting only.

All Lancashire warm-space rows are held ("feed not yet confirmed for 2026-27"). This watches each run for the
council's own feed to carry EXPLICIT 2026-27 season dates (a "2026-27" / "2026/27" label, or a stated date between
1 Sep 2026 and 31 May 2027). An edit date alone is not enough, and last season's dates (e.g. "12th Jan - 30th Mar
2026") count as past. When explicit current rows appear it writes a spot-check pack (rule 59): a small fixed sample
to compare with each venue's own page. It never lifts the hold itself: lifting stays a reviewed, spot-checked PR.
Writes reports/lancs_season.json and reports/lancs_season.md (private, gitignored).
"""
import datetime, hashlib, json, os, re

START = datetime.date(2026, 9, 1)
END = datetime.date(2027, 5, 31)
SAMPLE = 5
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
LABEL = re.compile(r"\b2026\s*[-/–]\s*(?:20)?27\b|\bwinter\s+2026\b", re.I)  # "26-27 High St" is an address, not a season
# "12th Jan 2026", "3 November 2026", "Jan 12 2026"; also numeric 12/01/2026
DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(20\d\d)\b")
MDY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b")
NUM = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d\d)\b")
# a range whose year is only on the end: "12th Jan - 30th Mar 2026"
RANGE_TAIL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s*[-–to]+\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(20\d\d)\b")


def _d(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _mon(s):
    return MONTHS.get((s or "")[:3].lower())


def dates_in(text):
    t = re.sub(r"\s+", " ", str(text or ""))
    out = []
    for d, m, y in DMY.findall(t):
        if _mon(m): out.append(_d(y, _mon(m), d))
    for m, d, y in MDY.findall(t):
        if _mon(m): out.append(_d(y, _mon(m), d))
    for d, m, y in NUM.findall(t):
        out.append(_d(y, m, d))
    for d1, m1, d2, m2, y in RANGE_TAIL.findall(t):
        if _mon(m1) and _mon(m2):
            y1 = int(y) - 1 if _mon(m1) > _mon(m2) else int(y)
            out.append(_d(y1, _mon(m1), d1))
    return [x for x in out if x]


def row_season(attrs):
    """-> ('current', evidence) for explicit 2026-27 text; ('past', evidence) for dated text all before 1 Sep 2026;
    ('undated', '') otherwise. Edit dates are ignored on purpose."""
    a = attrs or {}
    text = " ".join(str(a.get(k) or "") for k in a if isinstance(a.get(k), str))
    m = LABEL.search(text)
    if m:
        return "current", m.group(0)
    ds = dates_in(text)
    cur = [x for x in ds if START <= x <= END]
    if cur:
        return "current", min(cur).isoformat()
    if ds:
        return "past", max(ds).isoformat()
    return "undated", ""


def _attrs(f):
    a = (f or {}).get("attributes") or f or {}
    return {str(k).lower(): v for k, v in a.items()}


def watch(features, run_day, sample=SAMPLE):
    rows = []
    for f in features or []:
        a = _attrs(f)
        if str(a.get("orgapproved") or "").lower() != "yes":
            continue
        s, ev = row_season(a)
        rows.append({"objectid": a.get("objectid"), "name": re.sub(r"\s+", " ", str(a.get("orgname") or "")).strip(),
                     "season": s, "evidence": ev, "times": re.sub(r"\s+", " ", str(a.get("orgopentimes") or "")).strip()[:160],
                     "website": str(a.get("orgwebsite") or "").strip()})
    counts = {k: sum(1 for r in rows if r["season"] == k) for k in ("current", "past", "undated")}
    cur = [r for r in rows if r["season"] == "current"]
    # fixed sample per day, so a re-run shows the same rows to check
    cur.sort(key=lambda r: hashlib.sha256(("%s|%s" % (run_day, r["objectid"])).encode()).hexdigest())
    return {"run_day": run_day, "rows": len(rows), "counts": counts, "ready_for_spot_check": bool(cur),
            "spot_check": cur[:sample], "lifts_hold": False}


def write(features, run_day, root):
    doc = watch(features, run_day)
    rep = os.path.join(root, "reports"); os.makedirs(rep, exist_ok=True)
    json.dump(doc, open(os.path.join(rep, "lancs_season.json"), "w"), indent=1, ensure_ascii=False)
    c = doc["counts"]
    L = ["# Lancashire warm spaces: season watch (%s)" % run_day, "",
         "Rows in the council feed: %d. Explicit 2026-27 dates: %d. Last season's dates only: %d. No dates: %d." % (doc["rows"], c["current"], c["past"], c["undated"]),
         "The hold is never lifted by this check. An edit date alone does not count.", ""]
    if doc["ready_for_spot_check"]:
        L += ["**Ready for a spot-check (rule 59).** Compare these with each venue's own page, then lift the hold in a reviewed PR:", ""]
        L += ["- %s (object %s): %s; times: %s; %s" % (r["name"], r["objectid"], r["evidence"], r["times"], r["website"] or "no website") for r in doc["spot_check"]]
    else:
        L.append("Still last season's list. Nothing to do.")
    open(os.path.join(rep, "lancs_season.md"), "w").write("\n".join(L) + "\n")
    return doc
