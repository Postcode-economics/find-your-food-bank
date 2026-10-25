"""Self-learning sweeps (Dean, 25 Oct 2026, 08:01). Builds on source_score.py (fill rates per source).

What it learns (reports/learning_state.json, kept in the repo so it persists across runs):
  per source/place key: checks, finds (useful: new phone / times / confirmed change / new candidate),
  fails, consecutive fails, last check, last find, last change, and which extraction method worked
  (own_site, facebook, ifan, givefood, council_page, list_page ...).
How it is used - ONLY to decide ORDER, FREQUENCY and METHOD ORDER of checks, never what is published:
  reward   = (finds + 1) / (checks + 2)                      (Beta(1,1) prior: new keys start at 0.5)
  explore  = C * sqrt(ln(total_checks + 1) / (checks + 1))   (UCB1: stable keys still get checked)
  gap      = 0..1 share of missing fields (phone / times) for that key (low fill rate = dig more)
  stale    = min(days since last check / FLOOR_DAYS, 1)
  priority = reward + explore + GAP_W * gap + STALE_W * stale
  floor    : anything not checked for FLOOR_DAYS (7) days is checked this run, whatever its score.
  back-off : after k consecutive failures a key rests for min(2**(k-1), FLOOR_DAYS) days, then is retried
             (never longer than the weekly floor).
Every existing guard (publish gate, refresh guard, 10% drop stop, schema checks, 2-run confirmation rules)
is untouched: this module only sorts and budgets lists of URLs. Stdlib only."""
import datetime, json, math, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STATE = os.path.join(ROOT, "reports", "learning_state.json")
C, GAP_W, STALE_W, FLOOR_DAYS = 0.5, 0.6, 0.4, 7

def load(path=STATE):
    try: s = json.load(open(path))
    except Exception: s = {}
    s.setdefault("version", 1); s.setdefault("keys", {}); s.setdefault("total_checks", 0); s.setdefault("history", [])
    return s

def save(s, path=STATE):
    tmp = path + ".tmp"; json.dump(s, open(tmp, "w"), indent=0, sort_keys=True); os.replace(tmp, path)

def _days(a, b):
    try: return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days
    except Exception: return 10 ** 6

def entry(s, key, kind="source"):
    return s["keys"].setdefault(key, {"kind": kind, "checks": 0, "finds": 0, "fails": 0, "consec_fail": 0, "last_check": None,
                                      "last_find": None, "last_change": None, "methods": {}, "last_method": None})

def record(s, key, today, ok, finds=0, method=None, changed=False, kind="source"):
    """One check of `key` on `today` (ISO date). ok=None means 'not reached' (time budget) and records nothing."""
    if ok is None: return
    e = entry(s, key, kind); e["checks"] += 1; s["total_checks"] += 1; e["last_check"] = today
    if ok:
        e["consec_fail"] = 0
        if finds: e["finds"] += 1; e["last_find"] = today
        if changed: e["last_change"] = today
        if method:
            m = e["methods"].setdefault(method, {"ok": 0, "fail": 0}); m["ok"] += 1; e["last_method"] = method
    else:
        e["fails"] += 1; e["consec_fail"] += 1
        if method: e["methods"].setdefault(method, {"ok": 0, "fail": 0})["fail"] += 1

def reward(e): return (e["finds"] + 1) / (e["checks"] + 2)

def resting(e, today):
    """Back-off: k consecutive failures -> rest min(2**(k-1), FLOOR_DAYS) days since the last check."""
    k = e.get("consec_fail", 0)
    if k < 2 or not e.get("last_check"): return False
    return _days(e["last_check"], today) < min(2 ** (k - 1), FLOOR_DAYS)

def due_floor(e, today): return not e.get("last_check") or _days(e["last_check"], today) >= FLOOR_DAYS

def priority(s, key, today, gap=0.0):
    e = s["keys"].get(key) or {"checks": 0, "finds": 0, "last_check": None}
    explore = C * math.sqrt(math.log(s.get("total_checks", 0) + 1) / (e["checks"] + 1))
    stale = 1.0 if not e.get("last_check") else min(_days(e["last_check"], today) / FLOOR_DAYS, 1.0)
    return round(reward(e) + explore + GAP_W * max(0.0, min(gap, 1.0)) + STALE_W * stale, 4)

def plan(s, keys, today, gaps=None, budget=None):
    """Order keys for this run. Floor-due keys first (always kept), then by priority; resting keys (back-off) are
    left out unless the weekly floor makes them due. `budget` caps how many non-floor keys are kept."""
    gaps = gaps or {}; floor, rest, skipped = [], [], []
    for k in keys:
        e = s["keys"].get(k)
        if e and resting(e, today) and not due_floor(e, today): skipped.append(k); continue
        (floor if (e is None or due_floor(e, today)) else rest).append(k)
    p = {k: priority(s, k, today, gaps.get(k, 0.0)) for k in keys}
    floor.sort(key=lambda k: -p[k]); rest.sort(key=lambda k: -p[k])
    if budget is not None: rest = rest[:max(0, budget - len(floor))]
    return floor + rest, skipped, p

def method_order(s, key, methods):
    """Try the method that worked last for this site first, then the rest by past success rate."""
    e = s["keys"].get(key)
    if not e: return list(methods)
    rate = lambda m: (e["methods"].get(m, {}).get("ok", 0) + 1) / (sum(e["methods"].get(m, {}).values()) + 2)
    rest = sorted([m for m in methods if m != e.get("last_method")], key=lambda m: -rate(m))
    return ([e["last_method"]] if e.get("last_method") in methods else []) + rest

def snapshot(s, today, top=200):
    """Keep a small per-run history of priorities so the digest can show movers."""
    pr = {k: round(reward(e), 3) for k, e in s["keys"].items()}
    s["history"] = (s["history"] + [{"day": today, "reward": dict(sorted(pr.items(), key=lambda x: -x[1])[:top])}])[-14:]

def digest_lines(s, today, n=5):
    """'What the system learned' section for reports/morning_digest.md."""
    K = s["keys"]; L = ["## What the system learned", ""]
    if not K: return L + ["- nothing yet (first runs build the history)", ""]
    h = s.get("history", []); prev = h[-2]["reward"] if len(h) >= 2 else {}
    now = {k: reward(e) for k, e in K.items()}
    mv = sorted(((now[k] - prev.get(k, 0.5), k) for k in now if k in prev), reverse=True)
    up = [x for x in mv if x[0] > 0.001][:n]; down = [x for x in mv[::-1] if x[0] < -0.001][:n]
    found = sorted((k for k, e in K.items() if e.get("last_find") == today), key=lambda k: -now[k])[:n]
    back = sorted((k for k, e in K.items() if resting(e, today)), key=lambda k: -K[k]["consec_fail"])[:n]
    L += ["- Checks recorded so far: %d across %d sources/places" % (s.get("total_checks", 0), len(K))]
    L += ["- Top movers up: " + (", ".join("%s (+%.2f)" % (k, d) for d, k in up) or "none")]
    L += ["- Top movers down: " + (", ".join("%s (%.2f)" % (k, d) for d, k in down) or "none")]
    L += ["- Sources/places with useful finds today: " + (", ".join(found) or "none")]
    L += ["- Backing off (repeated failures, retried within %d days): " % FLOOR_DAYS + (", ".join("%s (%d fails)" % (k, K[k]["consec_fail"]) for k in back) or "none"), ""]
    return L
