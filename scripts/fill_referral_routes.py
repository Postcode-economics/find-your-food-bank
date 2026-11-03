"""Sweep step (rule 82, repair don't drop): before the gating suite, put back a hand-checked card's missing fields
from its verified data, and a dropped referral line from the card's own checked line. Local only: the sweep does not
push shelters.js or warmspaces.js, so live data is never changed here."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_js, write_js, fill_referral_routes, load_verified, restore_verified_fields
for path, var, ver in [("shelters.js", "SHELTERS", "overrides/shelters_verified.json"),
                       ("warmspaces.js", "WARMSPACES", "overrides/warmspaces_verified.json")]:
    d = load_js(path, var)
    if not d: continue
    items = d.get("items", [])
    restored = restore_verified_fields(items, load_verified(ver))
    filled = fill_referral_routes(items) if path == "shelters.js" else []
    if restored or filled: write_js(path, var, d)
    print(path, "restored from verified data:", restored, "referral_route filled:", filled)
