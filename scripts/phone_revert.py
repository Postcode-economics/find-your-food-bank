"""Undo one automatic phone change: python scripts/phone_revert.py <website>.
Removes the fix from reports/phone_fixes.json, so the next refresh shows the main database's number again, marks the
entry reverted in reports/phone_auto_applied.json and blocks that exact number for that website
(overrides/phone_auto_undone.json), so the strict phone gate never re-applies it."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def _load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d
def revert(website, root=ROOT):
    lp = os.path.join(root, "reports", "phone_auto_applied.json")
    fp = os.path.join(root, "reports", "phone_fixes.json")
    bp = os.path.join(root, "overrides", "phone_auto_undone.json")
    log, fixes, blk = _load(lp, []), _load(fp, {}), _load(bp, {})
    rec = next((e for e in reversed(log) if e.get("website") == website and not e.get("reverted")), None)
    if not rec: raise SystemExit("no automatic phone change logged for " + website)
    rec["reverted"] = True
    if (fixes.get(website) or {}).get("new") == rec["new"]: fixes.pop(website)
    blk[website] = rec["new"]
    os.makedirs(os.path.dirname(bp), exist_ok=True)
    json.dump(log, open(lp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(fixes, open(fp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(blk, open(bp, "w", encoding="utf-8"), indent=1, sort_keys=True)
    return rec
if __name__ == "__main__": print("reverted", revert(sys.argv[1])["website"])
