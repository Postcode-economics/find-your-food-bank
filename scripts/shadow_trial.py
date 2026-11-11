"""Two-week shadow trial of the proposed Phase 2 automatic rules (record only).

Plan: the 9 Nov self-sufficiency plan in the private vault, with Grok Bot 2's binding notes (9 Nov 14:19 GMT):
"Every Phase 2 rule: 2 weeks in shadow mode against the 08:00 hand-check first." Rules shadowed here, in Bot 2's
order (2.3 deferred; 2.6B and 2.7 rejected; 2.6A changes no rule):
  2.5   graduated trust per host: trust can only RAISE the evidence needed. A host is trusted after
        TRUST_MIN_APPLIES applies and no undo in TRUST_DAYS days; a new or unknown host, or missing memory, needs
        3 identical reads.
  2.1   per-item batch cap: above the blast cap, apply the strongest candidates up to the cap and hold the rest
        (instead of holding all). Two capped runs in a row still stop everything.
  2.2b  per-host coverage hold: when the coverage gate trips, hold only changes whose host had a failed read this
        run; keep the whole-layer stop when under 50% of source pages opened or render errors are over 25%.
  2.4   fewer days: a drop in days only when the page changed, the dropped day is nowhere on the page, the table
        was read identically on 3 runs at least 48 hours apart and the host is trusted.

What this module may do: read what the live gate already decided, and write ONLY under reports/shadow/ (ignored by
git; carried between runs by the private run state, scripts/private_state.sh). It never writes overrides/,
published data, phones, locks, the undo log, the two-run memory or opening times, and never changes an item.
It is switched on only by HELPMAP_SHADOW_TRIAL=1 (set on the main refresh and sweep steps). Every entry point
swallows its own errors: a shadow failure can never fail or change a refresh (fail closed = nothing recorded).
It records nothing when the run's saved state was not restored (HELPMAP_STATE_RESTORED != 1), so the start date
and the read counts can never be reset by a run that started without memory.
"""
from __future__ import annotations

import datetime, hashlib, json, os, re, sys, threading, urllib.parse

ENV = "HELPMAP_SHADOW_TRIAL"
OUT = os.path.join("reports", "shadow")
TRIAL = os.path.join(OUT, "trial.json")
TRIAL_DAYS = 14
TRUST_MIN_APPLIES = 10
TRUST_DAYS = 30
READS_UNTRUSTED = 3
SHRINK_GAP_HOURS = 48
COVER_FLOOR = 0.50
RENDER_CEIL = 0.25
RULES = ("2.5-host-trust", "2.1-per-item-cap", "2.2b-per-host-coverage", "2.4-fewer-days")
SOURCE = ("vault workspace/docs/self_sufficient_plan_2026-11-09.md, Phase 2 + Grok Bot 2 binding notes "
          "(9 Nov 2026 14:19 GMT): every Phase 2 rule 2 weeks in shadow against the 08:00 hand-check")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_WORDS = {"mon": r"\bmon(day)?s?\b", "tue": r"\btues?(day)?s?\b", "wed": r"\bwed(nesday)?s?\b",
             "thu": r"\bthu(rs?)?(day)?s?\b", "fri": r"\bfri(day)?s?\b", "sat": r"\bsat(urday)?s?\b",
             "sun": r"\bsun(day)?s?\b"}

_lock = threading.Lock()
_failed_hosts = {}   # layer -> set of hosts with a failed source read this process


def on():
    return os.environ.get(ENV) == "1"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _today():
    return _now().date().isoformat()


def host_of(url):
    try:
        h = (urllib.parse.urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return "foodbank.org.uk" if h == "foodbank.org.uk" or h.endswith(".foodbank.org.uk") else h


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _safe_path(root, *parts):
    """Every write goes through here: it must resolve inside <root>/reports/shadow."""
    base = os.path.realpath(os.path.join(root, OUT))
    p = os.path.realpath(os.path.join(root, OUT, *parts))
    if p != base and not p.startswith(base + os.sep):
        raise ValueError("shadow write outside reports/shadow refused")
    return p


# ---------------------------------------------------------------- hooks called from the live code (never raise)

def note_failed_reads(layer, failed_urls):
    """discover.read_sources: hosts whose source page did not open this run (input for 2.2b)."""
    try:
        if not on():
            return
        with _lock:
            s = _failed_hosts.setdefault(layer or "", set())
            for u in failed_urls or ():
                h = host_of(u)
                if h:
                    s.add(h)
    except Exception:
        pass


def snapshot(i, field, new, texts, home, why, decision):
    """One candidate as the live gate saw it, copied into plain values (the item itself is never kept)."""
    try:
        if not on():
            return None
        new = new or {}
        joined = "\n".join(t for t in (texts or ()) if isinstance(t, str))
        src = (home or {}).get("final_url") or (new.get("source_url") if isinstance(new, dict) else None)
        return json.loads(json.dumps({
            "id": i.get("id"), "name": i.get("name"), "postcode": i.get("postcode"),
            "source_url": src, "host": host_of(src),
            "new_raw": new.get("raw") if isinstance(new, dict) else None,
            "new_structured": new.get("structured") if isinstance(new, dict) else None,
            "old": i.get(field),
            "page_hash": hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16] if joined else None,
            "days_on_page": sorted(d for d, rx in DAY_WORDS.items() if re.search(rx, joined, re.I)) if joined else None,
            "why_today": list(why or []), "today": decision,
        }, default=str))
    except Exception:
        return None


