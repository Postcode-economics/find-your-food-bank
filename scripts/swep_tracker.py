"""Point 2 (24 Oct 2026): council SWEP tracker. Reads logs/swep_full.json (written by swep.py full) and writes
reports/swep_tracker.md: the shrinking 'still to check' list (status unknown or unreachable), plus a per-day count
history in logs/swep_tracker.json so progress is visible. Read-only on the map data."""
import json, os, collections
ROOT = os.path.join(os.path.dirname(__file__), "..")
FULL = os.path.join(ROOT, "logs", "swep_full.json"); HIST = os.path.join(ROOT, "logs", "swep_tracker.json")
MD = os.path.join(ROOT, "reports", "swep_tracker.md")
TODO = ("unknown", "unreachable")
def todo(councils): return sorted((c for c in councils if c.get("status") in TODO), key=lambda c: (c.get("status"), c.get("council")))
def update(full=FULL, hist=HIST, md=MD):
    d = json.load(open(full)); cs = d["councils"]; left = todo(cs)
    h = json.load(open(hist)) if os.path.exists(hist) else {"days": {}}
    h["days"][d["run"]] = dict(councils=len(cs), still_to_check=len(left), status=dict(collections.Counter(c["status"] for c in cs)))
    json.dump(h, open(hist, "w"), indent=1, sort_keys=True)
    days = sorted(h["days"])[-14:]
    L = ["# SWEP tracker - %s" % d["run"], "", "Councils still to check (status unknown or unreachable): **%d of %d**." % (len(left), len(cs)), "",
         "| day | still to check |", "|---|---|"] + ["| %s | %d |" % (k, h["days"][k]["still_to_check"]) for k in days] + ["", "## Still to check", ""]
    L += ["- %s (%s) - %s" % (c["council"], c.get("nation", ""), c["status"]) for c in left]
    open(md, "w", encoding="utf-8").write("\n".join(L) + "\n"); return len(left)
if __name__ == "__main__": print("swep tracker: still to check", update())
