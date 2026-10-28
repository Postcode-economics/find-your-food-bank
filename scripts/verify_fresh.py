"""Publish guard. Exits non-zero (blocking the commit/publish step) unless every published shelter and warm space
was re-fetched and confirmed in THIS run: each item needs fetched_at within MAX_AGE and an ok entry in the recheck log.
Two labelled exceptions, each checked strictly: 48h grace (source briefly unreachable), and warm spaces carried forward
this run by scripts/carry_forward.py (Dean, 28 Oct: shown with 'call before you go', never presented as re-confirmed)."""
import json, sys, os, datetime, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from common import load_js, is_transient, GRACE_HOURS
MAX_AGE = datetime.timedelta(hours=int(os.environ.get("MAX_AGE_HOURS", "2")))
now = datetime.datetime.now(datetime.timezone.utc); bad = []
ALL = {"foodbanks": ("data.full.js", "FB_DATA", "logs/foodbank_recheck.json"), "shelters": ("shelters.js", "SHELTERS", "logs/shelters_recheck.json"), "warmspaces": ("warmspaces.js", "WARMSPACES", "logs/warmspaces_recheck.json")}
CLOSED = ("source now says closed/ended", "feed says ended")

def published(out):
    """id -> item in the last committed copy of `out` (git HEAD), or None if it cannot be read."""
    try:
        t = subprocess.check_output(["git", "show", "HEAD:" + out], text=True, stderr=subprocess.DEVNULL)
        return {i["id"]: i for i in json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]}
    except Exception: return None

def carry_log():
    """logs/warmspaces_carry_forward.json, or {} if missing/unreadable."""
    try: return json.load(open("logs/warmspaces_carry_forward.json"))
    except Exception: return {}

def logged_this_run(x, lg):
    """Same rule as refresh_guard.ws_not_restorable: match the workflow run id when both sides have one, else the run day."""
    import carry_forward as CF
    rid = CF.run_id()
    same = (lg.get("run_id") == rid) if (rid and lg.get("run_id")) else (lg.get("run") == x.get("carried_forward"))
    return same and x["id"] in {r.get("id") for r in lg.get("carried", [])}

def carry_problem(x, r, prev, lg):
    """None if x is an honest carry-forward: labelled for the public, logged this run, previously published with the same
    fetched_at (so it never claims a newer confirmation), and its source did not say closed/ended this run."""
    if not (x.get("call_check") is True and x.get("carried_forward") and x.get("carried_note")): return "not confirmed this run"
    if not logged_this_run(x, lg): return "carried but not in this run's carry-forward log"
    if prev is None: return "carried but the last published warmspaces.js could not be read"
    if x["id"] not in prev: return "carried but was not published before"
    if x.get("fetched_at") != prev[x["id"]].get("fetched_at"): return "carried but fetched_at differs from the published copy"
    if r and (r.get("reason") or "") in CLOSED: return "carried but source says closed/ended this run"
    return None

for OUT, VAR, LOG in [ALL[a] for a in (sys.argv[1:] or ALL)]:
    if not os.path.exists(LOG): bad.append(f"{LOG} missing"); continue
    rc = json.load(open(LOG)); run = rc.get("_run", {})
    if not run or now - datetime.datetime.fromisoformat(run["fetched_at"]) > MAX_AGE: bad.append(f"{LOG}: no recheck in the last {MAX_AGE}")
    prev = lg = None
    for x in load_js(OUT, VAR)["items"]:
        r = rc.get(x["id"])
        if x.get("grace"):  # 48h grace: re-fetched this run but source briefly unreachable; last real confirmation < 48h ago
            try: age = now - datetime.datetime.fromisoformat(x.get("fetched_at", ""))
            except Exception: age = None
            if not (r and is_transient(r) and age is not None and age <= datetime.timedelta(hours=GRACE_HOURS)):
                bad.append(f"{OUT}: {x['id']} on grace but not eligible (unreachable <48h after last confirmation)")
            continue
        if not r or not r.get("ok"):
            if OUT == "warmspaces.js" and x.get("carried_forward"):
                if lg is None: prev, lg = published(OUT), carry_log()
                why = carry_problem(x, r, prev, lg)
                if why: bad.append(f"{OUT}: {x['id']} {why}")
                continue
            bad.append(f"{OUT}: {x['id']} not confirmed this run")
        elif x.get("fetched_at") != r.get("fetched_at"): bad.append(f"{OUT}: {x['id']} fetched_at does not match this run")
if bad:
    print("REFUSING TO PUBLISH:\n" + "\n".join(bad[:50])); sys.exit(1)
print("verify_fresh: all published entries confirmed this run (or labelled carry-forward / 48h grace)")
