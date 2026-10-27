"""Undo one automatic times change: python scripts/times_revert.py <id>. Restores the old times from
reports/times_auto_applied.json (or removes the override if there were none) and marks the entry reverted."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def revert(k, root=ROOT):
    lp, op = os.path.join(root, "reports", "times_auto_applied.json"), os.path.join(root, "overrides", "opening_times.json")
    log, cur = json.load(open(lp)), json.load(open(op))
    rec = next((r for r in reversed(log) if r["id"] == k and not r.get("reverted")), None)
    if not rec: raise SystemExit("no automatic change logged for " + k)
    if rec["old"]: cur[k] = rec["old"]
    else: cur.pop(k, None)
    rec["reverted"] = True
    json.dump(cur, open(op, "w"), indent=1, sort_keys=True, ensure_ascii=False); json.dump(log, open(lp, "w"), indent=1, ensure_ascii=False)
    return rec
if __name__ == "__main__": print("reverted", revert(sys.argv[1])["id"])
