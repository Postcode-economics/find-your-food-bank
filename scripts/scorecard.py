"""Weekly self-sufficiency scorecard (plan 0.2, private vault plan of 9 Nov 2026, Phase 0). Reporting only.

What it does: reads the saved private run state (the per-layer folders site-run-state/<layer>/ that
scripts/private_state.sh restore has just cloned into the runner's temp folder) and writes ONE private scorecard for
the ISO week: reports/scorecard/<YYYY>-W<ww>.json and .md. reports/ is ignored by git (rule 97), so the card never
enters this public repo; the sweep's save step carries it into the private vault (site-run-state/sweep/reports/
scorecard/), and the next restore brings it back so the following week can compare with it.

Rules it keeps:
- Real data only (rule 3, rule 59). Every number is counted from a saved run-state file or a GitHub run record. A
  measure whose input is missing or unreadable is null in the JSON and "no data yet" in the card; nothing is guessed.
  Counts say "this week" or "latest run day", never cumulative unless labelled, and never "verified".
- Writes only under <root>/reports/scorecard/ (refused anywhere else). Never writes overrides/, published data,
  phones, times, locks, the undo log or the two-run memory, and changes no item.
- Fail closed and never blocks: no readable saved state = nothing written; any error = a one-line message and exit 0,
  so a refresh, sweep or publish can never fail or wait because of it.

Usage:
  python scripts/scorecard.py --state <dir>/site-run-state [--week 2026-W46] [--root .] [--weekly] [--force]
  --weekly  only on Sundays (UTC), and only when this week's card is not already in reports/scorecard/.
            A later sweep on the same Sunday writes it if an earlier one failed. If every Sunday sweep
            that week fails, that week's card is not written.
"""
from __future__ import annotations

import argparse, collections, datetime, json, os, re, sys, urllib.request

LAYERS = ("foodbanks", "shelters", "warmspaces", "sweep")
KIND_LAYER = {"fb": "foodbanks", "sh": "shelters", "ws": "warmspaces"}
OUT = os.path.join("reports", "scorecard")
NO = "no data yet"
WORKFLOWS = {"foodbanks": "refresh.yml", "shelters": "refresh-shelters.yml", "warmspaces": "refresh-warmspaces.yml",
             "sweep": "sweep-daily.yml"}
PENDING_FILES = {"foodbanks": "logs/pending_dean.json", "shelters": "logs/pending_dean.json",
                 "warmspaces": "logs/pending_dean.json"}
DISCOVERY = {"foodbanks": "logs/discovery_today_foodbanks.json", "shelters": "logs/discovery_today_shelters.json",
             "warmspaces": "logs/discovery_today_warmspaces.json", "sweep": "logs/discovery_today_sweep.json"}


# ------------------------------------------------------------------ small helpers

def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def week_bounds(week):
    """'2026-W46' -> (Monday 00:00 UTC, next Monday 00:00 UTC)."""
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week or "")
    if not m:
        raise ValueError("week must look like 2026-W46")
    start = datetime.datetime.combine(datetime.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1),
                                      datetime.time(0), tzinfo=datetime.timezone.utc)
    return start, start + datetime.timedelta(days=7)


