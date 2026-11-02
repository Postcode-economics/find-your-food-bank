"""Publish guard. Exits non-zero (blocking the commit/publish step) unless every published shelter and warm space
was re-fetched and confirmed in THIS run: each item needs fetched_at within MAX_AGE and an ok entry in the recheck log.
Three labelled exceptions, each checked strictly per item: 48h grace (source briefly unreachable), hand-checked rows
kept through a blocked fetch (kept_fetch_blocked, Dean 1 Nov: 14 days), and warm spaces carried forward this run by scripts/carry_forward.py (Dean, 28 Oct: shown with 'call before you go', never presented as re-confirmed).
Shelters only (2 Nov 2026): a per-place problem drops that place for this run and the rest still publishes. The place is listed in
reports/manual_review.md and tried again next run. A whole-layer problem (no recheck, a file that will not parse, an empty result,
or a count more than 20% below the last published file) still refuses the publish. Food banks and warm spaces are unchanged."""
import json, sys, os, datetime, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from common import load_js, is_transient, GRACE_HOURS, is_fetch_blocked, manual_checked_days, MANUAL_BLOCK_DAYS, record_shelter_holds
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

KEEP_SAME = ("fetched_at", "phone", "address", "hours", "postcode")
def blocked_problem(x, r, prev):
    """None if x is an honest hand-checked keep (common.verification_gate, MANUAL_BLOCK_DAYS): hand-checked within the
    window, this run's fetch genuinely blocked (not a page that loaded), already published, and nothing changed."""
    md = manual_checked_days(x, now)
    if md is None: return "not a hand-checked manual row"
    if not (0 <= md <= MANUAL_BLOCK_DAYS): return f"hand-checked {md} days ago (limit {MANUAL_BLOCK_DAYS})"
    if not (r and is_fetch_blocked(r)): return f"this run's fetch was not blocked ({(r or {}).get('http')}, {(r or {}).get('reason')})"
    if prev is None: return "the published shelters.js could not be read"
    if x["id"] not in prev: return "was not published before"
    diff = [k for k in KEEP_SAME if x.get(k) != prev[x["id"]].get(k)]
    if diff: return "differs from the published copy: " + ", ".join(diff)
    return None

SHRINK = 0.8  # same floor as build_shelters: a result more than 20% below the last published file is a whole-layer failure
held_rows = []
def split_js(path):
    t = open(path, encoding="utf-8").read()
    a, b = t.index("{"), t.rindex("}") + 1
    return t[:a], json.loads(t[a:b]), t[b:]
def place_problem(x, r, OUT, state):
    """A reason this one place cannot be published, or None. Does not decide whether the whole run fails."""
    if x.get("grace") and x.get("kept_fetch_blocked"):
        if state["prev"] is None: state["prev"] = published(OUT)
        why = blocked_problem(x, r, state["prev"])
        return f"{OUT}: {x['id']} kept through blocked fetch but not eligible: {why}" if why else None
    if x.get("grace"):  # 48h grace: re-fetched this run but source briefly unreachable; last real confirmation < 48h ago
        try: age = now - datetime.datetime.fromisoformat(x.get("fetched_at", ""))
        except Exception: age = None
        if not (r and is_transient(r)): return f"{OUT}: {x['id']} on 48h grace but this run's failure is not a brief outage ({(r or {}).get('http')}, {(r or {}).get('reason')})"
        if age is None or age > datetime.timedelta(hours=GRACE_HOURS): return f"{OUT}: {x['id']} on 48h grace but last confirmation is older than {GRACE_HOURS}h"
        return None
    if not r or not r.get("ok"):
        if OUT == "warmspaces.js" and x.get("carried_forward"):
            if state["lg"] is None: state["prev"], state["lg"] = published(OUT), carry_log()
            why = carry_problem(x, r, state["prev"], state["lg"])
            return f"{OUT}: {x['id']} {why}" if why else None
        return f"{OUT}: {x['id']} not confirmed this run"
    if x.get("fetched_at") != r.get("fetched_at"): return f"{OUT}: {x['id']} fetched_at does not match this run"
    return None
for OUT, VAR, LOG in [ALL[a] for a in (sys.argv[1:] or ALL)]:
    if not os.path.exists(LOG): bad.append(f"{LOG} missing"); continue
    try: rc = json.load(open(LOG))
    except Exception as e: bad.append(f"{LOG}: will not parse ({e.__class__.__name__})"); continue
    run = rc.get("_run", {})
    try: fresh_run = bool(run) and now - datetime.datetime.fromisoformat(run["fetched_at"]) <= MAX_AGE
    except Exception: fresh_run = False
    if not fresh_run: bad.append(f"{LOG}: no recheck in the last {MAX_AGE}"); continue
    if not os.path.exists(OUT): bad.append(f"{OUT}: missing"); continue
    try: pre, data, post = split_js(OUT); items = data["items"]
    except Exception as e: bad.append(f"{OUT}: will not parse ({e.__class__.__name__})"); continue
    state = {"prev": None, "lg": None}
    problems = []
    for x in items:
        msg = place_problem(x, rc.get(x["id"]), OUT, state)
        if msg: problems.append((x, msg))
    if OUT != "shelters.js":
        bad.extend(msg for _, msg in problems); continue
    if not problems: continue
    drop = {x["id"] for x, _ in problems}
    kept = [x for x in items if x["id"] not in drop]
    base = published(OUT)
    base_n = len(base) if base is not None else None
    if not kept:
        bad.append(f"{OUT}: empty after holding {len(drop)} place(s) this run")
        bad.extend(msg for _, msg in problems)
    elif base_n and len(kept) < SHRINK * base_n:
        bad.append(f"{OUT}: count {len(kept)} is more than 20% below last published {base_n}")
        bad.extend(msg for _, msg in problems)
    else:
        data["items"] = kept
        open(OUT, "w", encoding="utf-8").write(pre + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + post)
        for x, msg in problems:
            prefix = "%s: %s " % (OUT, x["id"])
            held_rows.append({"id": x["id"], "name": x.get("name") or x["id"], "reason": msg[len(prefix):] if msg.startswith(prefix) else msg})
        print("shelters held this run (publish continues):\n" + "\n".join(msg for _, msg in problems[:50]))
if held_rows and not bad:
    record_shelter_holds(held_rows, replace=False)
    try:
        pend = "logs/shelters_pending.json"
        cur = json.load(open(pend)) if os.path.exists(pend) else []
        have = {p.get("id") for p in cur if isinstance(p, dict)}
        day = datetime.date.today().isoformat()
        for r in held_rows:
            if r["id"] not in have: cur.append({"id": r["id"], "name": r["name"], "first_seen": day, "reason": r["reason"]})
        json.dump(cur, open(pend, "w"), indent=1, ensure_ascii=False)
    except Exception as e:
        print("shelters pending note skipped:", e)
if bad:
    print("REFUSING TO PUBLISH:\n" + "\n".join(bad[:50])); sys.exit(1)
print("verify_fresh: all published entries confirmed this run (or labelled carry-forward / 48h grace)")
