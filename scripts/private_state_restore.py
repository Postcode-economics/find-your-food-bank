"""Merge the private vault's saved run state into this checkout (called by scripts/private_state.sh restore).

Layout in helpmap-research-backup: site-run-state/<layer>/{logs,reports}/... plus site-run-state/<layer>/.saved_at
(one folder per refresh layer and the sweep, so parallel runs never write the same path; Grok Bot 2 on #491).
A file only one layer saved is restored as is. A file several layers saved comes from the layer that saved last,
except the undo logs, which are the union of every layer's entries (an entry reverted anywhere stays reverted), and
the two-run times memory (SEEN_MAPS), which is merged key by key: each key's reading comes from the layer that owns it
(fb: food banks, sh: shelters, ws: warm spaces; the finder's map belongs to the sweep), exactly as that layer saved
it, so its run time still identifies the run that read it. A layer that saved the map is the only source for its own
keys, so a key it dropped stays dropped and another layer's older copy can never stand in as a first reading. Only
when the owner has never saved the map do other layers' copies count, newest reading first. Folders other than the
known layer labels are ignored, so nothing parked under site-run-state/ is ever restored as live memory.
Files already in the checkout always win. Prints '<files restored> present|missing'. 'missing' means no real state
was found (nothing, or only the practice probe file): the run then keeps times auto-apply off (auto_rules.state_ok).
Never prints file names or contents."""
import json, os, shutil, sys

PROBE = "logs/private_state_probe.json"
UNDO_LOGS = ("reports/times_auto_applied.json", "reports/phone_auto_applied.json")
LAYERS = ("foodbanks", "shelters", "warmspaces", "sweep", "run")   # the labels scripts/private_state.sh saves under
# Two-run times memory: key prefix -> the layer whose run writes those keys (discover.times_gate_apply drops and
# re-reads its own kind each run; times_finder rewrites its whole map and only the sweep runs it).
SEEN_MAPS = {"logs/times_crosscheck_seen.json": {"fb:": "foodbanks", "sh:": "shelters", "ws:": "warmspaces"},
             "logs/times_finder_seen.json": {"": "sweep"}}


def _layers(src):
    out = []
    if not os.path.isdir(src): return out
    if any(os.path.isdir(os.path.join(src, s)) for s in ("logs", "reports")): out.append((0.0, "", src))   # old flat layout
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        if d not in LAYERS or not os.path.isdir(p): continue
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


def _owner(owners, key):
    best = None
    for pre, layer in owners.items():
        if key.startswith(pre) and (best is None or len(pre) > len(best[0])): best = (pre, layer)
    return best[1] if best else None


def _seen_union(owners, copies):
    """copies: [(layer, map)] oldest save first. Returns the merged map; every entry is kept exactly as saved."""
    saved_by = {layer for layer, m in copies if isinstance(m, dict)}
    out = {}
    for layer, m in copies:
        if not isinstance(m, dict): continue
        for k, e in m.items():
            if not isinstance(e, dict): continue
            own = _owner(owners, k)
            if own in saved_by and own != layer: continue          # the owner's own save is the only source for its keys
            if own not in saved_by and k in out and str(out[k].get("run_at") or "") > str(e.get("run_at") or ""): continue
            out[k] = e                                               # same or newer reading, or the owner's copy
    return out


def restore(src, dst):
    pick, undo, seen = {}, {}, {}
    for _, d, p in _layers(src):
        for sub in ("logs", "reports"):
            for r, _, fs in os.walk(os.path.join(p, sub)):
                for f in fs:
                    full = os.path.join(r, f); rel = os.path.relpath(full, p).replace(os.sep, "/")
                    if rel in UNDO_LOGS: undo.setdefault(rel, []).append(full)
                    elif rel in SEEN_MAPS: seen.setdefault(rel, []).append((d, full))
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
    for rel, fulls in sorted(seen.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        if len(fulls) == 1:                                          # only one layer saved it: restored as is
            os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copy2(fulls[0][1], out); n += 1; real += 1; continue
        copies = []
        for d, f in fulls:
            try: copies.append((d, json.load(open(f, encoding="utf-8"))))
            except (OSError, ValueError): pass                       # an unreadable copy counts as not saved
        if not copies: continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh: json.dump(_seen_union(SEEN_MAPS[rel], copies), fh, indent=0, sort_keys=True, ensure_ascii=False)
        n += 1; real += 1
    return n, real > 0


if __name__ == "__main__":
    n, ok = restore(sys.argv[1], sys.argv[2])
    print(n, "present" if ok else "missing")
