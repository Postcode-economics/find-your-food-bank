"""Warm Spaces layer scraper. Separate from food banks and shelters.
Writes warmspaces.js and logs/warmspaces_log.json. Seasonal: entries whose scheme end date has passed are
marked 'ended' (shown greyed); they become active again automatically when a new listing/date appears."""
import json, seasonal, sys, os, re, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026: refresh stops if overrides/auto_apply_rules.json is missing
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from hours_fix import fix_hours, phone_ok, apply_phone
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
    ss = seasonal.parse(desc)  # start/end from the listing's own wording (pop-ups: 'SPACE OPENING ON 7th December 2026')
    end = ss["end"] or end_date(desc)
    if end and end == ss["start"]: end = ""  # an opening date is not an end date
    fresh.append({"id": f"ww-{x['id']}", "name": x["name"].strip(), "address": (x.get("streetaddress") or "").strip(), "postcode": postcode(x.get("streetaddress")),
        "lat": x["loc_lat"], "lng": x["loc_long"], "phone": (x.get("phone") or "").strip(), "website": (x.get("website") or "").strip(),
        "hours": hours, "provided": provided, "booking": booking, "notes": desc[:240],
        "scheme_start": ss["start"], "scheme_end": end, "scheme_dates": ("Until " + end) if end else "Not stated by source",
        "ended": bool(end and end < RUN), "source": "Warm Welcome", "source_url": page, "last_verified": RUN})
FIX = {f["id"]: f for f in json.load(open("overrides/warmspaces_fixes.json"))} if os.path.exists("overrides/warmspaces_fixes.json") else {}
for x in fresh:  # audited pin/postcode corrections, re-applied every run (fail-safe: only known keys)
    for k in ("lat", "lng", "postcode", "address"):
        if x["id"] in FIX and k in FIX[x["id"]]: x[k] = FIX[x["id"]][k]
man = json.load(open("overrides/warmspaces_manual.json")) if os.path.exists("overrides/warmspaces_manual.json") else []
for m in man:
    m["ended"] = bool(m.get("scheme_end") and m["scheme_end"] < RUN); fresh.append(m)
sources["Manual (council pages, press releases, approved self-registrations)"] = {"status": "ok", "count": len(man)}
for k, why in {"Council warm spaces / warm hubs pages (~360 councils)": "no common format; most councils now list via the Warm Welcome map (already included). Individual council pages to be added via overrides/warmspaces_manual.json with source URL",
               "warmspaces.org (Warm Spaces directory)": "inactive since Nov 2024 (per Open Innovations register); site returns 404",
               "Age UK branches, British Red Cross, libraries, church directories": "no machine-readable UK-wide listing; many of these venues are already registered on Warm Welcome"}.items():
    sources[k] = {"status": "not scraped: " + why}
prev = load_js(OUT, "WARMSPACES")
# Verification gate: publish only allowlisted warm spaces (independently confirmed for the current season).
VER = load_verified("overrides/warmspaces_verified.json")
def season_end(v):  # a verification is valid only for the winter season it was made in (to 30 April)
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01"))
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"
def ws_autocheck(x):
    # Bar (Dean, 21 Oct 2026): publish only when a credible source (council, venue's own site, library,
    # church or charity page) states the warm space runs on a given weekday at a given time, and nothing
    # says it has ended/closed/was last winter only. A Warm Welcome listing alone does not count.
    # This pre-check only flags; it never publishes. A human adds evidence_url + day_time_quote.
    flags = []
    if not x.get("hours"): flags.append("no opening hours")
    if x.get("ended"): flags.append("past stated end date")
    w = (x.get("website") or "").lower()
    if not w or "warmwelcome.uk" in w: flags.append("no independent website: Warm Welcome listing alone is not evidence")
    return {"result": "needs manual evidence", "flags": flags, "needs": "credible page with weekday + time, current season",
            "where_to_check": [x.get("website") or "", "council warm spaces page", "achurchnearyou / library page"]}
