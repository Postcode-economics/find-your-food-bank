"""A monthly drill of the anomaly brake, on a copy.

The spike is never added to the real change counts, and this never writes
reports/anomaly_brake.md. Nothing is published.
"""
import json, os
import learning

LIVE = "anomaly_brake.md"

def spike_for(history):
    """A proposed change count the brake should stop, from the recorded counts only.
    Fewer than four counts: None. No count is invented."""
    counts = []
    for h in history or []:
        if isinstance(h, dict) and isinstance(h.get("changes"), int): counts.append(h["changes"])
        elif isinstance(h, int): counts.append(h)
    if len(counts) < 4: return None
    med = sorted(counts)[len(counts) // 2]
    return max(10, med * 3, med + 8)

def drill(history, note_path=None):
    """Run the brake on a copy of `history`. The list passed in is not changed.
    note_path, when given, receives the drill note only. It must not be the live brake file."""
    if note_path and os.path.basename(note_path) == LIVE:
        raise ValueError("the drill must not write the live brake file")
    copy = [dict(h) if isinstance(h, dict) else h for h in (history or [])]
    before = json.dumps(history, default=str)
    spike = spike_for(copy)
    if spike is None:
        result = learning.anomaly_brake(copy, 0)
        line = "Brake drill: not enough recorded runs to judge. No spike was added and nothing was published."
        stopped = False
    else:
        result = learning.anomaly_brake(copy, spike)
        stopped = bool(result["stop"])
        line = "Brake drill on a copy: a run of %d changes would %s. The real counts were not changed and nothing was published." % (
            spike, "be stopped" if stopped else "not be stopped")
    if json.dumps(history, default=str) != before or len(copy) != len(list(history or [])):
        raise RuntimeError("the drill changed the real change counts")
    if note_path:
        os.makedirs(os.path.dirname(note_path) or ".", exist_ok=True)
        tmp = note_path + ".tmp"
        open(tmp, "w", encoding="utf-8").write("# Brake drill (copy only)\n\n%s\n\nNothing was published.\n" % line)
        os.replace(tmp, note_path)
    return {"stop": stopped, "line": line, "published": False, "copy_only": True, "spike": spike, "reason": result.get("reason", "")}

def maybe(today, history, note_path):
    """Run the drill on the first day of the month. Any other day writes nothing."""
    if today.day != 1:
        return {"stop": False, "line": "not the first of the month - no drill, and the live brake is unchanged", "published": False, "wrote": False, "spike": None}
    info = drill(history, note_path=note_path)
    info["wrote"] = True
    return info
