"""Held places near the top 20 UK cities, and a coverage watch on what is published.

Distance for held places uses the outcode centroid in outcodes.json. Distance for published
places uses each listing's own pin. 10km from the city centre. The watch writes a report and,
when asked, raises the existing refresh alert. It does not fail a run, and it does not change
phones or council lines.

'fewer than ~5 warm spaces' is fewer than 5 published warm spaces. 'no shelter or day centre'
counts published shelters plus any listing already carrying the Day centre label.
"""
import json, os, re
import discover

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADIUS_KM = 10
WARM_MIN = 5
TAG = "held near cities"
# City-centre points for the 20 cities this watch uses, including every city named in the 31 Oct 2026 audit.
CITIES = [
    {"name": "London", "lat": 51.5074, "lng": -0.1278},
    {"name": "Birmingham", "lat": 52.4862, "lng": -1.8904},
    {"name": "Manchester", "lat": 53.4808, "lng": -2.2426},
    {"name": "Glasgow", "lat": 55.8642, "lng": -4.2518},
    {"name": "Leeds", "lat": 53.8008, "lng": -1.5491},
    {"name": "Liverpool", "lat": 53.4084, "lng": -2.9916},
    {"name": "Newcastle upon Tyne", "lat": 54.9783, "lng": -1.6178},
    {"name": "Sheffield", "lat": 53.3811, "lng": -1.4701},
    {"name": "Bristol", "lat": 51.4545, "lng": -2.5879},
    {"name": "Belfast", "lat": 54.5973, "lng": -5.9301},
    {"name": "Leicester", "lat": 52.6369, "lng": -1.1398},
    {"name": "Edinburgh", "lat": 55.9533, "lng": -3.1883},
    {"name": "Cardiff", "lat": 51.4816, "lng": -3.1791},
    {"name": "Coventry", "lat": 52.4068, "lng": -1.5197},
    {"name": "Bradford", "lat": 53.7960, "lng": -1.7594},
    {"name": "Nottingham", "lat": 52.9548, "lng": -1.1581},
    {"name": "Kingston upon Hull", "lat": 53.7676, "lng": -0.3274},
    {"name": "Stoke-on-Trent", "lat": 53.0027, "lng": -2.1794},
    {"name": "Southampton", "lat": 50.9097, "lng": -1.4044},
    # City centre near Churchill Square. Published coverage uses each listing's own pin in
    # warmspaces.js / shelters.js, not the outcode. BN1, BN2, BN3 and BN41 fall inside 10km;
    # BN17 (Littlehampton) and BN20 (Eastbourne) do not.
    {"name": "Brighton and Hove", "lat": 50.8225, "lng": -0.1372},
]


def outcode(pc):
    """Outward code: the postcode minus its inward code (always the last three characters)."""
    n = discover.norm_pc(pc)
    if len(n) < 5 or not n[-3:-2].isdigit():
        return ""
    return n[:-3]


