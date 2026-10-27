"""Self-learning sweeps (Dean, 25 Oct 2026, 08:01). Builds on source_score.py (fill rates per source).

What it learns (reports/learning_state.json, kept in the repo so it persists across runs):
  per source/place key: checks, finds (useful: new phone / times / confirmed change / new candidate),
  fails, consecutive fails, last check, last find, last change, and which extraction method worked
  (own_site, facebook, ifan, givefood, council_page, list_page ...).
How it is used - ONLY to decide ORDER, FREQUENCY and METHOD ORDER of checks, never what is published:
  reward   = (faded finds + 1) / (faded checks + 2)       (Beta(1,1) prior: new keys start at 0.5)
             finds and checks fade with a 30-day half-life, so an old result counts for less than a recent one
  explore  = C * sqrt(ln(total_checks + 1) / (checks + 1))   (UCB1: stable keys still get checked)
  gap      = 0..1 share of missing fields (phone / times) for that key (low fill rate = dig more)
  stale    = min(days since last check / FLOOR_DAYS, 1)
  priority = reward + explore + GAP_W * gap + STALE_W * stale + boost
  boost    : from learning_signals.py, never above BOOST_CAP (signals only reorder; they do not add a run)
  floor    : anything not checked for FLOOR_DAYS (7) days is checked this run, whatever its score.
  back-off : after k consecutive failures a key rests for min(2**(k-1), FLOOR_DAYS) days, then is retried
             (never longer than the weekly floor).
Every existing guard (publish gate, refresh guard, 10% drop stop, schema checks, 2-run confirmation rules)
is untouched: this module only sorts and budgets lists of URLs. Stdlib only."""
import datetime, json, math, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STATE = os.path.join(ROOT, "reports", "learning_state.json")
C, GAP_W, STALE_W, FLOOR_DAYS = 0.5, 0.6, 0.4, 7
BOOST_CAP = 3.0        # one cap for every signal combined (learning_signals.py). Do not raise this per signal.
HALF_LIFE_DAYS = 30    # a find or check from 30 days ago counts half as much; 60 days ago, a quarter

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
    e = entry(s, key, kind)
    faded_finds, faded_checks = _fade_counts(e, today)
    e["decayed_finds"], e["decayed_checks"], e["decay_asof"] = faded_finds, faded_checks, today
    e["checks"] += 1; e["decayed_checks"] = faded_checks + 1; s["total_checks"] += 1; e["last_check"] = today
    if ok:
        e["consec_fail"] = 0
        if finds: e["finds"] += 1; e["decayed_finds"] = faded_finds + 1; e["last_find"] = today
        if changed: e["last_change"] = today
        if method:
            m = e["methods"].setdefault(method, {"ok": 0, "fail": 0}); m["ok"] += 1; e["last_method"] = method
    else:
        e["fails"] += 1; e["consec_fail"] += 1
        if method: e["methods"].setdefault(method, {"ok": 0, "fail": 0})["fail"] += 1

def _decay_factor(days):
    if not days or days <= 0: return 1.0
    return 0.5 ** (days / float(HALF_LIFE_DAYS))

def _fade_counts(e, today):
    """Finds and checks as of `today`. Keys saved before decay existed fade from their raw totals since last_check.
    Nothing is filled in when there is no check date."""
    if "decayed_checks" in e:
        finds, checks = float(e.get("decayed_finds") or 0), float(e["decayed_checks"])
        asof = e.get("decay_asof") or e.get("last_check")
    else:
        finds, checks = float(e.get("finds") or 0), float(e.get("checks") or 0)
        asof = e.get("last_check")
    if today and asof:
        days = _days(asof, today)
        if 0 < days < 10 ** 5:
            f = _decay_factor(days); finds *= f; checks *= f
    return finds, checks

def reward(e, today=None):
    finds, checks = _fade_counts(e, today)
    return (finds + 1) / (checks + 2)

def cap_parts(parts, cap=None):
    """Scale a site's signal parts so they sum to at most BOOST_CAP. One cap, shared by every signal."""
    cap = BOOST_CAP if cap is None else cap
    kept = {k: float(v) for k, v in (parts or {}).items() if v}
    raw = sum(kept.values())
    if raw <= cap or raw <= 0: return kept
    scale = cap / raw
    return {k: v * scale for k, v in kept.items()}

def note_signals(s, today, extra=None):
    """Bookkeeping the signals sweep writes into learning_state.json. Order data only."""
    s["signals_run"] = today
    for k, v in (extra or {}).items(): s[k] = v
    return s

def resting(e, today):
    """Back-off: k consecutive failures -> rest min(2**(k-1), FLOOR_DAYS) days since the last check."""
    k = e.get("consec_fail", 0)
    if k < 2 or not e.get("last_check"): return False
    return _days(e["last_check"], today) < min(2 ** (k - 1), FLOOR_DAYS)

def due_floor(e, today): return not e.get("last_check") or _days(e["last_check"], today) >= FLOOR_DAYS

def priority(s, key, today, gap=0.0, boost=0.0):
    e = s["keys"].get(key) or {"checks": 0, "finds": 0, "last_check": None}
    explore = C * math.sqrt(math.log(s.get("total_checks", 0) + 1) / (e["checks"] + 1))
    stale = 1.0 if not e.get("last_check") else min(_days(e["last_check"], today) / FLOOR_DAYS, 1.0)
    return round(reward(e, today) + explore + GAP_W * max(0.0, min(gap, 1.0)) + STALE_W * stale + max(0.0, min(float(boost or 0), BOOST_CAP)), 4)

