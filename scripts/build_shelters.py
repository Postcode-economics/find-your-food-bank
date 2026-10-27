"""Shelters layer scraper. Separate from food banks (data.js) and warm spaces.
Writes shelters.js and logs/shelters_log.json. Never invents data: every entry comes from a source record."""
import json, sys, os, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026: refresh stops if overrides/auto_apply_rules.json is missing
sys.path.insert(0, os.path.dirname(__file__))
from common import *
RUN = today()
OUT, LOG = "shelters.js", "logs/shelters_log.json"
Q = """[out:json][timeout:180];area["ISO3166-1"="GB"]->.uk;
(nwr["social_facility"~"shelter"]["social_facility:for"~"homeless"](area.uk);
 nwr["amenity"="shelter"]["shelter_type"="homeless"](area.uk);
 nwr["social_facility:for"~"homeless"]["social_facility"~"housing|group_home|assisted_living"](area.uk););out center tags;"""
sources = {}
def groups(t):
    s = ";".join([t.get("social_facility:for", ""), t.get("gender", ""), t.get("description", ""), t.get("name", "")]).lower()
    g = []
    if "women" in s or "female" in s: g.append("women")
    if ("men" in s.replace("women", "")) or "male" in s.replace("female", ""): g.append("men")
    if "famil" in s or "child" in s: g.append("families")
    if "youth" in s or "young" in s or "juvenile" in s: g.append("young people")
    return g
def season(t):
    s = " ".join([t.get("seasonal", ""), t.get("opening_hours", ""), t.get("name", ""), t.get("description", "")]).lower()
    if t.get("seasonal") in ("winter",) or "winter" in s or "swep" in s or "cold weather" in s: return "Winter-only"
    if t.get("seasonal") == "no" or t.get("opening_hours", "").startswith("24/7"): return "Year-round"
    return "Not stated"
fresh = []
try:
    els = None
    for ep in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]:
        try: els = json.loads(get(ep, ("data=" + urllib.parse.quote(Q)).encode(), timeout=240))["elements"]; break
        except Exception as e2: last = e2
    if els is None: raise last
    for e in els:
        t = e.get("tags", {}); lat = e.get("lat") or e.get("center", {}).get("lat"); lng = e.get("lon") or e.get("center", {}).get("lon")
        if not lat or not t.get("name"): continue
        addr = ", ".join(x for x in [" ".join(filter(None, [t.get("addr:housenumber"), t.get("addr:street")])), t.get("addr:city") or t.get("addr:town")] if x)
        cap = t.get("capacity") or t.get("beds")
        fresh.append({"id": f"osm-{e['type']}-{e['id']}", "name": t["name"], "address": addr, "postcode": (t.get("addr:postcode") or "").upper(),
            "lat": lat, "lng": lng, "phone": t.get("phone") or t.get("contact:phone") or "", "website": t.get("website") or t.get("contact:website") or "",
            "hours": t.get("opening_hours", ""), "referral": t.get("description", "") if "referr" in t.get("description", "").lower() else "",
            "beds": cap or "", "groups": groups(t), "season": season(t), "operator": t.get("operator", ""),
            "flag_closed": t.get("disused") == "yes" or t.get("opening_hours") == "closed",
            "source": "OpenStreetMap", "source_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}", "last_verified": RUN})
    sources["OpenStreetMap (Overpass)"] = {"status": "ok", "count": len(fresh)}
except Exception as ex:
    sources["OpenStreetMap (Overpass)"] = {"status": f"failed: {ex}"}
# Manually verified entries from charity / council pages and self-registrations approved by the owner.
man = json.load(open("overrides/shelters_manual.json")) if os.path.exists("overrides/shelters_manual.json") else []
for m in man:
    m.setdefault("groups", []); m.setdefault("season", "Not stated"); fresh.append(m)
sources["Manual (verified from source pages)"] = {"status": "ok", "count": len(man)}
for k, why in {"nightshelter.org.uk": "domain is parked (redirects to a lander page); no data",
               "StreetLink (thestreetlink.org.uk)": "403 to automated requests; it is a referral service, not a shelter directory",
               "LHF Atlas": "map is an interactive app with no public data export; London-only",
               "Crisis / Shelter / St Mungo's / Thames Reach": "no public shelter directory; services are via referral (council/outreach)"}.items():
    sources[k] = {"status": "not scraped: " + why}
need = [(x["id"], x["lat"], x["lng"]) for x in fresh if not x["postcode"]]
for k, pc in reverse_postcodes(need).items():
    for x in fresh:
        if x["id"] == k: x["postcode"] = pc; x["postcode_note"] = "nearest postcode (postcodes.io)"