# ---- discovery every run: Open Innovations aggregator (council + VCS warm space directories) -> own-site check ----
import discover, directories
UNV = load_verified("overrides/warmspaces_unverified.json")
oi, st = directories.open_innovations()
sources["Open Innovations warm spaces aggregator (council/VCS directories)"] = st
add, dlog = discover.discover_layer(oi, fresh, "ws", RUN, UNV, "logs/warmspaces_discovery.json")
fresh += add
# ---- Warm Welcome feed discovery (every run, time-boxed): feed entries not yet on our lists, with their OWN
# website, get the same own-site check as Open Innovations finds. Passes are cached (logs/warmspaces_ww_discovery.json)
# and re-confirmed by recheck.py every run like any tier-2 entry; 2026-27 pop-ups with stated dates go first.
WWLOG = "logs/warmspaces_ww_discovery.json"
wwc = json.load(open(WWLOG)) if os.path.exists(WWLOG) else {"passed": {}, "checked": {}}
for k, u in wwc["passed"].items(): UNV.setdefault(k, u)
known = set(VER) | set(UNV)
pool = [x for x in fresh if x["id"].startswith("ww-") and x["id"] not in known
        and wwc["checked"].get(x["id"], "") < (datetime.date.fromisoformat(RUN) - datetime.timedelta(days=7)).isoformat() and not x.get("ended")]
pool.sort(key=lambda x: (not (x.get("scheme_start") or x.get("scheme_end")), wwc["checked"].get(x["id"], ""), x["id"]))
# Full Warm Welcome feed (Dean, 23 Oct): every not-yet-known listing is checked, in chunks, until a time box runs out
# (WW_DISCOVERY_SECONDS, default 20 min); whatever is left is first in line next run. WW_DISCOVERY_BUDGET caps the count (0 = all).
import time as _t
budget = int(os.environ.get("WW_DISCOVERY_BUDGET", "0")) or len(pool)
tbox = _t.time() + int(os.environ.get("WW_DISCOVERY_SECONDS", "1200"))
before = set(UNV); wadd, batch = [], []
wlog = {"candidates": 0, "new": 0, "added": [], "flagged": [], "rejected": []}
for s0 in range(0, min(budget, len(pool)), 150):
    if _t.time() > tbox: break
    chunk = [dict(x, directory="Warm Welcome", directory_url=x["source_url"]) for x in pool[s0:min(s0 + 150, budget)]]
    try:
        a, l = discover.discover_layer(chunk, [x for x in fresh if x["id"] in known] + wadd, "ws", RUN, UNV, "logs/warmspaces_ww_discovery_run.json")
    except Exception as ex:
        sources["Warm Welcome feed discovery"] = {"status": "chunk failed: " + str(ex)[:80]}; break
    wadd += a; batch += chunk
    for k in ("candidates", "new"): wlog[k] += l[k]
    for k in ("added", "flagged", "rejected"): wlog[k] += l[k]
    for x in chunk: wwc["checked"][x["id"]] = RUN
for k in set(UNV) - before: wwc["passed"][k] = UNV[k]
json.dump(wwc, open(WWLOG, "w"), indent=0, ensure_ascii=False)
sources["Warm Welcome feed discovery"] = {"status": "ok", "pool": len(pool), "checked_this_run": len(batch), "added_this_run": len(wlog["added"]), "queued_this_run": len(wlog["flagged"]), "rejected_this_run": len(wlog["rejected"]), "passed_total": len(wwc["passed"])}
sources["Discovery"] = {"status": "ok", "candidates": dlog["candidates"], "new": dlog["new"], "added_unverified": len(dlog["added"]), "flagged": len(dlog["flagged"])}
HFIX = []
def clean(x):  # am/pm fix for 12h-clock times stored as 24h, and hide phones with fewer than 10 digits
    h, ch = fix_hours(x.get("hours"))
    if ch: x["hours"] = h; HFIX.append({"id": x["id"], "name": x["name"], "changes": ch})
    apply_phone(x)  # one valid UK number for tel:, others shown as text; invalid hidden
    return x
