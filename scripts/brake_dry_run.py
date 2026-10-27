"""Read-only dry-run of the anomaly brake on the refresh files already in the repo.

A run's change count is the number of rows in reports/access_changes.json with that
run's timestamp. That is the log full_check.py passes to learning.anomaly_brake
(new places, removals, access flips, phone fixes and closure notes). Review-only
flags are not in that log and are not counted.

Two decisions are printed. Both call learning.anomaly_brake. Neither writes a file
and neither publishes.

  live        what the next full_check will do: history is change_counts in
              reports/learning_state.json (missing until this brake has recorded
              four runs). The proposed count is the latest refresh run.
  recorded    the same brake on today's real runs: history is every earlier run
              in reports/daily_review.json, and the proposed count is the latest run.

No count is invented. A run with no access_changes rows counts as 0.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learning

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default

def refresh_runs(root):
    """Every run in daily_review, oldest first, with its real log length. No run is dropped or filled in."""
    review = _load(os.path.join(root, "reports", "daily_review.json"), {})
    changes = _load(os.path.join(root, "reports", "access_changes.json"), [])
    if not isinstance(review, dict): review = {}
    if not isinstance(changes, list): changes = []
    by_when = {}
    for c in changes:
        if isinstance(c, dict) and c.get("when"):
            by_when[c["when"]] = by_when.get(c["when"], 0) + 1
    rows = []
    for day in sorted(review):
        block = review[day]
        if not isinstance(block, dict): continue
        for run in block.get("runs") or []:
            if not isinstance(run, dict) or not run.get("at"): continue
            at = run["at"]
            rows.append({
                "day": str(day), "at": at, "changes": by_when.get(at, 0),
                "flips": run.get("flips"), "phone_fixes": run.get("phone_fixes"),
                "closures": run.get("closures", 0),
            })
    rows.sort(key=lambda r: r["at"])
    return rows

def _judge(history, proposed):
    """history is a list of {day, changes} or a note that there is no run to judge."""
    if proposed is None:
        return {"stop": False, "proposed": None, "median": None, "reason": "no refresh run recorded in reports/daily_review.json"}
    return learning.anomaly_brake(history, proposed)

def assess(root=None):
    """Return both brake decisions. Does not write anomaly_brake.md, learning_state, or any publish file."""
    root = root or ROOT
    rows = refresh_runs(root)
    latest = rows[-1] if rows else None
    prior = rows[:-1]
    proposed = latest["changes"] if latest else None
    history = [{"day": r["day"], "changes": r["changes"]} for r in prior]
    state = _load(os.path.join(root, "reports", "learning_state.json"), {})
    if not isinstance(state, dict): state = {}
    live_counts = state.get("change_counts") or []
    if not isinstance(live_counts, list): live_counts = []
    recorded = _judge(history, proposed)
    live = _judge(live_counts, proposed)
    judged = []
    for i, r in enumerate(rows):
        earlier = [{"day": p["day"], "changes": p["changes"]} for p in rows[:i]]
        flag = learning.anomaly_brake(earlier, r["changes"])
        judged.append(dict(r, stop=flag["stop"], median=flag["median"], reason=flag["reason"]))
    return {
        "published": False, "wrote": False,
        "latest": latest, "proposed": proposed,
        "history": history, "recorded": recorded,
        "live_change_counts": live_counts, "live": live,
        "runs": judged,
    }

def report(info):
    L = ["Anomaly brake dry-run. Nothing was published. No file was written.", ""]
    live, rec = info["live"], info["recorded"]
    n_live = len(info["live_change_counts"])
    L.append("Live path (what full_check will do on the latest run): %d recorded change_counts." % n_live)
    L.append("  proposed %s. stop=%s. %s" % (live.get("proposed"), live.get("stop"), live.get("reason")))
    L.append("Recorded refreshes (same brake, history = earlier runs only):")
    if not info["runs"]:
        L.append("  no runs in reports/daily_review.json")
    for r in info["runs"]:
        mark = "STOP" if r["stop"] else "ok"
        L.append("  %s  %s  changes %d  flips %s  phones %s  closures %s  [%s] %s" % (
            mark, r["at"], r["changes"], r["flips"], r["phone_fixes"], r["closures"],
            "median %s" % r["median"] if r["median"] is not None else "no median", r["reason"]))
    latest = info["latest"]
    if latest:
        L.append("Latest run %s would %s on the recorded history (%d earlier runs)." % (
            latest["at"], "STOP" if rec["stop"] else "not stop", len(info["history"])))
    L.append(rec.get("reason") or "")
    L.append("Nothing was published.")
    return "\n".join(L) + "\n"

def main():
    info = assess()
    sys.stdout.write(report(info))
    return 0

if __name__ == "__main__":
    sys.exit(main())
