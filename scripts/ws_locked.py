"""Locked hand fixes for warm spaces (overrides/warmspaces_locked.json).
Applied as the last step of build_warmspaces.py so the Warm Welcome feed cannot undo them.
Never removes a listing: entries only overwrite the named fields of listings that exist."""
import json, os
PATH = "overrides/warmspaces_locked.json"
FIELDS = ("address", "postcode", "hours", "notes", "website", "scheme_start", "scheme_end", "scheme_dates", "ended")
def load(path=PATH, key="items"):
    if not os.path.exists(path): return []
    return json.load(open(path, encoding="utf-8")).get(key, [])
def load_held(path=PATH):
    """Fixes not confirmed on the venue's own site: never applied, only listed for Dean."""
    return load(path, "held")
def apply(items, locked=None):
    """Mutates items in place; returns ids applied. Same length list in, same out."""
    locked = load() if locked is None else locked
    by = {x["id"]: x for x in items}; done = []
    for e in locked:
        x = by.get(e["id"])
        if not x: continue
        for k, v in e.get("set", {}).items():
            if k in FIELDS: x[k] = json.loads(json.dumps(v))
        if e.get("call_before_you_go"): x["call_before_you_go"] = True
        x["locked_fix"] = e.get("checked_on", True)
        done.append(e["id"])
    return done
def review_lines(locked=None, held=None):
    locked = load() if locked is None else locked
    held = load_held() if held is None else held
    L = []
    for e in locked:
        L.append(f"- LOCKED FIX **{e['name']}** ({e['id']}): {e.get('reason','')}. Set: " + ", ".join(sorted(e.get('set', {}))) + f". Source: {e.get('evidence_url','')} “{e.get('quote','')[:160]}”")
        if e.get("review_note"): L.append(f"  - For Dean: {e['review_note']}")
    for e in held:
        L.append(f"- HELD, NOT APPLIED **{e['name']}** ({e['id']}): {e.get('reason','')}. Proposed: " + ", ".join(sorted(e.get('proposed', {}))) + f". Own site: {e.get('own_site_url','')}")
        if e.get("review_note"): L.append(f"  - For Dean: {e['review_note']}")
    return L
