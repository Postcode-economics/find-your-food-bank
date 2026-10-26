"""Point 2 (24 Oct 2026): council SWEP tracker. Reads logs/swep_full.json (written by swep.py full) and writes
reports/swep_tracker.md: the shrinking 'still to check' list (status unknown or unreachable), plus a per-day count
history in logs/swep_tracker.json so progress is visible. Read-only on the map data."""
import json, os, collections
ROOT = os.path.join(os.path.dirname(__file__), "..")
FULL = os.path.join(ROOT, "logs", "swep_full.json"); HIST = os.path.join(ROOT, "logs", "swep_tracker.json")
MD = os.path.join(ROOT, "reports", "swep_tracker.md")
TODO = ("unknown", "unreachable")
HAND = os.path.join(ROOT, "overrides", "swep_handcheck.json"); HAND_DAYS = 30  # hand checks (owner 24 Oct) settle a council for 30 days
def hand(path, run):
    import datetime
    try: h = json.load(open(path))
    except Exception: return {}
    out = {}
    for k, v in h.items():
        if k.startswith("_") or v.get("result") == "todo": continue
        try: age = (datetime.date.fromisoformat(run) - datetime.date.fromisoformat(v["checked"])).days
        except Exception: continue
        if 0 <= age <= HAND_DAYS: out[k] = v
    return out
def todo(councils): return sorted((c for c in councils if c.get("status") in TODO), key=lambda c: (c.get("status"), c.get("council")))
def update(full=FULL, hist=HIST, md=MD, handp=HAND):
    d = json.load(open(full)); cs = d["councils"]; hc = hand(handp, d["run"])
    left = [c for c in todo(cs) if c.get("code") not in hc]; done = [c for c in todo(cs) if c.get("code") in hc]
    h = json.load(open(hist)) if os.path.exists(hist) else {"days": {}}
    h["days"][d["run"]] = dict(councils=len(cs), still_to_check=len(left), status=dict(collections.Counter(c["status"] for c in cs)))
    json.dump(h, open(hist, "w"), indent=1, sort_keys=True)
    days = sorted(h["days"])[-14:]
    L = ["# SWEP tracker - %s" % d["run"], "", "Councils still to check (status unknown or unreachable): **%d of %d**." % (len(left), len(cs)), "",
         "| day | still to check |", "|---|---|"] + ["| %s | %d |" % (k, h["days"][k]["still_to_check"]) for k in days] + ["", "## Still to check", ""]
    L += ["- %s (%s) - %s" % (c["council"], c.get("nation", ""), c["status"]) for c in left]
    fl = [c for c in done if hc[c["code"]]["result"] in ("flag", "none")]
    L += ["", "## Hand-checked - needs owner or a better page (%d)" % len(fl), ""] + ["- %s - %s: %s (%s)" % (c["council"], hc[c["code"]]["result"], hc[c["code"]]["note"], hc[c["code"]]["url"]) for c in fl]
    L += ["", "## Hand-checked, settled for %d days (%d)" % (HAND_DAYS, len(done) - len(fl)), ""] + ["- %s - %s, checked %s" % (c["council"], hc[c["code"]]["note"], hc[c["code"]]["checked"]) for c in done if c not in fl]
    open(md, "w", encoding="utf-8").write("\n".join(L) + "\n"); return len(left)
if __name__ == "__main__": print("swep tracker: still to check", update())
