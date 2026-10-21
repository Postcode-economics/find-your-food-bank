"""v3 (2026-10-21): two tiers. Re-apply the gate from pre-verification data (e8220fb) + manual overrides, no scraping.
Usage: git show e8220fb:shelters.js > /tmp/sh0.js; git show e8220fb:warmspaces.js > /tmp/ws0.js; python3 scripts/apply_verification_offline_v3.py /tmp/sh0.js /tmp/ws0.js"""
import json, sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import *
RUN = today()
def season_end(v):
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01")); return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"
def load_any(p):
    s = open(p).read(); return json.loads(s[s.index("{"):s.rindex("}") + 1])
for SRC, OUT, VAR, n, VU in [(sys.argv[1], "shelters.js", "SHELTERS", "shelters", None), (sys.argv[2], "warmspaces.js", "WARMSPACES", "warmspaces", season_end)]:
    fresh = [dict(x, last_verified=RUN) for x in load_any(SRC)["items"]]
    mp = f"overrides/{n}_manual.json"
    if os.path.exists(mp): fresh += json.load(open(mp))
    cur = load_js(OUT, VAR)
    pub, prev, k = verification_gate(fresh, cur, load_verified(f"overrides/{n}_verified.json"), RUN, f"logs/{n}_pending.json", valid_until=VU, unverified=load_verified(f"overrides/{n}_unverified.json"))
    items, closed = merge_lifecycle(prev, pub, RUN)
    src = cur["sources"]; src["Verification gate"] = {"status": "ok", "scraped": len(fresh), "published": len(items), "verified": sum(x.get("tier") == "verified" for x in items), "unverified": sum(x.get("tier") == "unverified" for x in items), "pending": k}
    write_js(OUT, VAR, {"updated": RUN, "items": items, "recently_closed": closed, "sources": src})
    print(OUT, src["Verification gate"])