def plan(s, keys, today, gaps=None, budget=None, boosts=None):
    """Order keys for this run. Floor-due keys first (always kept), then by priority; resting keys (back-off) are
    left out unless the weekly floor makes them due. `budget` caps how many non-floor keys are kept."""
    gaps = gaps or {}; boosts = boosts or {}; floor, rest, skipped = [], [], []
    for k in keys:
        e = s["keys"].get(k)
        if e and resting(e, today) and not due_floor(e, today) and boosts.get(k, 0) < 0.8: skipped.append(k); continue  # a strong change signal ends the rest early
        (floor if (e is None or due_floor(e, today)) else rest).append(k)
    p = {k: priority(s, k, today, gaps.get(k, 0.0), boosts.get(k, 0.0)) for k in keys}
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

CONFIDENCE_MIN = 0.8  # sits under auto_apply_rules.json: a lower score holds the change for Dean. It never grants a change the rules forbid.

def allow_under_rules(kind, rules, confidence=None, layer=None):
    """Rules first. Confidence can only refuse a change the rules would have allowed.
    A new place or a removal the rules forbid stays forbidden even at confidence 1.
    A stopped run does not grant an add or a removal. confidence None means no extra
    doubt: the rules alone decide."""
    rules = rules or {}
    if kind == "new_place":
        adds = rules.get("add_new_places") or {}
        allowed = bool(adds.get(layer)) if layer else any(bool(v) for v in adds.values())
    elif kind == "remove_place":
        allowed = bool(rules.get("remove_confirmed_closures"))
    else:
        allowed = kind in (rules.get("automatic") or [])
    if not allowed: return False
    if confidence is None: return True
    try: return float(confidence) >= CONFIDENCE_MIN
    except (TypeError, ValueError): return False

# Rows full_check would write onto the map. A new place, and a closure note that waits
# for Dean, are logged but not applied, so they do not count. The bars in anomaly_brake
# are unchanged; only the number passed in as `proposed` is the applied count.
APPLIED_KINDS = {"phone", "removed", "hours", "opening hours", "hour change", "access"}
HELD_KINDS = {"new food bank", "new_place", "closure"}

def is_applied_change(entry):
    """True for a change this run would write: access flip, phone fix, hour change, removal.
    A new place held for Dean is false. A closure note that keeps the pin and waits for Dean is false."""
    if not isinstance(entry, dict): return False
    kind = str(entry.get("kind") or "").strip().lower()
    if kind in HELD_KINDS or kind.startswith("new "): return False
    if kind in APPLIED_KINDS: return True
    return not kind and "old" in entry and "new" in entry

def applied_count(entries):
    return sum(1 for e in entries or [] if is_applied_change(e))

def anomaly_brake(history, proposed):
    """Stop when this run would apply many more changes than recent runs.
    `proposed` is the applied count (access flips, phone fixes, hour changes, removals).
    Fewer than four recorded runs: do not stop (there is no baseline to compare with, and none is invented).
    Unusual means at least 10, at least three times the median, and at least 8 above that median.
    Those bars are multiples of the recorded counts, not a guessed expected number."""
    counts = []
    for h in history or []:
        if isinstance(h, dict) and isinstance(h.get("changes"), int): counts.append(h["changes"])
        elif isinstance(h, int): counts.append(h)
    flag = {"stop": False, "proposed": int(proposed), "median": None, "reason": ""}
    if len(counts) < 4:
        flag["reason"] = "not enough history to judge this run (%d past runs)" % len(counts)
        return flag
    med = sorted(counts)[len(counts) // 2]; flag["median"] = med
    if proposed >= max(10, med * 3) and proposed >= med + 8:
        flag["stop"] = True
        flag["reason"] = "this run would change %d places; recent runs usually change about %d. Stopped and flagged for Dean." % (proposed, med)
    else:
        flag["reason"] = "within the usual range (%d vs about %d)" % (proposed, med)
    return flag

def snapshot(s, today, top=200):
    """Keep a small per-run history of priorities so the digest can show movers."""
    pr = {k: round(reward(e, today), 3) for k, e in s["keys"].items()}
    s["history"] = (s["history"] + [{"day": today, "reward": dict(sorted(pr.items(), key=lambda x: -x[1])[:top])}])[-14:]

def digest_lines(s, today, n=5):
    """'What the system learned' section for reports/morning_digest.md."""
    K = s["keys"]; L = ["## What the system learned", ""]
    if not K: return L + ["- nothing yet (first runs build the history)", ""]
    h = s.get("history", []); prev = h[-2]["reward"] if len(h) >= 2 else {}
    now = {k: reward(e, today) for k, e in K.items()}
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

def try_auto_phone(item, proposed, source, root=None, via="learning"):
    """Learning / auto-apply writer for one listing phone.
    A frozen number is not changed. The attempt is held for Dean. Returns True only when proposed was written."""
    import phone_lock
    return phone_lock.consider(item, "phone", proposed, root=root, via=via, source=source, persist_new=True)
