"""Merge the private vault's saved run state into this checkout (called by scripts/private_state.sh restore).

Layout in helpmap-research-backup: site-run-state/<layer>/{logs,reports}/... plus site-run-state/<layer>/.saved_at
(one folder per refresh layer and the sweep, so parallel runs never write the same path; Grok Bot 2 on #491).
A file only one layer saved is restored as is. A file several layers saved comes from the layer that saved last,
except the undo logs, which are the union of every layer's entries (an entry reverted anywhere stays reverted).
Files already in the checkout always win. Prints '<files restored> present|missing'. 'missing' means no real state
was found (nothing, or only the practice probe file): the run then keeps times auto-apply off (auto_rules.state_ok).
Never prints file names or contents."""
import json, os, shutil, sys

PROBE = "logs/private_state_probe.json"
UNDO_LOGS = ("reports/times_auto_applied.json", "reports/phone_auto_applied.json")


def _layers(src):
    out = []
    if not os.path.isdir(src): return out
    if any(os.path.isdir(os.path.join(src, s)) for s in ("logs", "reports")): out.append((0.0, "", src))   # old flat layout
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        if d in ("logs", "reports") or d.startswith(".") or not os.path.isdir(p): continue
        try: t = float(open(os.path.join(p, ".saved_at"), encoding="utf-8").read().strip())
        except (OSError, ValueError): t = 0.0
        out.append((t, d, p))
    return sorted(out)


def _union(lists):
    key = lambda e: json.dumps({k: v for k, v in e.items() if k != "reverted"}, sort_keys=True)
    out, at = [], {}
    for lst in lists:
        for e in lst if isinstance(lst, list) else []:
            if not isinstance(e, dict): continue
            k = key(e)
            if k in at:
                if e.get("reverted"): out[at[k]]["reverted"] = True
                continue
            at[k] = len(out); out.append(dict(e))
    return out


def restore(src, dst):
    pick, undo = {}, {}
    for _, _, p in _layers(src):
        for sub in ("logs", "reports"):
            for r, _, fs in os.walk(os.path.join(p, sub)):
                for f in fs:
                    full = os.path.join(r, f); rel = os.path.relpath(full, p).replace(os.sep, "/")
                    if rel in UNDO_LOGS: undo.setdefault(rel, []).append(full)
                    else: pick[rel] = full            # layers are oldest first, so the newest save wins
    n = real = 0
    for rel, full in sorted(pick.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copy2(full, out); n += 1
        if rel != PROBE: real += 1
    for rel, fulls in sorted(undo.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        lists = []
        for f in fulls:
            try: lists.append(json.load(open(f, encoding="utf-8")))
            except (OSError, ValueError): pass
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh: json.dump(_union(lists), fh, indent=1, ensure_ascii=False); fh.write("\n")
        n += 1; real += 1
    return n, real > 0


if __name__ == "__main__":
    n, ok = restore(sys.argv[1], sys.argv[2])
    print(n, "present" if ok else "missing")
