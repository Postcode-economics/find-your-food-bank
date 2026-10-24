"""Point 5 (24 Oct 2026): change log per food bank. Each refresh compares data.full.js with the last snapshot
(logs/entry_snapshot.json) and appends what changed to logs/entry_history.json, keyed by id (last 50 changes each).
Every change gets a label:
  'real closure (own site says closed)'  - removed and listed in overrides/foodbank_closed.json
  'removed from feed (not confirmed closed)' - removed for any other reason
  'new on map', or 'website/feed update' for a field change.
Read-only on the map data."""
import datetime, json, os
ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data.full.js"); SNAP = os.path.join(ROOT, "logs", "entry_snapshot.json")
HIST = os.path.join(ROOT, "logs", "entry_history.json"); CLOSED = os.path.join(ROOT, "overrides", "foodbank_closed.json")
FIELDS = ("name", "address", "postcode", "phone", "website", "opening_times", "lat", "lng")
KEEP = 50
def load_items(path):
    s = open(path, encoding="utf-8").read(); return json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", [])
def snap(items): return {i["id"]: {k: i.get(k) for k in FIELDS} for i in items}
def diff(old, new, closed, when):
    out = []
    for x in sorted(set(old) - set(new)):
        out.append(dict(id=x, when=when, change="removed", label="real closure (own site says closed)" if x in closed else "removed from feed (not confirmed closed)", name=old[x].get("name")))
    for x in sorted(set(new) - set(old)):
        out.append(dict(id=x, when=when, change="added", label="new on map", name=new[x].get("name")))
    for x in sorted(set(old) & set(new)):
        for k in FIELDS:
            if old[x].get(k) != new[x].get(k):
                out.append(dict(id=x, when=when, change=k, label="website/feed update", old=old[x].get(k), new=new[x].get(k)))
    return out
def update(data=DATA, snap_p=SNAP, hist_p=HIST, closed_p=CLOSED, when=None):
    when = when or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    new = snap(load_items(data))
    closed = set(json.load(open(closed_p))) if os.path.exists(closed_p) else set()
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else {}
    ch = []
    if os.path.exists(snap_p):
        old = json.load(open(snap_p)); ch = diff(old, new, closed, when)
        if len(ch) > 5000: print("entry history: %d changes looks wrong, not recorded" % len(ch)); return []
        for c in ch: hist.setdefault(c["id"], []).append(c); hist[c["id"]] = hist[c["id"]][-KEEP:]
    json.dump(hist, open(hist_p, "w"), separators=(",", ":"), sort_keys=True)
    json.dump(new, open(snap_p, "w"), separators=(",", ":"), sort_keys=True)
    return ch
if __name__ == "__main__": print("entry history: %d changes" % len(update()))
