"""Re-apply the verification gate from the pre-verification layer data (commit e8220fb) without re-scraping.
v2 (2026-10-21): also adds overrides/shelters_manual.json entries and passes season_end for warm spaces.
Usage: git show e8220fb:shelters.js > /tmp/sh0.js; git show e8220fb:warmspaces.js > /tmp/ws0.js; python3 scripts/apply_verification_offline_v2.py /tmp/sh0.js /tmp/ws0.js"""
import json, sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import *
RUN = today()
def season_end(v):
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01"))
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"
def load_any(path, var):
    s = open(path).read(); return json.loads(s[s.index("{"):s.rindex("}") + 1])
for SRC, OUT, VAR, VF, PEND, VU in [(sys.argv[1], "shelters.js", "SHELTERS", "overrides/shelters_verified.json", "logs/shelters_pending.json", None),
                                    (sys.argv[2], "warmspaces.js", "WARMSPACES", "overrides/warmspaces_verified.json", "logs/warmspaces_pending.json", season_end)]:
    base = load_any(SRC, VAR); fresh = [dict(x, last_verified=RUN) for x in base["items"]]
    if VAR == "SHELTERS" and os.path.exists("overrides/shelters_manual.json"):
        fresh += json.load(open("overrides/shelters_manual.json"))
    cur = load_js(OUT, VAR)
    pub, prev, n = verification_gate(fresh, cur, load_verified(VF), RUN, PEND, valid_until=VU)
    items, closed = merge_lifecycle(prev, pub, RUN)
    src = cur["sources"]; src["Verification gate"] = {"status": "ok", "scraped": len(fresh), "published": len(items), "pending": n}
    write_js(OUT, VAR, {"updated": RUN, "items": items, "recently_closed": closed, "sources": src})
    print(OUT, len(fresh), "->", len(items), "published,", n, "pending")