def record(layer, rows, root, run_at=None, stats=None, applied_before=None):
    """Called once per gate pass. Returns the run record (or None). Never raises."""
    try:
        if not on() or not root:
            return None
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        if os.environ.get("HELPMAP_STATE_RESTORED") != "1":
            print("shadow trial: saved run state not restored this run; nothing recorded (fails closed)", flush=True)
            return None
        return _record(layer, rows, root, run_at or _now().isoformat(timespec="seconds"), stats or {}, applied_before)
    except Exception as ex:
        try:
            print("shadow trial: skipped (%s)" % type(ex).__name__, flush=True)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------- the trial

def trial_state(root, create=True):
    path = _safe_path(root, "trial.json")
    t = _load(path, {})
    if t.get("start") and t.get("end"):
        return t
    if not create:
        return {}
    start = datetime.date.fromisoformat(_today())
    t = {"start": start.isoformat(), "last_day": (start + datetime.timedelta(days=TRIAL_DAYS - 1)).isoformat(),
         "end": (start + datetime.timedelta(days=TRIAL_DAYS)).isoformat(), "days": TRIAL_DAYS,
         "rules": list(RULES), "source": SOURCE, "mode": "shadow (record only)",
         "compare_against": "08:00 hand-check of each place's own source (rule 67)"}
    _dump(path, t)
    return t


def host_trust(root, now=None):
    """{host: {"applies": n, "undone": n, "trusted": bool}} from the undo log (reports/times_auto_applied.json).
    Missing or unreadable log = no host is trusted (fails closed)."""
    now = now or _now()
    log = _load(os.path.join(root, "reports", "times_auto_applied.json"), [])
    out = {}
    cutoff = now - datetime.timedelta(days=TRUST_DAYS)
    for e in log:
        if not isinstance(e, dict):
            continue
        h = host_of(e.get("source_url"))
        if not h:
            continue
        at = e.get("second_run_at") or e.get("when") or ""
        try:
            t = datetime.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if t < cutoff:
            continue
        s = out.setdefault(h, {"applies": 0, "undone": 0})
        s["applies"] += 1
        if e.get("reverted"):
            s["undone"] += 1
    for s in out.values():
        s["trusted"] = s["applies"] >= TRUST_MIN_APPLIES and s["undone"] == 0
    return out


def _sig(st):
    return json.dumps(st, sort_keys=True) if st else None


def update_reads(mem, key, row, run_at):
    """Shadow-only read memory: identical consecutive reads per listing (the live two-run memory is untouched)."""
    sig = _sig(row.get("new_structured"))
    prev = mem.get(key) or {}
    if not sig:
        return prev
    if prev.get("sig") == sig:
        if prev.get("last_run_at") != run_at:
            prev = dict(prev, n=int(prev.get("n") or 0) + 1, last_run_at=run_at)
        if row.get("page_hash") and row.get("page_hash") != prev.get("page_hash"):
            prev = dict(prev, page_hash=row.get("page_hash"))
    else:
        prev = {"sig": sig, "n": 1, "first_run_at": run_at, "last_run_at": run_at, "page_hash": row.get("page_hash"),
                "page_hash_before": prev.get("page_hash") or prev.get("page_hash_before")}
    mem[key] = prev
    return prev


def _days(v):
    if isinstance(v, dict) and isinstance(v.get("structured"), dict):
        return {str(k)[:3].lower() for k, s in v["structured"].items() if s}
    if isinstance(v, dict):
        return {str(k)[:3].lower() for k, s in v.items() if s and str(k)[:3].lower() in DAYS and str(s).strip().lower() != "closed"}
    return set()


def classify(why):
    c = {"cap": [], "coverage": [], "shrink": [], "other": []}
    for w in why or []:
        w = str(w)
        if w.startswith("blast limit:"):
            c["cap"].append(w)
        elif w.startswith("coverage gate:"):
            c["coverage"].append(w)
        elif w.startswith("would cut known hours to fewer"):
            c["shrink"].append(w)
        else:
            c["other"].append(w)
    return c


