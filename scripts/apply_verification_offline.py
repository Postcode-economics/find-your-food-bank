"""Re-apply the verification gate to the current layer files without re-scraping (used 2026-10-21)."""
import json, sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import *
RUN = today()
for OUT, VAR, VF, PEND in [("shelters.js", "SHELTERS", "overrides/shelters_verified.json", "logs/shelters_pending.json"),
                           ("warmspaces.js", "WARMSPACES", "overrides/warmspaces_verified.json", "logs/warmspaces_pending.json")]:
    cur = load_js(OUT, VAR); fresh = [dict(x, last_verified=RUN) for x in cur["items"]]
    pub, prev, n = verification_gate(fresh, cur, load_verified(VF), RUN, PEND)
    items, closed = merge_lifecycle(prev, pub, RUN)
    cur["sources"]["Verification gate"] = {"status": "ok", "scraped": len(fresh), "published": len(items), "pending": n}
    write_js(OUT, VAR, {"updated": RUN, "items": items, "recently_closed": closed, "sources": cur["sources"]})
    print(OUT, len(fresh), "->", len(items), "published,", n, "pending")
