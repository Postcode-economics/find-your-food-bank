"""Merge the private vault's saved run state into this checkout (called by scripts/private_state.sh restore).

Layout in helpmap-research-backup: site-run-state/<layer>/{logs,reports}/... plus site-run-state/<layer>/.saved_at
(one folder per refresh layer and the sweep, so parallel runs never write the same path; Grok Bot 2 on #491).
A file only one layer saved is restored as is. A file several layers saved comes from the layer that saved last,
except the undo logs, which are the union of every layer's entries (an entry reverted anywhere stays reverted), and
the intelligent mode summary (SUMMARIES), whose per-layer slots are merged: each run writes only its own layer's slot
(layers.foodbanks, .shelters, .warmspaces, .sweep), so every layer's slot for the newest day comes back, from that
layer's own save when it has one for that day, otherwise from the newest save of that day that carries it. The blast
caps (intelligent_rails.applied_today) then see every layer's applies, not only the last layer to save. Only a real
YYYY-MM-DD run day up to today counts. reports/learning_state.json is merged per key by the run that writes it
(see _learning_merge). The two-run times memory (SEEN_MAPS), which is merged key by key: each key's reading comes from the layer that owns it
(fb: food banks, sh: shelters, ws: warm spaces; the finder's map belongs to the sweep), exactly as that layer saved
it, so its run time still identifies the run that read it. A layer that saved the map is the only source for its own
keys, so a key it dropped stays dropped and another layer's older copy can never stand in as a first reading. A
layer counts as having saved the map when its folder holds the file, whatever is in it: a copy that cannot be read or
is not a map gives no readings for that layer's keys (fails closed: at most one extra run before a confirmation),
never a fallback to other layers' older copies. Only when the owner has never saved the map do other layers' copies
count, newest reading first (equal run times: the later save). A key no layer owns (unknown prefix) is always merged
that way: no layer can delete it, so the newest reading of it wins. Folders other than the
known layer labels are ignored, so nothing parked under site-run-state/ is ever restored as live memory.
Files already in the checkout always win. Prints '<files restored> present|missing'. 'missing' means no real state
was found (nothing, or only the practice probe file): the run then keeps times auto-apply off (auto_rules.state_ok).
Never prints file names or contents."""
import datetime, json, os, re, shutil, sys

PROBE = "logs/private_state_probe.json"
UNDO_LOGS = ("reports/times_auto_applied.json", "reports/phone_auto_applied.json")
SUMMARIES = ("reports/intelligent_mode.json",)
LEARNING = "reports/learning_state.json"
# learning_state.json is written by two runs: full_check and learning_signals in refresh.yml (saved as foodbanks) and
# sweep_daily (saved as sweep). A key belongs to the run that records it (its kind); note_heal (full_check only)
# can create a key before record does, with the default kind "source".
KEY_OWNER = {"foodbank_site": "foodbanks", "source": "foodbanks", "sweep_page": "sweep"}
SHARED = ("keys", "history", "total_checks", "version")      # every other top-level field is written by foodbanks only
FIELD_OWNER = "foodbanks"
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
    """copies: [(layer, map or None)] oldest save first; None = the layer saved the file but it is unreadable or not a
    map. Returns the merged map; every entry is kept exactly as saved."""
    saved_by = {layer for layer, _ in copies}                     # decided before parsing: presence, not content
    out = {}
    for layer, m in copies:
        if not isinstance(m, dict): continue                         # an unusable owner copy gives none of its keys
        for k, e in m.items():
            if not isinstance(e, dict): continue
            own = _owner(owners, k)
            if own in saved_by and own != layer: continue          # the owner's own save is the only source for its keys
            if own not in saved_by and k in out and str(out[k].get("run_at") or "") > str(e.get("run_at") or ""): continue
            out[k] = e                                               # same or newer reading, or the owner's copy
    return out


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    except (OSError, ValueError): return None


def _real_day(v, today):
    """A summary's run day must be a real calendar date written YYYY-MM-DD and not after today, so a bogus or
    future value can never outrank (and hide) today's saves or reset the blast caps."""
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v): return False
    try: return datetime.date.fromisoformat(v) <= today
    except ValueError: return False


def _summary_union(copies, today=None):
    """copies: [(folder, summary or None)] oldest save first. Only the newest real day counts (intelligent_rails starts
    a new summary when the day changes); copies without a valid day are ignored. Returns None when no copy is usable.
    A layer whose own copy is unreadable or has no valid day gives no slot of its own, so another save's carried copy
    of that slot (possibly an older, lower count) is used instead: nothing else holds a newer count for it."""
    today = today or datetime.date.today()
    usable = [(d, c) for d, c in copies if isinstance(c, dict) and _real_day(c.get("run"), today)]
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


def _load_state(path):
    v = _load(path)
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
    pick, undo, summ, seen, learn = {}, {}, {}, {}, []
    for _, d, p in _layers(src):
        for sub in ("logs", "reports"):
            for r, _, fs in os.walk(os.path.join(p, sub)):
                for f in fs:
                    full = os.path.join(r, f); rel = os.path.relpath(full, p).replace(os.sep, "/")
                    if rel in UNDO_LOGS: undo.setdefault(rel, []).append(full)
                    elif rel in SUMMARIES: summ.setdefault(rel, []).append((d, full))
                    elif rel in SEEN_MAPS: seen.setdefault(rel, []).append((d, full))
                    else:
                        if rel == LEARNING: learn.append((d, full))
                        pick[rel] = full            # layers are oldest first, so the newest save wins
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
    merged = _learning_merge([(d, _load_state(f)) for d, f in learn]) if len(learn) > 1 else None
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
        lists = [_load(f) for f in fulls]
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh: json.dump(_union(lists), fh, indent=1, ensure_ascii=False); fh.write("\n")
        n += 1; real += 1
    for rel, fulls in sorted(seen.items()):
        out = os.path.join(dst, rel)
        if os.path.exists(out): continue
        if len(fulls) == 1:                                          # only one layer saved it: restored as is
            os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copy2(fulls[0][1], out); n += 1; real += 1; continue
        copies = [(d, m if isinstance(m, dict) else None) for d, m in ((d, _load(f)) for d, f in fulls)]
        # an unreadable copy or one that is not a map is None but still counts as that layer's save
        if all(m is None for _, m in copies): continue                # nothing usable anywhere: nothing restored
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh: json.dump(_seen_union(SEEN_MAPS[rel], copies), fh, indent=0, sort_keys=True, ensure_ascii=False)
        n += 1; real += 1
    return n, real > 0


if __name__ == "__main__":
    n, ok = restore(sys.argv[1], sys.argv[2])
    print(n, "present" if ok else "missing")
