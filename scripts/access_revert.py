"""Undo one automatic access flip: python scripts/access_revert.py <id>.

Restores the previous tag on the logged row, marks that row reverted, and blocks the id in
overrides/access_auto_undone.json so the next intelligent-mode refresh does not flip it again.
The published access.js file is rewritten only when this id is present in reports/access_tags.json.
"""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def revert(iid, root=ROOT):
    lp = os.path.join(root, "reports", "access_changes.json")
    tp = os.path.join(root, "reports", "access_tags.json")
    bp = os.path.join(root, "overrides", "access_auto_undone.json")
    log, tags, blk = _load(lp, []), _load(tp, {}), _load(bp, {})
    rec = next((e for e in log if e.get("id") == iid and not e.get("reverted") and not e.get("kind")), None)
    if not rec:
        raise SystemExit("no automatic access change logged for " + iid)
    rec["reverted"] = True
    was = rec.get("old")
    if iid in tags:
        if was and was != "unconfirmed":
            tags[iid] = dict(tags[iid], tag=was, was=rec.get("new"), reverted=True)
        else:
            tags.pop(iid, None)
    if not isinstance(blk, dict):
        blk = {}
    blk[iid] = was
    os.makedirs(os.path.dirname(bp), exist_ok=True)
    json.dump(log, open(lp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(tags, open(tp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(blk, open(bp, "w", encoding="utf-8"), indent=1, sort_keys=True)
    acc = os.path.join(root, "access.js")
    if os.path.exists(acc):
        raw = open(acc, encoding="utf-8").read()
        body = raw[raw.index("{") : raw.rindex("}") + 1]
        data = json.loads(body)
        if was and was != "unconfirmed":
            data[iid] = was
        else:
            data.pop(iid, None)
        open(acc, "w", encoding="utf-8").write("window.FB_ACCESS=" + json.dumps(data, separators=(",", ":")) + ";\n")
    return rec


if __name__ == "__main__":
    print("reverted", revert(sys.argv[1])["id"])