def _hours_between(a, b):
    try:
        ta = datetime.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        tb = datetime.datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        return (tb - ta).total_seconds() / 3600.0
    except (TypeError, ValueError):
        return 0.0


def _decide_trust(trust):
    def d(r):
        if r["today"] != "apply":
            return "hold", "held today: " + "; ".join(r["why_today"][:3]), {}
        h = trust.get(r.get("host") or "") or {}
        n = int((r.get("reads") or {}).get("n") or 0)
        if h.get("trusted"):
            return "apply", "trusted host keeps 2 identical reads", {"host_record": h}
        if n >= READS_UNTRUSTED:
            return "apply", "new or low-trust host, %d identical reads" % n, {"host_record": h}
        return "hold", "new or low-trust host needs %d identical reads (has %d)" % (READS_UNTRUSTED, n), {"host_record": h}
    return d


def _strength(r, trust):
    reads = int((r.get("reads") or {}).get("n") or 0)
    trusted = 1 if (trust.get(r.get("host") or "") or {}).get("trusted") else 0
    change = len(_days(r.get("old")) ^ _days({"structured": r.get("new_structured") or {}}))
    return (-reads, -trusted, change, str(r.get("id")))


def _decide_cap(rows, trust, room, capped_last_run):
    eligible = [r for r in rows if r["today"] == "hold" and classify(r["why_today"])["cap"]
                and not [w for k, ws in classify(r["why_today"]).items() if k != "cap" for w in ws]]
    pick = {id(r) for r in sorted(eligible, key=lambda r: _strength(r, trust))[:max(0, room)]}
    def d(r):
        c = classify(r["why_today"])
        if r["today"] == "apply":
            return "apply", "same as today (cap not reached)", {}
        if not c["cap"]:
            return "hold", "held today for other reasons", {}
        if capped_last_run:
            return "hold", "capped two runs in a row: anomaly brake still stops everything", {}
        if id(r) in pick:
            return "apply", "within the cap of the strongest candidates", {"room": room}
        if c["other"] or c["coverage"] or c["shrink"]:
            return "hold", "held today for other reasons too", {}
        return "hold", "over the cap: waits for the next run", {"room": room}
    return d


def _decide_coverage(stats, failed):
    pages, opened = stats.get("source_pages"), stats.get("source_opened")
    att, err = int(stats.get("render_attempts") or 0), int(stats.get("render_errors") or 0)
    whole = []
    if isinstance(pages, int) and pages > 0 and isinstance(opened, int) and opened / pages < COVER_FLOOR:
        whole.append("under %d%% of source pages opened" % int(COVER_FLOOR * 100))
    if att >= 8 and err / att > RENDER_CEIL:
        whole.append("render errors over %d%%" % int(RENDER_CEIL * 100))
    def d(r):
        c = classify(r["why_today"])
        if r["today"] == "apply":
            return "apply", "same as today (coverage gate not tripped)", {}
        if not c["coverage"] or c["other"] or c["cap"] or c["shrink"]:
            return "hold", "held today for other reasons", {}
        if whole:
            return "hold", "whole-layer stop kept: " + "; ".join(whole), {}
        if (r.get("host") or "") in failed:
            return "hold", "this host had a failed read this run", {}
        return "apply", "its own host read fine; coverage hold lifted for this item", {}
    return d


def _decide_shrink(trust, now_iso):
    def d(r):
        c = classify(r["why_today"])
        if r["today"] == "apply":
            return "apply", "same as today (no drop in days)", {}
        if not c["shrink"] or c["other"] or c["cap"] or c["coverage"]:
            return "hold", "held today for other reasons", {}
        reads = r.get("reads") or {}
        dropped = sorted(_days(r.get("old")) - _days({"structured": r.get("new_structured") or {}}))
        on_page = set(r.get("days_on_page") or [])
        if r.get("days_on_page") is None:
            return "hold", "page text not available to check the dropped days", {"dropped": dropped}
        still = [x for x in dropped if x in on_page]
        if still:
            return "hold", "dropped day still on the page: " + ", ".join(still), {"dropped": dropped}
        if not reads.get("page_hash_before") or reads.get("page_hash_before") == reads.get("page_hash"):
            return "hold", "page change not seen yet", {"dropped": dropped}
        n = int(reads.get("n") or 0)
        span = _hours_between(reads.get("first_run_at"), now_iso)
        if n < 3 or span < SHRINK_GAP_HOURS:
            return "hold", "needs 3 identical reads over %dh (has %d over %.0fh)" % (SHRINK_GAP_HOURS, n, span), {"dropped": dropped}
        if not (trust.get(r.get("host") or "") or {}).get("trusted"):
            return "hold", "host not trusted yet", {"dropped": dropped}
        return "apply", "page changed, dropped days gone, 3 reads over 48h, trusted host", {"dropped": dropped}
    return d


