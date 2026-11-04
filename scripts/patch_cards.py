"""Scoped card patch (Dean, 4 Nov 2026): rebuild ONLY the named shelter cards inside the published
shelters.js from the hand files (overrides/shelters_manual.json + shelters_verified.json). No fetching.
- Only ids already on the map; no adds, no removals, no closures.
- Phones never change here (rule 45): the published phone/council lines are kept.
- Hours, address, postcode, pin and card text come from the hand files; hours normalised as in the build.
- place_lock.final_lock runs last; no_pin cards never carry postcode/lat/lng.
- Whole-file guard: anything other than the named cards (and the 'updated' date) changing aborts.
Usage: python scripts/patch_cards.py man-ss-a,man-ss-b [--root DIR] [--dry-run]
The workflow (patch-shelter-cards.yml) then runs the same gates as a refresh on the whole file."""
import copy, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import place_lock, hours_norm, phone_lock
from common import load_js, write_js

CARD_FIELDS = ("name", "address", "postcode", "lat", "lng", "hours", "hours_quote", "hours_source", "hours_checked",
               "referral", "referral_route", "beds", "groups", "who_for", "facilities", "facilities_quote",
               "facilities_source", "season", "access_type", "kind", "website", "source_url", "wheelchair",
               "wheelchair_quote", "wheelchair_source", "age_range", "discovery_url", "discovery_label")
DATE_FIELDS = ("last_verified", "checked_on", "last_checked")
NEVER = ("phone", "phone_label", "tel") + place_lock.LOCKED_CONTACT

class PatchError(Exception):
    pass

def _stated(v):
    return place_lock._stated(v)

def patch(ids, root=".", today=None):
    today = today or datetime.date.today().isoformat()
    path = os.path.join(root, "shelters.js")
    data = load_js(path, "SHELTERS")
    if not data or not isinstance(data.get("items"), list):
        raise PatchError("shelters.js missing or unreadable")
    before = copy.deepcopy(data["items"])
    man = {r["id"]: r for r in json.load(open(os.path.join(root, "overrides", "shelters_manual.json"), encoding="utf-8"))
           if isinstance(r, dict) and r.get("id")}
    ver = json.load(open(os.path.join(root, "overrides", "shelters_verified.json"), encoding="utf-8"))
    by = {x["id"]: x for x in data["items"]}
    ids = [i.strip() for i in ids if i and i.strip()]
    if not ids:
        raise PatchError("no ids given")
    missing = [i for i in ids if i not in by]
    if missing:
        raise PatchError("not on the map (patch never adds): %s" % ", ".join(missing))
    nohand = [i for i in ids if i not in man and i not in ver]
    if nohand:
        raise PatchError("no hand record: %s" % ", ".join(nohand))
    for i in ids:
        x = by[i]; m = man.get(i) or {}; v = ver.get(i) or {}
        for f in CARD_FIELDS:
            if f in m and _stated(m[f]):
                x[f] = m[f]
        for f in ("address", "postcode", "lat", "lng", "hours"):
            if f in v and _stated(v[f]):
                x[f] = v[f]
        if v.get("access"):
            x["referral"] = v["access"][0].upper() + v["access"][1:]
            if x.get("card_type") == "referral_hostel" and not (m.get("referral_route")):
                x["referral_route"] = x["referral"]
        if x.get("card_type") == "referral_hostel" and m.get("referral_route"):
            x["referral_route"] = m["referral_route"]
        for f in DATE_FIELDS:
            x[f] = today
        if v.get("verified_on"):
            x["verified_on"] = today
    hours_norm.apply([by[i] for i in ids], "hours")
    blocked = place_lock.final_lock([by[i] for i in ids], before, place_lock.hands(root, "shelters"), "shelters",
                                    baseline=((phone_lock.load(root) or {}).get("listings")))
    # phones never change in a patch, even to a hand value
    old = {x["id"]: x for x in before}
    for i in ids:
        for f in NEVER:
            if by[i].get(f) != old[i].get(f):
                place_lock._restore(by[i], f, old[i].get(f))
    # whole-file guard
    if [x.get("id") for x in data["items"]] != [x.get("id") for x in before]:
        raise PatchError("card list changed (adds/removals/reorder are not allowed)")
    changed = [x["id"] for x, y in zip(data["items"], before) if json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True)]
    stray = [c for c in changed if c not in ids]
    if stray:
        raise PatchError("cards outside the list changed: %s" % ", ".join(stray))
    for x in data["items"]:
        if x.get("no_pin") and any(k in x for k in ("postcode", "lat", "lng")):
            raise PatchError("no_pin card carries pin fields: %s" % x["id"])
    data["updated"] = today
    return data, changed, blocked

def main(argv):
    root = "."; dry = False; ids = []
    it = iter(argv)
    for a in it:
        if a == "--root": root = next(it)
        elif a == "--dry-run": dry = True
        else: ids += a.split(",")
    try:
        data, changed, blocked = patch(ids, root)
    except PatchError as e:
        print("PATCH REFUSED:", e); return 1
    print("patched:", changed, "| final lock adjustments:", len(blocked))
    if not dry:
        write_js(os.path.join(root, "shelters.js"), "SHELTERS", data)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
