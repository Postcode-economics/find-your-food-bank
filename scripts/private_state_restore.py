"""Merge the private vault's saved run state into this checkout (called by scripts/private_state.sh restore).

Layout in helpmap-research-backup: site-run-state/<layer>/{logs,reports}/... plus site-run-state/<layer>/.saved_at
(one folder per refresh layer and the sweep, so parallel runs never write the same path; Grok Bot 2 on #491).
A file only one layer saved is restored as is. A file several layers saved comes from the layer that saved last,
except the undo logs, which are the union of every layer's entries (an entry reverted anywhere stays reverted), and
the intelligent mode summary (SUMMARIES), whose per-layer slots are merged: each run writes only its own layer's slot
(layers.foodbanks, .shelters, .warmspaces, .sweep), so every layer's slot for the newest day comes back, from that
layer's own save when it has one for that day, otherwise from the newest save of that day that carries it. The blast
caps (intelligent_rails.applied_today) then see every layer's applies, not only the last layer to save.
Files already in the checkout always win. Prints '<files restored> present|missing'. 'missing' means no real state
was found (nothing, or only the practice probe file): the run then keeps times auto-apply off (auto_rules.state_ok).
Never prints file names or contents."""
import json, os, shutil, sys

PROBE = "logs/private_state_probe.json"
UNDO_LOGS = ("reports/times_auto_applied.json", "reports/phone_auto_applied.json")
SUMMARIES = ("reports/intelligent_mode.json",)


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


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    except (OSError, ValueError): return None


def _summary_union(copies):
    """copies: [(folder, summary or None)] oldest save first. Only the newest day counts (intelligent_rails starts a new
    summary when the day changes). Returns None when no copy is a usable summary."""
    usable = [(d, c) for d, c in copies if isinstance(c, dict) and isinstance(c.get("run"), str)]
    if not usable: return None
    day = max(c["run"] for _, c in usable)
    same = [(d, c) for d, c in usable if c["run"] == day]
    out = dict(same[-1][1])                                         # other fields: the newest save of that day
    slots = {}
    for d, c in same:
        layers = c.get("layers") if isinstance(c.get("layers"), dict) else {}
        for name, slot in layers.items():
            if not isinstance(slot, dict): continue
            if name in slots and slots[name][0] == name and d != name: continue   # the layer's own save wins
            slots[name] = (d, slot)
    out["layers"] = {name: slot for name, (_, slot) in sorted(slots.items())}
    out["enabled"] = any(bool(c.get("enabled")) for _, c in same)
    out["generated_at"] = max(str(c.get("generated_at") or "") for _, c in same)
    blocks = []
    for _, c in same:
        for line in c.get("would_block") if isinstance(c.get("would_block"), list) else []:
            if line not in blocks: blocks.append(line)
    out["would_block"] = blocks
    out["alerts"] = sorted({a for s in out["layers"].values() for a in (s.get("alerts") or [])})
    return out


def restore(src, dst):
    pick, undo, summ = {}, {}, {}
    for _, d, p in _layers(src):
        for sub in ("logs", "reports"):
            for r, _, fs in os.walk(os.path.join(p, sub)):
                for f in fs:
                    full = os.path.join(r, f); rel = os.path.relpath(full, p).replace(os.sep, "/")
                    if rel in UNDO_LOGS: undo.setdefault(rel, []).append(full)
                    elif rel in SUMMARIES: summ.setdefault(rel, []).append((d, full))
                    else: pick[rel] = full            # layers are oldest first, so the newest save wins
    n = real = 0
    for rel, fulls in sorted(summ.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        merged = _summary_union([(d, _load(f)) for d, f in fulls]) if len(fulls) > 1 else None
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if merged is None: shutil.copy2(fulls[-1][1], out)          # one save, or nothing usable: the newest save as is
        else:
            with open(out, "w", encoding="utf-8") as fh: json.dump(merged, fh, indent=1, ensure_ascii=False)
        n += 1; real += 1
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
