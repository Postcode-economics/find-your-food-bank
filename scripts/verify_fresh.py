"""Publish guard. Exits non-zero (blocking the commit/publish step) unless every published shelter and warm space
was re-fetched and confirmed in THIS run: each item needs fetched_at within MAX_AGE and an ok entry in the recheck log."""
import json, sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import load_js
MAX_AGE = datetime.timedelta(hours=int(os.environ.get("MAX_AGE_HOURS", "2")))
now = datetime.datetime.now(datetime.timezone.utc); bad = []
ALL = {"foodbanks": ("data.js", "FB_DATA", "logs/foodbank_recheck.json"), "shelters": ("shelters.js", "SHELTERS", "logs/shelters_recheck.json"), "warmspaces": ("warmspaces.js", "WARMSPACES", "logs/warmspaces_recheck.json")}
for OUT, VAR, LOG in [ALL[a] for a in (sys.argv[1:] or ALL)]:
    if not os.path.exists(LOG): bad.append(f"{LOG} missing"); continue
    rc = json.load(open(LOG)); run = rc.get("_run", {})
    if not run or now - datetime.datetime.fromisoformat(run["fetched_at"]) > MAX_AGE: bad.append(f"{LOG}: no recheck in the last {MAX_AGE}")
    for x in load_js(OUT, VAR)["items"]:
        r = rc.get(x["id"])
        if not r or not r.get("ok"): bad.append(f"{OUT}: {x['id']} not confirmed this run")
        elif x.get("fetched_at") != r.get("fetched_at"): bad.append(f"{OUT}: {x['id']} fetched_at does not match this run")
if bad:
    print("REFUSING TO PUBLISH:\n" + "\n".join(bad[:50])); sys.exit(1)
print("verify_fresh: all published entries confirmed this run")