prev = load_js(OUT, "SHELTERS")
# Verification gate: publish only allowlisted shelters; new finds go to logs/shelters_pending.json.
VER = load_verified("overrides/shelters_verified.json")
HE_HINT = "https://homeless.org.uk/homeless-england/"
def shelter_autocheck(x):
    # Bar (Dean, 21 Oct 2026): a credible council/operator/charity/official page must show it is a homeless
    # shelter, night shelter or emergency accommodation, open in a stated period, with opening or access
    # times/route. Day centres without beds do not count. This pre-check only flags; it never publishes.
    flags = []
    if x.get("flag_closed"): flags.append("tagged closed/disused in OSM")
    n = x["name"].lower()
    if any(w in n for w in ["hotel", "alms", "care home", "day centre", "refugee", "foyer"]): flags.append("name suggests not a shelter")
    if any(w in n for w in ["night shelter", "winter shelter", "swep", "cold weather"]): flags.append("seasonal: needs stated open period")
    if not x.get("website"): flags.append("no operator website in source")
    return {"result": "needs manual evidence", "flags": flags, "where_to_check": [x.get("website") or "", HE_HINT, "council homelessness page"]}
# ---- discovery every run: Homeless Link 'Find help' + OSM finds not on our lists -> own-site check -> tier 2 or flagged ----
import discover, directories
UNV = load_verified("overrides/shelters_unverified.json")
known = set(VER) | set(UNV)
hl, st = directories.homeless_link(known=known)
sources["Homeless Link 'Find help' (homeless.org.uk/homeless-england)"] = st
osm_new = [x for x in fresh if x["id"] not in known and x["id"].startswith("osm-")]
base = [x for x in fresh if x["id"] in known]
add, dlog = discover.discover_layer(osm_new + hl, base, "sh", RUN, UNV, "logs/shelters_discovery.json")
have = {x["id"] for x in fresh}
fresh += [c for c in add if c["id"] not in have]
sources["Discovery"] = {"status": "ok", "candidates": dlog["candidates"], "new": dlog["new"], "added_unverified": len(dlog["added"]), "flagged": len(dlog["flagged"])}
raw_count = len(fresh)
fresh, prev, n_pending = verification_gate(fresh, prev, VER, RUN, "logs/shelters_pending.json", unverified=UNV, autocheck=shelter_autocheck)
from hours_fix import apply_phone
for x in fresh: apply_phone(x)  # one valid UK number for tel:, others shown as text; invalid hidden
# times cross-check on every published shelter's OWN site this run (closed -> removed; unconfirmed -> times withheld)
tlog = discover.cross_check_times(fresh, "sh", "hours")
gone = [x["id"] for x in fresh if x.get("_own_site_closed")]
fresh = [x for x in fresh if not x.pop("_own_site_closed", None)]
json.dump(tlog, open("logs/shelters_times_check.json", "w"), indent=0, ensure_ascii=False)
import hours_norm  # stored hours: Mon-Sun day table (OSM text converted) or the place's own wording once
sources["Hours normalised"] = {"status": "ok", "changed": hours_norm.apply(fresh, "hours")}
sources["Own-site times check"] = {"status": "ok", **discover.summary(tlog), "removed_closed": gone}
sources["Verification gate"] = {"status": "ok", "scraped": raw_count, "published": len(fresh), "pending": n_pending, "kept_on_48h_grace": [g["id"] for g in getattr(verification_gate, "graced", [])]}
if not fresh or (prev and prev["items"] and len(fresh) < 0.8 * len(prev["items"]) and not os.environ.get("FORCE")):
    append_log(LOG, {"run": RUN, "result": "aborted: source returned too few entries", "sources": sources}); sys.exit(0)
items, closed = merge_lifecycle(prev, fresh, RUN)
import seasonal  # winter night shelters: 'Opens <date>' until the stated start, expire after the stated end
for x in items:
    if not (x.get("scheme_start") or x.get("scheme_end")):
        d = seasonal.parse(" ".join(str(x.get(k) or "") for k in ("season", "hours", "referral")))
        if d["start"] or d["end"]: x["scheme_start"], x["scheme_end"] = d["start"], d["end"]
items, expired = seasonal.apply(items, RUN, closed)
for x in items:
    if x.get("upcoming") and x.get("scheme_dates"): x["season"] = "Winter-only (" + x["scheme_dates"] + ")"
sources["Seasonal dates"] = {"status": "ok", "upcoming": sum(bool(x.get("upcoming")) for x in items), "expired": [x["id"] for x in expired]}
import shelter_contacts  # manual numbers/emails + council referral lines (overrides/shelters_contacts.json) survive every refresh
sources["Manual contacts"] = {"status": "ok", "phones_filled": shelter_contacts.apply(items), "missing_any_number": shelter_contacts.check(items)}
import phone_lock  # frozen numbers, and no daytime council line without a verified out-of-hours number
for x in items: phone_lock.settle_council(x)
phone_lock.guard(items, phone_lock.ROOT, via="refresh", source="feed refresh", layer="shelters", persist_new=not os.environ.get("DRY_RUN"))
if os.environ.get("DRY_RUN"): print("DRY RUN:", len(items), "shelters", json.dumps(sources)[:1500]); sys.exit(0)
write_js(OUT, "SHELTERS", {"updated": RUN, "items": items, "recently_closed": closed, "sources": sources})
append_log(LOG, {"run": RUN, "result": "ok", "items": len(items), "stale": sum(x["stale"] for x in items), "recently_closed": len(closed), "sources": sources})
print(len(items), "shelters")
