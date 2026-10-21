"""Shelters layer scraper. Separate from food banks (data.js) and warm spaces.
Writes shelters.js and logs/shelters_log.json. Never invents data: every entry comes from a source record."""
import json, sys, os, urllib.parse
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
               "Homeless England (Homeless Link)": "listings have no address/postcode, so they cannot be pinned without guessing",
               "LHF Atlas": "map is an interactive app with no public data export; London-only",
               "Crisis / Shelter / St Mungo's / Thames Reach": "no public shelter directory; services are via referral (council/outreach)"}.items():
    sources[k] = {"status": "not scraped: " + why}
need = [(x["id"], x["lat"], x["lng"]) for x in fresh if not x["postcode"]]
for k, pc in reverse_postcodes(need).items():
    for x in fresh:
        if x["id"] == k: x["postcode"] = pc; x["postcode_note"] = "nearest postcode (postcodes.io)"
prev = load_js(OUT, "SHELTERS")
if prev and len(fresh) < 0.8 * len(prev["items"]) and not os.environ.get("FORCE"):
    append_log(LOG, {"run": RUN, "result": "aborted: source returned too few entries", "sources": sources}); sys.exit(0)
items, closed = merge_lifecycle(prev, fresh, RUN)
write_js(OUT, "SHELTERS", {"updated": RUN, "items": items, "recently_closed": closed, "sources": sources})
append_log(LOG, {"run": RUN, "result": "ok", "items": len(items), "stale": sum(x["stale"] for x in items), "recently_closed": len(closed), "sources": sources})
print(len(items), "shelters")