def _record(layer, rows, root, run_at, stats, applied_before):
    import shadow_apply
    trial = trial_state(root)
    ldir = _safe_path(root, layer or "unknown")
    mem_path = os.path.join(ldir, "reads.json")
    mem = _load(mem_path, {})
    meta = mem.get("_meta") if isinstance(mem.get("_meta"), dict) else {}
    for r in rows:
        r["reads"] = dict(update_reads(mem, "%s:%s" % (layer, r.get("id")), r, run_at))
    trust = host_trust(root)
    with _lock:
        failed = set(_failed_hosts.get(layer or "", set()))
    cap_today = any(classify(r["why_today"])["cap"] for r in rows)
    room = 40 - int(applied_before or 0)
    deciders = {
        "2.5-host-trust": _decide_trust(trust),
        "2.1-per-item-cap": _decide_cap(rows, trust, room, bool(meta.get("capped_last_run")) and cap_today),
        "2.2b-per-host-coverage": _decide_coverage(stats, failed),
        "2.4-fewer-days": _decide_shrink(trust, run_at),
    }
    out = {"layer": layer, "run_at": run_at, "trial": trial, "candidates": len(rows),
           "today_applied": [r.get("id") for r in rows if r["today"] == "apply"],
           "failed_hosts": len(failed), "stats": {k: stats.get(k) for k in ("source_pages", "source_opened", "render_attempts", "render_errors")},
           "rules": {}}
    for rid, dec in deciders.items():
        rep = shadow_apply.shadow_run(rid, rows, dec, root=root, write=False, meta={"layer": layer})
        differs = [x for x in rep["would_apply"] if x["id"] not in out["today_applied"]] + \
                  [x for x in rep["would_hold"] if x["id"] in out["today_applied"]]
        keep = {r.get("id"): r for r in rows}
        def brief(x):
            r = keep.get(x["id"]) or {}
            return {"id": x["id"], "name": x.get("name"), "postcode": r.get("postcode"), "source_url": r.get("source_url"),
                    "new_raw": r.get("new_raw"), "new_structured": r.get("new_structured"), "old": r.get("old"),
                    "why_today": r.get("why_today"), "shadow": x["decision"], "reason": x["reason"]}
        out["rules"][rid] = {"summary": rep["summary"], "differs_from_today": [brief(x) for x in differs],
                             "errors": rep["errors"]}
    meta["capped_last_run"] = cap_today
    mem["_meta"] = meta
    _dump(mem_path, mem)
    day_path = os.path.join(ldir, "%s.json" % run_at[:10])
    day = _load(day_path, {})
    day.setdefault("day", run_at[:10]); day.setdefault("layer", layer); day.setdefault("runs", [])
    day["runs"] = [x for x in day["runs"] if x.get("run_at") != run_at] + [out]
    _dump(day_path, day)
    print("shadow trial: %s recorded %d candidate(s); differs from today: %s" % (
        layer, len(rows), ", ".join("%s %d" % (k, len(v["differs_from_today"])) for k, v in out["rules"].items())), flush=True)
    return out


# ---------------------------------------------------------------- reading the results (for the daily review)

def summary(root, day=None):
    """Plain text summary of one day's shadow results across layers (default: newest day found)."""
    base = os.path.join(root, OUT)
    trial = _load(os.path.join(base, "trial.json"), {})
    days = {}
    if os.path.isdir(base):
        for layer in sorted(os.listdir(base)):
            p = os.path.join(base, layer)
            if not os.path.isdir(p):
                continue
            for f in os.listdir(p):
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f):
                    days.setdefault(f[:10], []).append((layer, os.path.join(p, f)))
    if not days:
        return "shadow trial: no results yet"
    day = day or max(days)
    lines = ["Shadow trial %s to %s (review due %s). Day %s." % (trial.get("start"), trial.get("last_day"), trial.get("end"), day)]
    for layer, path in sorted(days.get(day, [])):
        d = _load(path, {})
        for run in d.get("runs", []):
            parts = ["%s: %d differ" % (rid, len(v.get("differs_from_today") or [])) for rid, v in (run.get("rules") or {}).items()]
            lines.append("- %s %s: %d candidates, %d applied today; %s" % (layer, run.get("run_at"), run.get("candidates") or 0,
                                                                           len(run.get("today_applied") or []), "; ".join(parts)))
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "summary":
        print(summary(argv[1] if len(argv) > 1 else ".", argv[2] if len(argv) > 2 else None))
        return 0
    print("usage: shadow_trial.py summary [root] [YYYY-MM-DD]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
