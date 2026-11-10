"""Merge the private vault's saved run state into this checkout (called by scripts/private_state.sh restore).

Layout in helpmap-research-backup: site-run-state/<layer>/{logs,reports}/... plus site-run-state/<layer>/.saved_at
(one folder per refresh layer and the sweep, so parallel runs never write the same path; Grok Bot 2 on #491).
A file only one layer saved is restored as is. A file several layers saved comes from the layer that saved last,
except the undo logs, which are the union of every layer's entries (an entry reverted anywhere stays reverted), and
reports/learning_state.json, which is merged per key by the layer that writes it (see _learning_merge).
Files already in the checkout always win. Prints '<files restored> present|missing'. 'missing' means no real state
was found (nothing, or only the practice probe file): the run then keeps times auto-apply off (auto_rules.state_ok).
Never prints file names or contents."""
import json, os, shutil, sys

PROBE = "logs/private_state_probe.json"
UNDO_LOGS = ("reports/times_auto_applied.json", "reports/phone_auto_applied.json")
LEARNING = "reports/learning_state.json"
# learning_state.json is written by two runs: full_check and learning_signals in refresh.yml (saved as foodbanks) and
# sweep_daily (saved as sweep). A key belongs to the run that records it (its kind); note_heal (full_check only)
# can create a key before record does, with the default kind "source".
KEY_OWNER = {"foodbank_site": "foodbanks", "source": "foodbanks", "sweep_page": "sweep"}
SHARED = ("keys", "history", "total_checks", "version")      # every other top-level field is written by foodbanks only
FIELD_OWNER = "foodbanks"


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
        with open(path, encoding="utf-8") as fh: v = json.load(fh)
    except (OSError, ValueError): return None
    return v if isinstance(v, dict) and isinstance(v.get("keys", {}), dict) else None


def _learning_merge(copies):
    """copies: [(folder, state or None)] oldest save first; None is a copy that could not be read or is not a state.
    Newest save wins would let one run's copy, saved before the other run's save, drop the other run's work (the
    sweep copy has no change_counts, so the brake's run history was lost). Instead:
    - a key goes to its owner (KEY_OWNER by kind) when that layer saved the file: only its copy counts, so a key it
      pruned stays pruned and a carried older entry never wins. Owner saved the file decides, before it is read:
      an unreadable owner copy gives none of its keys (fail closed, as for the seen maps). Keys with no owner, or
      whose owner saved nothing, take the entry with the newest last_check (tie: later save).
    - change_counts, anomaly, tombstones and the signals fields go to foodbanks the same way (from the newest copy
      when foodbanks saved nothing).
    - history is the union of the per-run snapshots (exact duplicates once), by day, last 14; total_checks and
      version are the highest.
    Returns None when no copy is usable (the newest file is then copied as before)."""
    usable = [(d, s) for d, s in copies if s is not None]
    if not usable: return None
    saved_by = {d for d, _ in copies}
    own = {d: s for d, s in usable}
    out = {}
    if FIELD_OWNER in saved_by:
        src = own.get(FIELD_OWNER) or {}
        out.update({k: v for k, v in src.items() if k not in SHARED})
    else:
        for _, s in usable: out.update({k: v for k, v in s.items() if k not in SHARED})
    keys, best = {}, {}
    for i, (d, s) in enumerate(usable):
        for k, e in (s.get("keys") or {}).items():
            if not isinstance(e, dict): continue
            owner = KEY_OWNER.get(e.get("kind"))
            if owner in saved_by:
                if d != owner: continue
                keys[k] = e; best[k] = (True, "", i)
                continue
            rank = (False, str(e.get("last_check") or ""), i)
            if k not in best or (not best[k][0] and rank >= best[k]): keys[k] = e; best[k] = rank
    out["keys"] = keys
    hist, seen = [], set()
    for _, s in usable:
        for h in s.get("history") or []:
            if not isinstance(h, dict): continue
            j = json.dumps(h, sort_keys=True)
            if j not in seen: seen.add(j); hist.append(h)
    out["history"] = sorted(hist, key=lambda h: str(h.get("day") or ""))[-14:]
    nums = lambda f: [s[f] for _, s in usable if isinstance(s.get(f), int) and not isinstance(s.get(f), bool)]
    out["total_checks"] = max(nums("total_checks") or [0])
    out["version"] = max(nums("version") or [1])
    return out


def restore(src, dst):
    pick, undo, learn = {}, {}, []
    for _, d, p in _layers(src):
        for sub in ("logs", "reports"):
            for r, _, fs in os.walk(os.path.join(p, sub)):
                for f in fs:
                    full = os.path.join(r, f); rel = os.path.relpath(full, p).replace(os.sep, "/")
                    if rel in UNDO_LOGS: undo.setdefault(rel, []).append(full); continue
                    if rel == LEARNING: learn.append((d, full))
                    pick[rel] = full                  # layers are oldest first, so the newest save wins
    n = real = 0
    merged = _learning_merge([(d, _load(f)) for d, f in learn]) if len(learn) > 1 else None
    for rel, full in sorted(pick.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        if rel == LEARNING and merged is not None:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh: json.dump(merged, fh, indent=0, sort_keys=True)
            n += 1; real += 1
            continue
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