def iso_week(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def prev_week(week):
    start, _ = week_bounds(week)
    return iso_week((start - datetime.timedelta(days=1)).date())


def _ts(v):
    """ISO timestamp or YYYY-MM-DD -> aware datetime, else None."""
    if not isinstance(v, str) or not v:
        return None
    try:
        t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _in(v, start, end):
    t = _ts(v)
    return t is not None and start <= t < end


def _reason(text):
    """Group a hold reason: drop the per-place detail in brackets and numbers, keep the rule wording."""
    t = re.sub(r"\([^)]*\)", "", str(text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = t.split(";")[0].strip()
    return t[:90] or "(no reason given)"


def _seq(v):
    """A list or tuple, or a single string as one item (never letter by letter). Anything else is empty."""
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, (list, tuple)):
        return list(v)
    return []


def _int(v):
    """A real number, else None. Booleans and non-numeric values are not counts."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def _yn(x):
    return NO if x is None else ("yes" if x else "no")


LAYER_LABEL = {"foodbanks": "food banks", "shelters": "shelters", "warmspaces": "warm spaces", "sweep": "sweep"}


def _partial_sum(xs, labels):
    """All missing -> 'no data yet'; all present -> the total; otherwise the total labelled as partial."""
    present = [(v, lab) for v, lab in zip(xs, labels) if v is not None]
    if not present:
        return NO
    total = str(sum(v for v, _ in present))
    if len(present) == len(xs):
        return total
    return "%s (partial: %s only)" % (total, ", ".join(lab for _, lab in present))


def _measure(fn, default=None):
    """One bad field must not skip the rest of the card."""
    try:
        return fn()
    except Exception:
        return default


def safe_out(root):
    """The only folder this script may write to: <root>/reports/scorecard."""
    base = os.path.realpath(os.path.join(root, OUT))
    rep = os.path.realpath(os.path.join(root, "reports"))
    if not base.startswith(rep + os.sep):
        raise ValueError("scorecard write outside reports/ refused")
    return base


# ------------------------------------------------------------------ measures (each returns real counts or None)

def undo_log(state):
    """Union of every layer's saved undo log (same de-duplication as private_state_restore: an entry reverted anywhere
    stays reverted). None when no layer saved one."""
    out, at, seen = [], {}, False
    for layer in LAYERS:
        lst = _load(os.path.join(state, layer, "reports", "times_auto_applied.json"))
        if not isinstance(lst, list):
            continue
        seen = True
        for e in lst:
            if not isinstance(e, dict):
                continue
            k = json.dumps({a: b for a, b in e.items() if a != "reverted"}, sort_keys=True)
            if k in at:
                if e.get("reverted"):
                    out[at[k]]["reverted"] = True
                continue
            at[k] = len(out); out.append(dict(e))
    return out if seen else None


def applied(state, start, end):
    """Automatic opening-time changes applied this week, per layer, and how many of those are now marked undone."""
    log = undo_log(state)
    res = {l: {"auto_applied": None, "undone": None, "ids": None} for l in LAYERS}
    if log is None:
        return res
    for l in LAYERS:
        res[l] = {"auto_applied": 0, "undone": 0, "ids": []}
    for e in log:
        when = e.get("second_run_at") or e.get("applied_at") or e.get("first_run_at")
        if not _in(when, start, end):
            continue
        layer = KIND_LAYER.get(e.get("kind")) if e.get("path") == "cross_check" else "sweep"   # times_finder = sweep
        if not layer:
            continue
        res[layer]["auto_applied"] += 1
        if e.get("id") is not None:
            res[layer]["ids"].append(str(e.get("id")))
        if e.get("reverted"):
            res[layer]["undone"] += 1
    return res


def held(state):
    """Latest saved intelligent-mode summary per layer (each layer's own folder): held, applied that day, hold reasons,
    pages that did not open, and any coverage-gate block. Missing or wrong-type keys are null, never 0."""
    res = {}
    for l in LAYERS:
        try:
            d = _load(os.path.join(state, l, "reports", "intelligent_mode.json"))
            slot = ((d or {}).get("layers") or {}).get(l) if isinstance(d, dict) else None
            if not isinstance(slot, dict):
                res[l] = None
                continue
            rejected = slot.get("rejected") if "rejected" in slot else None
            if isinstance(rejected, list):
                rejected_listed = len(rejected)
                held_ids = sorted({str(r.get("id")) for r in rejected if isinstance(r, dict) and r.get("id")})
                reasons = collections.Counter()
                for r in rejected:
                    if not isinstance(r, dict):
                        continue
                    for why in set(_reason(x) for x in _seq(r.get("reasons"))):
                        reasons[why] += 1
                hold_reasons = dict(reasons.most_common(8))
            else:
                rejected_listed, held_ids, hold_reasons = None, [], {}
            cov = slot.get("coverage") if isinstance(slot.get("coverage"), dict) else {}
            unreach = {}
            if isinstance(cov.get("sites"), int) and isinstance(cov.get("sites_opened"), int):
                unreach["sites_not_opened"] = cov["sites"] - cov["sites_opened"]; unreach["sites"] = cov["sites"]
            if isinstance(cov.get("source_pages"), int) and isinstance(cov.get("source_opened"), int):
                unreach["source_pages_not_opened"] = cov["source_pages"] - cov["source_opened"]
                unreach["source_pages"] = cov["source_pages"]
            if isinstance(cov.get("render_errors"), int):
                unreach["render_errors"] = cov["render_errors"]; unreach["render_attempts"] = cov.get("render_attempts")
            if "would_block" not in d or not isinstance(d.get("would_block"), list):
                coverage_gate_blocks = None
            else:
                coverage_gate_blocks = len([b for b in d["would_block"] if isinstance(b, str)])
            if "errors" not in slot or not isinstance(slot.get("errors"), list):
                errors = None
            else:
                errors = len(slot["errors"])
            res[l] = {"run_day": d.get("run"), "held": _int(slot.get("held")), "applied_that_day": _int(slot.get("applied")),
                      "stale_cleared": _int(slot.get("stale_cleared")), "rejected_listed": rejected_listed,
                      "held_ids": held_ids, "hold_reasons": hold_reasons, "unreachable": unreach or None,
                      "coverage_gate_blocks": coverage_gate_blocks, "errors": errors}
        except Exception:
            res[l] = None
    return res


def pending(state, prev):
    """Dean's held queue (logs/pending_dean.json in each layer's own folder): size, reasons, and how many of these ids
    were already in the queue at last week's scorecard (queue age in weeks; held_on is rewritten every run)."""
    res = {}
    for l in LAYERS:
        if l not in PENDING_FILES:
            res[l] = None
            continue
        d = _load(os.path.join(state, l, PENDING_FILES[l]))
        rows = (d or {}).get(l) if isinstance(d, dict) else None
        if not isinstance(rows, list):
            res[l] = None
            continue
        ids = sorted({str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")})
        why = collections.Counter()
        for r in rows:
            if not isinstance(r, dict):
                continue
            items = _seq(r.get("why")) or ["(no reason given)"]
            for w in items:
                why[_reason(w)] += 1
        prev_layers = prev.get("layers") if isinstance(prev, dict) else None
        last_layer = (prev_layers or {}).get(l) if isinstance(prev_layers, dict) else None
        last = last_layer.get("pending") if isinstance(last_layer, dict) else None
        last_ids = set(last.get("ids") or []) if isinstance(last, dict) and isinstance(last.get("ids"), list) else None
        res[l] = {"size": len(rows), "reasons": dict(why.most_common(8)), "ids": ids,
                  "also_at_last_scorecard": (len(set(ids) & last_ids) if last_ids is not None else None)}
    return res


def discovery(state, start, end):
    """Discovery queue (latest saved day per layer) and the follow-through queue movement this week (sweep)."""
    res = {}
    for l in LAYERS:
        d = _load(os.path.join(state, l, DISCOVERY[l]))
        if not isinstance(d, dict):
            res[l] = None
            continue
        try:
            if "queued" not in d or not isinstance(d.get("queued"), dict):
                queued, queue_reasons = None, {}
            else:
                q = d["queued"]
                queued = len(q)
                reasons = collections.Counter(_reason(r) for v in q.values() if isinstance(v, dict) for r in _seq(v.get("reasons")))
                queue_reasons = dict(reasons.most_common(6))
            added = d.get("added")
            if "runs" not in d or not isinstance(d.get("runs"), list):
                runs_that_day = None
            else:
                runs_that_day = len(d["runs"])
            res[l] = {"day": d.get("day"), "queued": queued,
                      "added_that_day": len(added) if isinstance(added, (list, dict)) else None,
                      "runs_that_day": runs_that_day, "queue_reasons": queue_reasons}
        except Exception:
            res[l] = None
    ft = _load(os.path.join(state, "sweep", "logs", "follow_through_queue_seen.json"))
    if isinstance(ft, dict):
        days = [v for v in ft.values() if isinstance(v, str)]
        res["follow_through"] = {"followed_up_this_week": sum(1 for v in days if _in(v, start, end)),
                                 "tracked": len(ft)}
    else:
        res["follow_through"] = None
    sp = _load(os.path.join(state, "sweep", "logs", "sweep_pending.json"))
    if isinstance(sp, dict) and isinstance(sp.get("items"), list):
        res["sweep_pending"] = {"run": sp.get("run"), "size": len(sp["items"]),
                                "reasons": dict(collections.Counter(_reason(i.get("reason")) for i in sp["items"]
                                                                    if isinstance(i, dict)).most_common(6))}
    else:
        res["sweep_pending"] = None
    vp = _load(os.path.join(state, "warmspaces", "reports", "verified_new_places.json"))
    res["verified_proposals"] = ({"generated": vp.get("generated"), "places": len(vp.get("places") or [])}
                                 if isinstance(vp, dict) and isinstance(vp.get("places"), list) else None)
    return res


def brakes(state, start, end):
    """Whether a brake trip is on file this week (yes/no, from the latest anomaly record) and change-count stats.
    Only one latest anomaly record is stored, so this is not a trip count. Missing keys are null, never 0."""
    ls = _load(os.path.join(state, "foodbanks", "reports", "learning_state.json"))
    if not isinstance(ls, dict):
        return None
    if "anomaly" not in ls or not isinstance(ls.get("anomaly"), dict):
        trip_on_file, last_trip = None, None
    else:
        an = ls["anomaly"]
        if not an.get("stop"):
            trip_on_file, last_trip = False, None
        elif _ts(an.get("day")) is None:
            # stop is set but the week cannot be read, so this is not a "no"
            trip_on_file = None
            last_trip = {"day": an.get("day"), "reason": an.get("reason")}
        else:
            trip_on_file = bool(_in(an.get("day"), start, end))
            last_trip = {"day": an.get("day"), "reason": an.get("reason")}
    if "change_counts" not in ls or not isinstance(ls.get("change_counts"), list):
        runs_counted, max_changes = None, None
    else:
        counts = [c for c in ls["change_counts"] if isinstance(c, dict) and _in(c.get("day"), start, end)]
        runs_counted = len(counts)
        nums = [_int(c.get("changes")) for c in counts]
        nums = [n for n in nums if n is not None]
        max_changes = max(nums) if nums else None
    return {"trip_on_file_this_week": trip_on_file,
            "last_trip": last_trip,
            "stop_report_on_file": os.path.exists(os.path.join(state, "foodbanks", "reports", "anomaly_brake.md")),
            "runs_counted_this_week": runs_counted,
            "max_changes_in_a_run": max_changes}


def failures(state):
    """Food bank own-site pages that failed on the latest saved full check."""
    se = _load(os.path.join(state, "foodbanks", "reports", "source_errors.json"))
    if not isinstance(se, dict) or not isinstance(se.get("errors"), list):
        return None
    codes = collections.Counter(str(e.get("http") or "error") for e in se["errors"] if isinstance(e, dict))
    blocked = sum(n for c, n in codes.items() if c in ("403", "429"))
    return {"run": se.get("run"), "checked": _int(se.get("checked")), "failed": len(se["errors"]), "blocked_403_429": blocked}


def corrections(state, start, end):
    """Hand corrections on file per the learning report's own trend (count at the last point this week)."""
    s = _load(os.path.join(state, "foodbanks", "reports", "learning_signals.json"))
    if not isinstance(s, dict) or not isinstance(s.get("trend"), list):
        return None
    pts = [t for t in s["trend"] if isinstance(t, dict) and _in(t.get("day"), start, end)]
    if not pts:
        return None
    last = sorted(pts, key=lambda t: t.get("day"))[-1]
    return {"day": last.get("day"), "hand_corrections_on_file": last.get("corrections"),
            "reachable_share": last.get("reachable"), "phone_agreement": last.get("phone_agreement")}


def shadow(state, start, end):
    """Shadow trial (record only) runs this week, per layer and rule: runs, candidates and rows that differ from today's
    live decision. None until the trial has recorded something."""
    res, any_found = {}, False
    for l in LAYERS:
        base = os.path.join(state, l, "reports", "shadow", l)
        if not os.path.isdir(base):
            res[l] = None
            continue
        runs, cands, differ, have_cands = 0, 0, collections.Counter(), False
        for f in sorted(os.listdir(base)):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f) or not _in(f[:10], start, end):
                continue
            d = _load(os.path.join(base, f), {})
            for r in (d.get("runs") or []) if isinstance(d, dict) else []:
                if not isinstance(r, dict):
                    continue
                runs += 1
                n = _int(r.get("candidates"))
                if n is not None:
                    cands += n
                    have_cands = True
                rules = r.get("rules") if isinstance(r.get("rules"), dict) else {}
                for rid, v in rules.items():
                    rows = (v or {}).get("differs_from_today") if isinstance(v, dict) else None
                    if isinstance(rows, list):
                        differ[rid] += len(rows)
        res[l] = {"runs": runs, "candidates": (cands if have_cands else None), "differs_by_rule": dict(differ)} if runs else None
        any_found = any_found or bool(runs)
    trial = None
    for l in LAYERS:
        t = _load(os.path.join(state, l, "reports", "shadow", "trial.json"))
        if isinstance(t, dict):
            trial = {k: t.get(k) for k in ("start", "last_day", "end")}
            break
    return {"trial": trial, "layers": res} if (any_found or trial) else None


def other(state):
    lanc = _load(os.path.join(state, "warmspaces", "reports", "lancs_season.json"))
    cities = None
    try:
        txt = open(os.path.join(state, "sweep", "reports", "city_coverage.md"), encoding="utf-8").read()
        rows = re.findall(r"^- (.+?): .* — (.+)$", txt, re.M)
        if rows:
            cities = {"top20_listed": len(rows), "under_the_bar": sorted(c for c, s in rows if s.strip() != "ok")}
    except OSError:
        pass
    return {"lancashire": ({"run_day": lanc.get("run_day"), "rows": lanc.get("rows"), "counts": lanc.get("counts"),
                            "lifts_hold": lanc.get("lifts_hold")} if isinstance(lanc, dict) else None),
            "cities": cities}


def saves(state):
    """When each layer last saved its run state (from its .saved_at), UTC ISO."""
    out = {}
    for l in LAYERS:
        try:
            t = float(open(os.path.join(state, l, ".saved_at"), encoding="utf-8").read().strip())
            out[l] = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec="minutes")
        except (OSError, ValueError):
            out[l] = None
    return out


def runs(start, end, token=None, repo=None, opener=None):
    """Main-branch workflow runs created this week per layer (success / failure / other), from the GitHub API.
    None per layer when the API can't be read (no token, offline); never raises."""
    token = token if token is not None else os.environ.get("GH_TOKEN", "")
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "Postcode-economics/find-your-food-bank")
    opener = opener or urllib.request.urlopen
    out = {}
    for l, wf in WORKFLOWS.items():
        if not token:
            out[l] = None
            continue
        url = ("https://api.github.com/repos/%s/actions/workflows/%s/runs?branch=main&per_page=100&created=%s..%s"
               % (repo, wf, start.date().isoformat(), (end - datetime.timedelta(days=1)).date().isoformat()))
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
                                                       "Accept": "application/vnd.github+json"})
            with opener(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            c = collections.Counter(str(x.get("conclusion") or x.get("status")) for x in data.get("workflow_runs") or [])
            out[l] = {"runs": sum(c.values()), "success": c.get("success", 0), "failure": c.get("failure", 0),
                      "other": sum(n for k, n in c.items() if k not in ("success", "failure"))}
        except Exception:
            out[l] = None
    return out


# ------------------------------------------------------------------ the card

def build(state, week, prev=None, now=None, gh=None):
    start, end = week_bounds(week)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    empty_ap = {l: {"auto_applied": None, "undone": None, "ids": None} for l in LAYERS}
    ap = _measure(lambda: applied(state, start, end), empty_ap) or empty_ap
    hd = _measure(lambda: held(state), {l: None for l in LAYERS}) or {l: None for l in LAYERS}
    pd = _measure(lambda: pending(state, prev), {l: None for l in LAYERS}) or {l: None for l in LAYERS}
    disc = _measure(lambda: discovery(state, start, end), {}) or {}
    sh = _measure(lambda: shadow(state, start, end), None)
    card = {"week": week, "window_utc": [start.isoformat(), min(end, now).isoformat()], "generated_at": now.isoformat(timespec="seconds"),
            "source": "private run state site-run-state/<layer>/ as each layer last saved it; GitHub run records",
            "saved_at": _measure(lambda: saves(state), {l: None for l in LAYERS}),
            "layers": {},
            "discovery": {k: disc.get(k) for k in ("follow_through", "sweep_pending", "verified_proposals")},
            "brake": _measure(lambda: brakes(state, start, end), None),
            "foodbank_page_failures": _measure(lambda: failures(state), None),
            "hand_corrections": _measure(lambda: corrections(state, start, end), None), "shadow_trial": sh,
            "hand_check": {"auto_changes_undone_this_week": (
                sum(v["undone"] for v in ap.values() if isinstance(v, dict) and isinstance(v.get("undone"), int))
                if isinstance(ap.get("foodbanks"), dict) and ap["foodbanks"].get("undone") is not None else None),
                           "note": "08:00/21:30 hand-check records are kept by Grok Bot outside the run state: " + NO},
            "runs": gh if gh is not None else runs(start, end), **(_measure(lambda: other(state), {"lancashire": None, "cities": None}) or {"lancashire": None, "cities": None})}
    prev_layers = prev.get("layers") if isinstance(prev, dict) else None
    for l in LAYERS:
        a = ap.get(l) if isinstance(ap.get(l), dict) else {"auto_applied": None, "undone": None, "ids": None}
        rate = (round(a["undone"] / a["auto_applied"], 3) if a.get("auto_applied") else None)
        last_layer = (prev_layers or {}).get(l) if isinstance(prev_layers, dict) else None
        latest_prev = last_layer.get("latest_day") if isinstance(last_layer, dict) else None
        last_held = latest_prev.get("held_ids") if isinstance(latest_prev, dict) else None
        resolved = (len(set(last_held) & set(a["ids"])) if isinstance(last_held, list) and a.get("ids") is not None else None)
        card["layers"][l] = {"auto_applied_this_week": a.get("auto_applied"), "undone_of_those": a.get("undone"), "undo_rate": rate,
                             "held_at_last_card_auto_applied_since": resolved,
                             "held_at_last_card": (len(last_held) if isinstance(last_held, list) else None),
                             "latest_day": hd.get(l), "pending": pd.get(l), "discovery": disc.get(l),
                             "shadow": ((sh or {}).get("layers") or {}).get(l) if isinstance(sh, dict) else None}
    card["week_on_week"] = _measure(lambda: compare(card, prev), None)
    return card


def _headline(card, l):
    empty = {"auto_applied_this_week": None, "undone_of_those": None, "held_latest_day": None,
             "pending_size": None, "discovery_queued": None}
    L = ((card or {}).get("layers") or {}).get(l) if isinstance(card, dict) else None
    if not isinstance(L, dict):
        return empty
    ld = L.get("latest_day") if isinstance(L.get("latest_day"), dict) else {}
    pd = L.get("pending") if isinstance(L.get("pending"), dict) else {}
    dc = L.get("discovery") if isinstance(L.get("discovery"), dict) else {}
    return {"auto_applied_this_week": _int(L.get("auto_applied_this_week")), "undone_of_those": _int(L.get("undone_of_those")),
            "held_latest_day": _int(ld.get("held")),
            "pending_size": _int(pd.get("size")),
            "discovery_queued": _int(dc.get("queued"))}


def compare(card, prev):
    if not isinstance(prev, dict) or not isinstance(prev.get("layers"), dict):
        return None
    out = {}
    for l in LAYERS:
        try:
            now_h, then_h = _headline(card, l), _headline(prev, l)
        except Exception:
            continue
        out[l] = {}
        for k in now_h:
            a, b = _int(now_h[k]), _int(then_h.get(k))
            out[l][k] = None if a is None or b is None else a - b
    return {"previous_week": prev.get("week"), "change": out}


def _v(x):
    return NO if x is None else str(x)


def _d(x):
    return "" if x is None else (" (%+d on last week)" % x)


def render(card):
    wow = ((card.get("week_on_week") or {}).get("change")) or {}
    L = ["# Self-sufficiency scorecard %s (PRIVATE, vault only)" % card["week"], "",
         "Window (UTC): %s to %s. Every count is this week or the latest saved run day, as labelled; nothing here is "
         "hand-verified (rule 59). \"%s\" means the input isn't in the saved run state." % (card["window_utc"][0][:16], card["window_utc"][1][:16], NO), ""]
    tot_a = [card["layers"][l]["auto_applied_this_week"] for l in LAYERS]
    hold_layers = ("foodbanks", "shelters", "warmspaces")
    tot_h = [((card["layers"][l]["latest_day"] or {}).get("held") if isinstance(card["layers"][l].get("latest_day"), dict) else None) for l in hold_layers]
    sw_ld = card["layers"]["sweep"].get("latest_day")
    sw_h = sw_ld.get("held") if isinstance(sw_ld, dict) else None
    pend_layers = tuple(PENDING_FILES)
    tot_p = [((card["layers"][l]["pending"] or {}).get("size") if isinstance(card["layers"][l].get("pending"), dict) else None) for l in pend_layers]
    L += ["## Summary", "",
          "1. Automatic opening-time changes this week: %s; later undone: %s." % (
              _partial_sum(tot_a, [LAYER_LABEL[l] for l in LAYERS]),
              _v(card["hand_check"]["auto_changes_undone_this_week"])),
          "2. Opening-time changes held on the latest run day (food banks, shelters, warm spaces): %s; sweep finds held: %s; "
          "places waiting in the held queue: %s." % (
              _partial_sum(tot_h, [LAYER_LABEL[l] for l in hold_layers]),
              _v(sw_h),
              _partial_sum(tot_p, [LAYER_LABEL[l] for l in pend_layers])),
          "3. Brake trip on file this week: %s; shadow trial: %s." % (
              _yn((card["brake"] or {}).get("trip_on_file_this_week")) if card.get("brake") is not None else NO,
              "recording" if card["shadow_trial"] else NO), ""]
    for l in LAYERS:
        c, w = card["layers"][l], wow.get(l) or {}
        ld, pd, dc = c["latest_day"], c["pending"], c["discovery"]
        L += ["## %s" % l, "",
              "- Auto-applied this week: %s%s; undone of those: %s; undo rate: %s" % (_v(c["auto_applied_this_week"]), _d(w.get("auto_applied_this_week")), _v(c["undone_of_those"]), _v(c["undo_rate"])),
              "- Held at last week's card and auto-applied since (resolved without a human): %s" % (NO if c["held_at_last_card_auto_applied_since"] is None else "%d of %d" % (c["held_at_last_card_auto_applied_since"], c["held_at_last_card"])),
              "- Latest run day: %s" % (NO if not ld else "%s: held %s%s, applied %s, stale cleared %s, coverage-gate blocks %s"
                                        % (_v(ld.get("run_day")), _v(ld.get("held")), _d(w.get("held_latest_day")), _v(ld.get("applied_that_day")), _v(ld.get("stale_cleared")), _v(ld.get("coverage_gate_blocks"))))]
        if ld and ld.get("hold_reasons"):
            L.append("- Hold reasons (places, latest day; first %s listed): %s" % (_v(ld.get("rejected_listed")), "; ".join("%s %d" % kv for kv in ld["hold_reasons"].items())))
        if ld:
            L.append("- Pages not opened (latest day): %s" % (NO if not ld["unreachable"] else ", ".join("%s %s" % kv for kv in ld["unreachable"].items())))
        if l in PENDING_FILES:
            L.append("- Held queue: %s" % (NO if not pd else "%d%s; also there at last week's card: %s; reasons: %s"
                                          % (pd["size"], _d(w.get("pending_size")), _v(pd["also_at_last_scorecard"]), "; ".join("%s %d" % kv for kv in pd["reasons"].items()) or "none")))
        L.append("- Discovery queue: %s" % (NO if not dc else "%s queued%s, %s added on %s; reasons: %s"
                                            % (_v(dc.get("queued")), _d(w.get("discovery_queued")), _v(dc.get("added_that_day")), _v(dc.get("day")), "; ".join("%s %d" % kv for kv in (dc.get("queue_reasons") or {}).items()) or "none")))
        sh = c["shadow"]
        L.append("- Shadow trial this week: %s" % (NO if not sh else "%s runs, %s candidates; differs from today: %s"
                                                   % (_v(sh.get("runs")), _v(sh.get("candidates")), ", ".join("%s %d" % kv for kv in (sh.get("differs_by_rule") or {}).items()) or "none")))
        r = (card["runs"] or {}).get(l)
        L.append("- Main runs this week: %s" % (NO if not r else "%d (success %d, failure %d, other %d)" % (r["runs"], r["success"], r["failure"], r["other"])))
        L.append("- State last saved: %s UTC" % _v(card["saved_at"].get(l)))
        L.append("")
    d, b, f, hc = card["discovery"], card["brake"], card["foodbank_page_failures"], card["hand_corrections"]
    L += ["## Across layers", "",
          "- Follow-through queue: %s" % (NO if not d["follow_through"] else "%d followed up this week (%d tracked)" % (d["follow_through"]["followed_up_this_week"], d["follow_through"]["tracked"])),
          "- Sweep finds waiting (latest sweep): %s" % (NO if not d["sweep_pending"] else "%d; %s" % (d["sweep_pending"]["size"], "; ".join("%s %d" % kv for kv in d["sweep_pending"]["reasons"].items()))),
          "- Discovery proposals for a reviewed PR: %s" % (NO if not d["verified_proposals"] else "%d (file of %s)" % (d["verified_proposals"]["places"], d["verified_proposals"]["generated"])),
          "- Anomaly brake: %s" % (NO if not b else "trip on file this week: %s, %s runs counted, most changes in a run %s, stop report on file: %s"
                                  % (_yn(b.get("trip_on_file_this_week")), _v(b.get("runs_counted_this_week")), _v(b.get("max_changes_in_a_run")), "yes" if b.get("stop_report_on_file") else "no")),
          "- Food bank own-site pages failed (latest full check): %s" % (NO if not f else "%d of %s, of which 403/429 %d" % (f["failed"], _v(f["checked"]), f["blocked_403_429"])),
          "- Hand corrections on file (learning report): %s" % (NO if not hc else "%s on %s (reachable %s, phone agreement %s)" % (_v(hc["hand_corrections_on_file"]), hc["day"], _v(hc["reachable_share"]), _v(hc["phone_agreement"]))),
          "- Hand-check outcomes: automatic changes undone this week %s; %s" % (_v(card["hand_check"]["auto_changes_undone_this_week"]), card["hand_check"]["note"]),
          "- Cities under the coverage bar: %s" % (NO if not card["cities"] else "%d of %d: %s" % (len(card["cities"]["under_the_bar"]), card["cities"]["top20_listed"], ", ".join(card["cities"]["under_the_bar"]) or "none")),
          "- Lancashire season: %s" % (NO if not card["lancashire"] else "%s rows, %s, hold lifts: %s" % (_v(card["lancashire"]["rows"]), json.dumps(card["lancashire"]["counts"]), card["lancashire"]["lifts_hold"])),
          "- Week on week: %s" % ("first scorecard, so " + NO if not card["week_on_week"] else "compared with " + str(card["week_on_week"]["previous_week"])),
          ""]
    return "\n".join(L)


def write(card, root):
    base = safe_out(root)
    os.makedirs(base, exist_ok=True)
    try:
        md = render(card) + "\n"
    except Exception as ex:
        md = "# Self-sufficiency scorecard %s (PRIVATE, vault only)\n\nMarkdown could not be built (%s). The JSON card next to this file has the counts.\n" % (card.get("week"), type(ex).__name__)
    for ext, body in (("json", json.dumps(card, indent=1, ensure_ascii=False, sort_keys=True) + "\n"), ("md", md)):
        p = os.path.join(base, "%s.%s" % (card["week"], ext))
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
    return os.path.join(base, card["week"] + ".md")


def main(argv=None, now=None, gh=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", default=os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "private-state", "site-run-state"))
    ap.add_argument("--root", default=".")
    ap.add_argument("--week")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        week = a.week or iso_week(now.date())
        if a.weekly and now.isoweekday() != 7:
            print("scorecard: weekly (Sundays), not this run"); return 0
        base = safe_out(a.root)
        if a.weekly and not a.force and os.path.exists(os.path.join(base, week + ".json")):
            print("scorecard: %s already written" % week); return 0
        if not any(os.path.isdir(os.path.join(a.state, l)) for l in LAYERS):
            print("scorecard: no saved run state to read, nothing written (fails closed)"); return 0
        prev = _load(os.path.join(base, prev_week(week) + ".json"))
        if prev is None:
            prev = _load(os.path.join(a.state, "sweep", "reports", "scorecard", prev_week(week) + ".json"))
        card = build(a.state, week, prev=prev, now=now, gh=gh)
        print("scorecard: wrote %s (private reports/scorecard/, carried by the private run state)" % os.path.relpath(write(card, a.root), a.root))
    except Exception as ex:   # never fails or blocks a run
        print("scorecard: skipped (%s)" % type(ex).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
