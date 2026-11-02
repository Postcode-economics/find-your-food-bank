"""Publish guard. A live listing stays when this run could not read its page (blocked, 404, timeout, unread). It is
removed only when its own source says it has closed. A place that was not published before, and whose read failed, is
held for this run so the rest can publish. One place never fails the run.
The run still refuses when the recheck log is missing or stale, a data file will not parse, the result would be empty,
or the count would fall more than 20% below the last published file. Warm spaces carried forward stay labelled
'call before you go' (Dean, 28 Oct) and are not presented as re-confirmed."""
import json, sys, os, datetime, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from common import load_js, source_says_closed, record_layer_holds
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
    """None if a live listing is being kept because this run could not read the page. No age limit and no hand-check requirement.
    A source that says closed is not eligible. A place that was not published before is not eligible."""
    if source_says_closed(r, x): return "source says closed"
    if prev is None: return "the published file could not be read"
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
LAYER_OF = {"shelters.js": "shelters", "warmspaces.js": "warmspaces", "data.full.js": "foodbanks"}
def place_problem(x, r, OUT, state):
    """A reason this one place cannot stay in the file, or None. A live listing stays unless its source says closed."""
    if state["prev"] is None: state["prev"] = published(OUT)
    prev = state["prev"]
    if source_says_closed(r, x):
        return f"{OUT}: {x['id']} source says closed"
    if prev and x["id"] in prev:
        old = prev[x["id"]]
        for k in KEEP_SAME:  # a failed read must not replace the last good phone, address, hours or checked time
            if x.get(k) != old.get(k):
                x[k] = old.get(k); state["rewritten"] = True
        return None
    if x.get("grace") and x.get("kept_fetch_blocked"):
        why = blocked_problem(x, r, prev)
        return f"{OUT}: {x['id']} kept through blocked fetch but not eligible: {why}" if why else None
    if x.get("grace"):
        return None  # the build kept it; there is no grace expiry
    if not r or not r.get("ok"):
        if OUT == "warmspaces.js" and x.get("carried_forward"):
            if state["lg"] is None: state["lg"] = carry_log()
            why = carry_problem(x, r, prev, state["lg"])
            if why and "was not published before" not in why and "says closed" not in (why or ""):
                return None  # a labelled carry of a live venue stays
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
    state = {"prev": None, "lg": None, "rewritten": False}
    problems = []
    for x in items:
        msg = place_problem(x, rc.get(x["id"]), OUT, state)
        if msg: problems.append((x, msg))
    if not problems:
        if state.get("rewritten"):
            data["items"] = items
            open(OUT, "w", encoding="utf-8").write(pre + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + post)
        continue
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
            held_rows.append({"id": x["id"], "name": x.get("name") or x["id"], "layer": LAYER_OF.get(OUT, "shelters"), "reason": msg[len(prefix):] if msg.startswith(prefix) else msg})
        print("%s held this run (publish continues):\n" % LAYER_OF.get(OUT, OUT) + "\n".join(msg for _, msg in problems[:50]))
if held_rows and not bad:
    by_layer = {}
    for row in held_rows:
        by_layer.setdefault(row.get("layer") or "shelters", []).append(row)
    for layer, rows in by_layer.items():
        record_layer_holds(rows, layer, replace=False)
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
