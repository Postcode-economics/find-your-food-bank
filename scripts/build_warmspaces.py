"""Warm Spaces layer scraper. Separate from food banks and shelters.
Writes warmspaces.js and logs/warmspaces_log.json. Seasonal: entries whose scheme end date has passed are
marked 'ended' (shown greyed); they become active again automatically when a new listing/date appears."""
import json, sys, os, re, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import *
RUN = today(); OUT, LOG = "warmspaces.js", "logs/warmspaces_log.json"
SP = "https://api.storepoint.co/v1/16320a694c8cc5/locations"  # Warm Welcome network public map feed
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], 1)}
DATE_RE = re.compile(r"\b(?:until|till|to|ends?|running to|closes? on|-|–)\s*(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(20\d\d)?", re.I)
def end_date(text):
    m = None
    for m in DATE_RE.finditer(text or ""): pass
    if not m or not m.group(3): return ""  # only trust end dates that state a year
    y = int(m.group(3)); d = datetime.date(y, MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
    return d.isoformat()
seen, sources = {}, {}
def pull(q):
    return (json.loads(get(SP + ("?" + q if q else ""))).get("results") or {}).get("locations") or []
try:
    for x in pull(""): seen[x["id"]] = x
    # the feed caps results (5000 unfiltered, 500 per radius query), so sweep a grid of the UK, subdividing busy cells
    def sweep(lat, lng, r):
        res = pull(f"lat={lat}&long={lng}&radius={r}")
        for x in res: seen[x["id"]] = x
        if len(res) >= 490 and r > 3:
            h = r / 2; dl = h / 69; dg = h / 40
            for a in (-dl, dl):
                for b in (-dg, dg): sweep(round(lat + a, 4), round(lng + b, 4), h)
    lat = 49.9
    while lat <= 60.9:
        lng = -8.2
        while lng <= 1.8:
            sweep(round(lat, 3), round(lng, 3), 40); lng += 1.3
        lat += 0.8
    sources["Warm Welcome network (warmwelcome.uk map feed)"] = {"status": "ok", "count": len(seen)}
except Exception as ex:
    sources["Warm Welcome network (warmwelcome.uk map feed)"] = {"status": f"failed: {ex}", "count": len(seen)}
fresh = []
for x in seen.values():
    if not (49.8 < (x.get("loc_lat") or 0) < 61 and -8.7 < (x.get("loc_long") or 99) < 2): continue  # UK only
    tags = [t.strip(" \u00a0") for t in (x.get("tags") or "").split(",") if t.strip(" \u00a0")]
    provided = [t for t in tags if t.lower() not in DAYS]
    desc = re.sub(r"\s+", " ", x.get("description") or "").strip()
    hours = {d[:3].title(): (x.get(d) or "").strip() for d in DAYS if (x.get(d) or "").strip() and (x.get(d) or "").strip().lower() != "closed"}
    cf = {}
    try: cf = json.loads(x.get("custom_fields") or "{}")
    except Exception: pass
    page = next((v for v in cf.values() if "/space?" in v), "https://www.warmwelcome.uk/find-a-space")
    low = (desc + " " + " ".join(tags)).lower()
    booking = "Booking needed" if re.search(r"\b(book(ing)? (is )?(required|essential|needed)|must book|please book)\b", low) else ("No booking needed" if re.search(r"no (need to book|booking)|drop[- ]in|just turn up", low) else "Not stated")
    end = end_date(desc)
    fresh.append({"id": f"ww-{x['id']}", "name": x["name"].strip(), "address": (x.get("streetaddress") or "").strip(), "postcode": postcode(x.get("streetaddress")),
        "lat": x["loc_lat"], "lng": x["loc_long"], "phone": (x.get("phone") or "").strip(), "website": (x.get("website") or "").strip(),
        "hours": hours, "provided": provided, "booking": booking, "notes": desc[:240],
        "scheme_end": end, "scheme_dates": ("Until " + end) if end else "Not stated by source",
        "ended": bool(end and end < RUN), "source": "Warm Welcome", "source_url": page, "last_verified": RUN})
man = json.load(open("overrides/warmspaces_manual.json")) if os.path.exists("overrides/warmspaces_manual.json") else []
for m in man:
    m["ended"] = bool(m.get("scheme_end") and m["scheme_end"] < RUN); fresh.append(m)
sources["Manual (council pages, press releases, approved self-registrations)"] = {"status": "ok", "count": len(man)}
for k, why in {"Council warm spaces / warm hubs pages (~360 councils)": "no common format; most councils now list via the Warm Welcome map (already included). Individual council pages to be added via overrides/warmspaces_manual.json with source URL",
               "Age UK branches, British Red Cross, libraries, church directories": "no machine-readable UK-wide listing; many of these venues are already registered on Warm Welcome"}.items():
    sources[k] = {"status": "not scraped: " + why}
prev = load_js(OUT, "WARMSPACES")
# Verification gate: publish only allowlisted warm spaces (independently confirmed for the current season).
VER = load_verified("overrides/warmspaces_verified.json")
def season_end(v):  # a verification is valid only for the winter season it was made in (to 30 April)
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01"))
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"
def ws_autocheck(x):
    # Evidence the feed allows: opening hours, no past end date. The listing's own last-updated date
    # is shown on warmwelcome.uk; a spot-check of 51 season-updated listings passed only 59%, so this
    # pre-check can never publish on its own.
    flags = []
    if not x.get("hours"): flags.append("no opening hours")
    if x.get("ended"): flags.append("past stated end date")
    return {"result": "needs manual evidence", "flags": flags, "where_to_check": [x.get("website") or "", x.get("source_url", ""), "council warm spaces page"]}
raw_count = len(fresh)
fresh, prev, n_pending = verification_gate(fresh, prev, VER, RUN, "logs/warmspaces_pending.json", ws_autocheck, season_end)
sources["Verification gate"] = {"status": "ok", "scraped": raw_count, "published": len(fresh), "pending": n_pending}
if not fresh or (prev and prev["items"] and len(fresh) < 0.8 * len(prev["items"]) and not os.environ.get("FORCE")):
    append_log(LOG, {"run": RUN, "result": "aborted: source returned too few entries", "sources": sources}); sys.exit(0)
items, closed = merge_lifecycle(prev, fresh, RUN)
write_js(OUT, "WARMSPACES", {"updated": RUN, "items": items, "recently_closed": closed, "sources": sources})
append_log(LOG, {"run": RUN, "result": "ok", "items": len(items), "ended": sum(x.get("ended", False) for x in items), "stale": sum(x["stale"] for x in items), "recently_closed": len(closed), "sources": sources})
print(len(items), "warm spaces")