def load_outcodes(root=None):
    root = root or ROOT
    for p in (os.path.join(root, "outcodes.json"), os.path.join(ROOT, "outcodes.json")):
        if os.path.isfile(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                return {}
    return {}


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def load_items(path):
    try:
        t = open(path, encoding="utf-8").read()
        i = t.index("{")
        return json.loads(t[i:t.rindex("}") + 1]).get("items") or []
    except Exception:
        return []


def active(items):
    return [i for i in items or [] if not i.get("ended") and not i.get("flag_closed")]


def is_day_centre(item):
    """A published day centre uses label 'Day centre' or kind/service day_centre (underscore, as on the map)."""
    kind = (item.get("kind") or item.get("service") or "").lower().replace("-", " ").replace("_", " ")
    return item.get("label") == "Day centre" or kind == "day centre"


def within_pin(items, city, km=RADIUS_KM):
    out = []
    for i in items or []:
        if i.get("lat") is None or i.get("lng") is None:
            continue
        if discover.hav(float(i["lat"]), float(i["lng"]), city["lat"], city["lng"]) <= km:
            out.append(i)
    return out


def near_outcode(places, cities, codes, km=RADIUS_KM):
    """places -> {city name: [places]}. Also returns how many had no outcode centroid."""
    buckets = {c["name"]: [] for c in cities}
    unlocated = 0
    for p in places or []:
        xy = codes.get(outcode(p.get("postcode")))
        if not xy or len(xy) < 2:
            unlocated += 1
            continue
        for c in cities:
            if discover.hav(xy[0], xy[1], c["lat"], c["lng"]) <= km:
                buckets[c["name"]].append(p)
    return buckets, unlocated


def reason_of(p):
    flags = (p.get("autocheck") or {}).get("flags") or []
    reason = (p.get("reason") or p.get("why") or "held").strip()
    if reason == "not on allowlist" and flags:
        reason = "not on allowlist; " + str(flags[0])
    reason = re.sub(r"\s+", " ", reason)
    if len(reason) <= 90:
        return reason
    return reason[:90].rsplit(" ", 1)[0]


def main_reason(places):
    from collections import Counter
    c = Counter(reason_of(p) for p in places)
    if not c:
        return "none"
    return c.most_common(1)[0][0]


def held_rows(warm, shelters, day_centres, codes, cities=None):
    cities = cities or CITIES
    bw, uw = near_outcode(warm, cities, codes)
    bs, us = near_outcode(shelters, cities, codes)
    bd, ud = near_outcode(day_centres, cities, codes)
    rows = []
    for c in cities:
        name = c["name"]
        bag = bw[name] + bs[name] + bd[name]
        rows.append({
            "city": name,
            "warm": len(bw[name]),
            "shelters": len(bs[name]),
            "day_centres": len(bd[name]),
            "reason": main_reason(bag) if bag else "none held",
        })
    return rows, uw + us + ud


def _n(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def held_lines(rows, unlocated):
    lines = ["Counts of held warm spaces, shelters and day-centre candidates within 10km of each top-20 city centre (outcode centroid). Not on the map.", ""]
    for r in rows:
        lines.append("- %s: %s, %s, %s — main reason: %s" % (
            r["city"], _n(r["warm"], "warm space", "warm spaces"), _n(r["shelters"], "shelter", "shelters"),
            _n(r["day_centres"], "day centre", "day centres"), r["reason"]))
    if unlocated:
        lines.append("")
        lines.append("%d held places had no outcode centroid, so they are not counted under a city." % unlocated)
    return lines


def load_held(root):
    warm = load_json(os.path.join(root, "logs", "warmspaces_pending.json"), [])
    shelters = load_json(os.path.join(root, "logs", "shelters_pending.json"), [])
    dc = load_json(os.path.join(root, "logs", "day_centre_candidates.json"), {})
    if not isinstance(warm, list):
        warm = []
    if not isinstance(shelters, list):
        shelters = []
    days = dc.get("candidates") if isinstance(dc, dict) else []
    if not isinstance(days, list):
        days = []
    return warm, shelters, days


def held_summary(root=None):
    """Short section for the findings report. Empty when there is nothing held."""
    root = root or ROOT
    warm, shelters, days = load_held(root)
    if not warm and not shelters and not days:
        return ""
    rows, unlocated = held_rows(warm, shelters, days, load_outcodes(root))
    body = "\n".join(held_lines(rows, unlocated))
    return "Held near cities\n" + body


def replace_section(path, tag, block_lines):
    start, end = "<!-- %s -->" % tag, "<!-- /%s -->" % tag
    block = start + "\n" + "\n".join(block_lines).rstrip() + "\n" + end
    prev = ""
    if os.path.exists(path):
        prev = open(path, encoding="utf-8").read()
    if start in prev and end in prev:
        prev = re.sub(re.escape(start) + r".*?" + re.escape(end), block, prev, count=1, flags=re.S)
        text = prev
    else:
        base = prev.rstrip() if prev else "# Pending for Dean\n"
        text = base + "\n\n" + block + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    open(path, "w", encoding="utf-8").write(text)


def write_held_section(root=None):
    root = root or ROOT
    warm, shelters, days = load_held(root)
    rows, unlocated = held_rows(warm, shelters, days, load_outcodes(root))
    lines = ["## Held near cities", ""] + held_lines(rows, unlocated)
    replace_section(os.path.join(root, "reports", "pending_dean.md"), TAG, lines)
    return rows


def coverage(warm_items, shelter_items, day_items=None, cities=None):
    """Published coverage. day_items are listings that already carry the Day centre label."""
    cities = cities or CITIES
    warm_items, shelter_items = active(warm_items), active(shelter_items)
    day_items = [i for i in (day_items if day_items is not None else []) if is_day_centre(i)]
    # A shelter list may also carry the label; count those as day centres as well as shelters
    # only when the caller passed them in day_items. Shelters here are night shelters.
    rows = []
    for c in cities:
        nw = len(within_pin(warm_items, c))
        ns = len(within_pin(shelter_items, c))
        nd = len(within_pin(day_items, c))
        gaps = []
        if nw < WARM_MIN:
            gaps.append("fewer than %d warm spaces (%d)" % (WARM_MIN, nw))
        if ns + nd < 1:
            gaps.append("no shelter or day centre")
        rows.append({"city": c["name"], "warm": nw, "shelters": ns, "day_centres": nd, "gaps": gaps})
    return rows


def coverage_lines(rows):
    lines = ["Published places within 10km of each top-20 city centre (the listing's own pin).",
             "An alert is raised when a city has fewer than %d warm spaces or no shelter or day centre. This check does not fail the run." % WARM_MIN,
             ""]
    for r in rows:
        note = "; ".join(r["gaps"]) if r["gaps"] else "ok"
        lines.append("- %s: %s, %s, %s — %s" % (
            r["city"], _n(r["warm"], "warm space", "warm spaces"), _n(r["shelters"], "shelter", "shelters"),
            _n(r["day_centres"], "day centre", "day centres"), note))
    return lines


def write_coverage(root=None, warm=None, shelters=None, day_items=None):
    root = root or ROOT
    if warm is None:
        warm = load_items(os.path.join(root, "warmspaces.js"))
    if shelters is None:
        shelters = load_items(os.path.join(root, "shelters.js"))
    if day_items is None:
        day_items = [i for i in shelters + warm if is_day_centre(i)]
        shelters = [i for i in shelters if not is_day_centre(i)]
    rows = coverage(warm, shelters, day_items)
    path = os.path.join(root, "reports", "city_coverage.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("# City coverage\n\n" + "\n".join(coverage_lines(rows)) + "\n")
    return rows


def notify(rows, opener=None, resolver=None):
    """Alert through scripts/alert.py. Missing credentials are the caller's problem; this function does not exit."""
    import alert as A
    opener = opener or A.open_
    resolver = resolver or A.resolve
    gaps = [r for r in rows if r.get("gaps")]
    if not gaps:
        resolver("city-coverage")
        return 0
    title = "City coverage: %d top-20 cities under the warm-space or shelter line" % len(gaps)
    body = "\n".join("- %s: %s, %s, %s — %s" % (
        r["city"], _n(r["warm"], "warm space", "warm spaces"), _n(r["shelters"], "shelter", "shelters"),
        _n(r["day_centres"], "day centre", "day centres"), "; ".join(r["gaps"])) for r in gaps)
    opener("city-coverage", title, body)
    return len(gaps)


def run_watch(root=None, alert=True, opener=None, resolver=None):
    """Write the report and the held section, then alert. Always returns 0."""
    root = root or ROOT
    try:
        rows = write_coverage(root)
        write_held_section(root)
        if alert:
            try:
                notify(rows, opener=opener, resolver=resolver)
            except Exception as ex:
                print("city coverage alert not sent: %s" % ex)
        print("city coverage: %d cities short" % sum(1 for r in rows if r.get("gaps")))
    except Exception as ex:
        print("city coverage watch failed: %s" % ex)
    return 0


def main(argv=None):
    """Always exits 0: a thin city is not a CI failure."""
    import sys
    argv = argv if argv is not None else sys.argv
    return run_watch(alert="--report-only" not in argv)


if __name__ == "__main__":
    import sys
    sys.exit(main())
