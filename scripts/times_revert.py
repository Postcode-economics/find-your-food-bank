"""Undo one automatic times change: python scripts/times_revert.py <id>. Restores the old times from
reports/times_auto_applied.json (or removes the override if there were none) and marks the entry reverted."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def revert(k, root=ROOT):
    if ":" in k: return revert_crosscheck(k, root)
    lp, op = os.path.join(root, "reports", "times_auto_applied.json"), os.path.join(root, "overrides", "opening_times.json")
    log, cur = json.load(open(lp)), json.load(open(op))
    rec = next((r for r in reversed(log) if r["id"] == k and not r.get("reverted")), None)
    if not rec: raise SystemExit("no automatic change logged for " + k)
    if rec["old"]: cur[k] = rec["old"]
    else: cur.pop(k, None)
    rec["reverted"] = True
    json.dump(cur, open(op, "w"), indent=1, sort_keys=True, ensure_ascii=False); json.dump(log, open(lp, "w"), indent=1, ensure_ascii=False)
    return rec
def revert_crosscheck(key, root=ROOT):
    """Refresh-path change (key 'fb:<id>' / 'sh:<id>' / 'ws:<id>'): mark it reverted and block that exact change, so the next
    refresh keeps the old (main database) times and never re-applies it (overrides/times_auto_undone.json)."""
    lp, bp = os.path.join(root, "reports", "times_auto_applied.json"), os.path.join(root, "overrides", "times_auto_undone.json")
    kind, k = key.split(":", 1); log = json.load(open(lp)); blk = json.load(open(bp)) if os.path.exists(bp) else {}
    rec = next((r for r in reversed(log) if r.get("path") == "cross_check" and r["id"] == k and r.get("kind") == kind and not r.get("reverted")), None)
    if not rec: raise SystemExit("no automatic change logged for " + key)
    new = rec["new"]; st = new.get("structured") if isinstance(new, dict) and "structured" in new else None
    if st is None and isinstance(new, dict):   # shelter/warm-space hours: block by the parsed table recorded on the run
        st = rec.get("new_structured")
    blk[key] = json.dumps(st, sort_keys=True) if st else None
    rec["reverted"] = True
    os.makedirs(os.path.dirname(bp), exist_ok=True); json.dump(blk, open(bp, "w"), indent=1, sort_keys=True); json.dump(log, open(lp, "w"), indent=1, ensure_ascii=False)
    return rec
if __name__ == "__main__": print("reverted", revert(sys.argv[1])["id"])