fresh = [clean(x) for x in fresh]
raw_count = len(fresh)
fresh, prev, n_pending = verification_gate(fresh, prev, VER, RUN, "logs/warmspaces_pending.json", unverified=UNV, autocheck=ws_autocheck, valid_until=season_end)
fresh = [clean(x) for x in fresh]  # again: verified overrides can set hours/phone
sources["am/pm hours fix"] = {"status": "ok", "entries_fixed": len({c['id'] for c in HFIX}), "detail": HFIX[:60]}
tlog = discover.cross_check_times(fresh, "ws", "hours", state_root=".")
gone = [x["id"] for x in fresh if x.get("_own_site_closed")]
fresh = [clean(x) for x in fresh if not x.pop("_own_site_closed", None)]  # and after own-site times updates
json.dump(tlog, open("logs/warmspaces_times_check.json", "w"), indent=0, ensure_ascii=False)
import hours_norm  # stored hours: Mon-Sun order (fixes e.g. Cat and Mouse Library, Central Library) or own wording once
sources["Hours normalised"] = {"status": "ok", "changed": hours_norm.apply(fresh, "hours")}
sources["Own-site times check"] = {"status": "ok", **discover.summary(tlog), "removed_closed": gone}
sources["Verification gate"] = {"status": "ok", "scraped": raw_count, "published": len(fresh), "pending": n_pending, "kept_on_48h_grace": [g["id"] for g in getattr(verification_gate, "graced", [])]}
if not fresh or (prev and prev["items"] and len(fresh) < 0.8 * len(prev["items"]) and not os.environ.get("FORCE")):
    append_log(LOG, {"run": RUN, "result": "aborted: source returned too few entries", "sources": sources}); sys.exit(0)
items, closed = merge_lifecycle(prev, fresh, RUN)
items, expired = seasonal.apply(items, RUN, closed)  # 'Opens <date>' for pop-ups not open yet; ended > 14 days -> recently_closed
sources["Seasonal dates"] = {"status": "ok", "upcoming": sum(bool(x.get("upcoming")) for x in items), "ended_greyed": sum(bool(x.get("ended")) for x in items), "expired": [x["id"] for x in expired]}
EXCL = {e["id"] for e in json.load(open("overrides/warmspaces_exclude.json"))} if os.path.exists("overrides/warmspaces_exclude.json") else set()
items = [x for x in items if x["id"] not in EXCL]; closed = [x for x in closed if x["id"] not in EXCL]  # signed-off removals stay off on every rebuild
sources["Excluded by review"] = {"status": "ok", "ids": sorted(EXCL)}
if os.environ.get("DRY_RUN"): print("DRY RUN:", len(items), "warm spaces", json.dumps(sources)[:1500]); sys.exit(0)
import shelter_contacts  # venue numbers + labelled council fallback (overrides/warmspaces_contacts.json) survive every refresh
sources["Manual contacts"] = {"status": "ok", "phones_filled": shelter_contacts.apply(items, shelter_contacts.load(shelter_contacts.WS)), "missing_any_number": shelter_contacts.check(items)}
import phone_lock  # frozen numbers, and no daytime council line without a verified out-of-hours number
for x in items: phone_lock.settle_council(x)
phone_lock.guard(items, phone_lock.ROOT, via="refresh", source="feed refresh", layer="warmspaces", persist_new=not os.environ.get("DRY_RUN"))
write_js(OUT, "WARMSPACES", {"updated": RUN, "items": items, "recently_closed": closed, "sources": sources})
append_log(LOG, {"run": RUN, "result": "ok", "items": len(items), "ended": sum(x.get("ended", False) for x in items), "stale": sum(x["stale"] for x in items), "recently_closed": len(closed), "sources": sources})
print(len(items), "warm spaces")
