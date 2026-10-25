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
        if changed:
            prev = e.get("last_change")
            if prev and prev != today:
                gap = _days(prev, today)
                if 0 < gap < 10 ** 5:
                    e.setdefault("change_gaps", []).append(gap); e["change_gaps"] = e["change_gaps"][-12:]
            e["last_change"] = today
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

def rhythm_factor(e, today):
    """0..1 once a place is due again by its own observed gap between real changes.
    Fewer than two observed gaps: 0 (the rhythm is not invented)."""
    gaps = [g for g in (e.get("change_gaps") or []) if isinstance(g, (int, float)) and g > 0]
    if len(gaps) < 2 or not e.get("last_change") or not today: return 0.0
    typical = sorted(gaps)[len(gaps) // 2]
    elapsed = _days(e["last_change"], today)
    if typical <= 0 or elapsed >= 10 ** 5 or elapsed < typical * 0.5: return 0.0
    return round(min(elapsed / typical, 1.0), 3)

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

def note_heal(s, key, tried, method, today=None):
    """Remember a switch from a failed method to one that worked. No result is stored here."""
    if method and tried and method != tried[0]:
        e = entry(s, key); e["healed_from"], e["healed_to"] = tried[0], method
        if today: e["healed_on"] = today

CONFIDENCE_MIN = 0.8  # sits under auto_apply_rules.json: a lower score holds the change for Dean. It never grants a change the rules forbid.

def allow_under_rules(kind, rules, confidence=None, layer=None):
    """Rules first. Confidence can only refuse a change the rules would have allowed.
    A new place or a removal the rules forbid stays forbidden even at confidence 1.
    confidence None means no extra doubt: the rules alone decide (today's behaviour)."""
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

def confidence_for(website, conflicted):
    """0 when sources already disagree for this site. Otherwise None, so the rules stand."""
    if website and website in (conflicted or ()): return 0.0
    return None

def provenance(kind, confidence, source, rules):
    """A log line for an automatic edit the rules already allowed. decides is always False:
    the rules file still decides, and this note cannot grant a change. A kind the rules
    would refuse, including a new place or a removal, returns None. Confidence can only refuse."""
    rules = rules or {}
    if kind not in (rules.get("automatic") or []): return None
    if not allow_under_rules(kind, rules, confidence): return None
    return {"rule": kind, "confidence": confidence, "source": source, "decides": False}

def empty_parse(http, extracted, previous, minimum=1):
    """True when a page answered HTTP 200 and the parser found fewer than `minimum` records,
    after a previous run that had found at least `minimum`. No previous count: False.
    Nothing is invented, and this does not remove a place."""
    try: http, extracted = int(http), int(extracted)
    except (TypeError, ValueError): return False
    if http != 200 or extracted >= minimum: return False
    if previous is None: return False
    try: previous = int(previous)
    except (TypeError, ValueError): return False
    return previous >= minimum

def source_history_update(history, marks, keep=12):
    """Append one success or failure per source. Older rows are kept, up to `keep`. Places are not touched."""
    out = {}
    for name, row in (history or {}).items():
        if isinstance(row, list): out[name] = [x for x in row if isinstance(x, bool)][-keep:]
    for name, ok in (marks or {}).items():
        if not name: continue
        out[name] = (out.get(name) or []) + [bool(ok)]
        out[name] = out[name][-keep:]
    return out

def sources_gone(history, need=3):
    """Sources whose last `need` recorded runs all failed. Fewer than `need` runs: not flagged.
    This is a flag only. It does not remove a place."""
    gone = []
    for name in sorted(history or {}):
        row = [x for x in (history.get(name) or []) if isinstance(x, bool)]
        if len(row) >= need and not any(row[-need:]): gone.append(name)
    return gone

def record_sources(path, marks, keep=12):
    """Update the source-health file. A missing file starts empty. Nothing is invented."""
    try: cur = json.load(open(path))
    except Exception: cur = {}
    if not isinstance(cur, dict): cur = {}
    nxt = source_history_update(cur, marks, keep)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"; json.dump(nxt, open(tmp, "w"), indent=0, sort_keys=True); os.replace(tmp, path)
    return nxt

PRUNE_DAYS = 90

def prune(s, today, seen, days=PRUNE_DAYS):
    """Forget scores for keys that are not in this run's list and were last checked at least `days` ago.
    No last_check: kept, because the age would be a guess. An empty seen list prunes nothing.
    A tombstone records the key, the last day and the word pruned. The map is not touched.
    A later check of that key starts again as a new key."""
    if not seen: return s
    seen = set(seen); tomb = list(s.get("tombstones") or [])
    for k, e in list((s.get("keys") or {}).items()):
        if k in seen: continue
        last = e.get("last_check")
        if not last: continue
        age = _days(last, today)
        if age < days or age >= 10 ** 5: continue
        tomb.append({"key": k, "last_day": str(last)[:10], "reason": "pruned"})
        del s["keys"][k]
    s["tombstones"] = tomb[-200:]
    return s

def anomaly_brake(history, proposed):
    """Stop when this run would change many more places than recent runs.
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

def heal(s, key, today, methods, attempt):
    """Try each method in method_order until one works, then remember that method.
    attempt(name) -> (ok, result). If every method fails, the result is None. Nothing is invented."""
    order = method_order(s, key, methods); tried = []
    for m in order:
        tried.append(m)
        try: ok, result = attempt(m)
        except Exception: ok, result = False, None
        if ok:
            note_heal(s, key, tried, m, today)
            return {"ok": True, "method": m, "result": result, "tried": tried, "healed": m != tried[0]}
    return {"ok": False, "method": None, "result": None, "tried": tried, "healed": False}

def snapshot(s, today, top=200):
    """Keep a small per-run history of priorities so the digest can show movers."""
    pr = {k: round(reward(e, today), 3) for k, e in s["keys"].items()}
    s["history"] = (s["history"] + [{"day": today, "reward": dict(sorted(pr.items(), key=lambda x: -x[1])[:top])}])[-14:]

def digest_lines(s, today, n=5):
    """Plain-English 'What the system learned' for the morning note. Same facts as before."""
    K = s["keys"]; L = ["## What the system learned", ""]
    if not K: return L + ["- Nothing has been learned yet. The first checks will start the record.", ""]
    h = s.get("history", []); prev = h[-2]["reward"] if len(h) >= 2 else {}
    now = {k: reward(e, today) for k, e in K.items()}
    mv = sorted(((now[k] - prev.get(k, 0.5), k) for k in now if k in prev), reverse=True)
    up = [x for x in mv if x[0] > 0.001][:n]; down = [x for x in mv[::-1] if x[0] < -0.001][:n]
    found = sorted((k for k, e in K.items() if e.get("last_find") == today), key=lambda k: -now[k])[:n]
    back = sorted((k for k, e in K.items() if resting(e, today)), key=lambda k: -K[k]["consec_fail"])[:n]
    L += ["- So far the sweeps have made %d checks across %d sources and places." % (s.get("total_checks", 0), len(K))]
    L += ["- Moved up the queue, because recent checks found more: " + (", ".join("%s (score up by %.2f)" % (k, d) for d, k in up) or "none")]
    L += ["- Moved down the queue, because recent checks found less: " + (", ".join("%s (score down by %.2f)" % (k, abs(d)) for d, k in down) or "none")]
    L += ["- Places that turned up something useful today: " + (", ".join(found) or "none")]
    L += ["- Waiting a little longer after several failed checks (still looked at at least every %d days): " % FLOOR_DAYS
          + (", ".join("%s (failed %d times in a row)" % (k, K[k]["consec_fail"]) for k in back) or "none"), ""]
    return L
