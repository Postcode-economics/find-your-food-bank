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
REAL_CHANGES = ("phone", "tel", "opening_times", "hours", "access", "closed", "removed", "notice", "added")
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
def week_of(when):
    d = datetime.date.fromisoformat(str(when)[:10]); y, w, _ = d.isocalendar(); return "%d-W%02d" % (y, w)

def add_tally(path, changes):
    """Count real changes per ISO week. Names, phones and addresses are not stored.
    The season boost is not changed here."""
    try: cur = json.load(open(path))
    except Exception: cur = {}
    counts = dict(cur.get("counts") or {}) if isinstance(cur, dict) else {}
    for c in changes or []:
        if c.get("change") not in REAL_CHANGES: continue
        o, n = c.get("old"), c.get("new")
        if isinstance(o, dict) and isinstance(n, dict) and {k: o.get(k) for k in ("raw", "structured")} == {k: n.get(k) for k in ("raw", "structured")}: continue
        try: key = week_of(c.get("when"))
        except Exception: continue
        counts[key] = int(counts.get(key) or 0) + 1
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"; json.dump({"counts": counts}, open(tmp, "w"), indent=0, sort_keys=True); os.replace(tmp, path)
    return counts

def years_of(counts):
    return sorted({k.split("-")[0] for k in (counts or {}) if "-W" in k})

def redact(hist, today, days=90):
    """Drop old and new values once a change is `days` old. The label, the field and the date stay."""
    try: today_d = datetime.date.fromisoformat(str(today)[:10])
    except Exception: return hist
    for rows in (hist or {}).values():
        if not isinstance(rows, list): continue
        for c in rows:
            if not isinstance(c, dict): continue
            try: age = (today_d - datetime.date.fromisoformat(str(c.get("when"))[:10])).days
            except Exception: continue
            if age >= days:
                c.pop("old", None); c.pop("new", None)
    return hist

def update(data=DATA, snap_p=SNAP, hist_p=HIST, closed_p=CLOSED, when=None, tally_p=None):
    when = when or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    new = snap(load_items(data))
    closed = set(json.load(open(closed_p))) if os.path.exists(closed_p) else set()
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else {}
    ch = []
    if os.path.exists(snap_p):
        old = json.load(open(snap_p)); ch = diff(old, new, closed, when)
        if len(ch) > 5000: print("entry history: %d changes looks wrong, not recorded" % len(ch)); return []
        for c in ch: hist.setdefault(c["id"], []).append(c); hist[c["id"]] = hist[c["id"]][-KEEP:]
        redact(hist, when)
    json.dump(hist, open(hist_p, "w"), separators=(",", ":"), sort_keys=True)
    json.dump(new, open(snap_p, "w"), separators=(",", ":"), sort_keys=True)
    add_tally(tally_p or os.path.join(os.path.dirname(hist_p), "week_counts.json"), ch)
    return ch
if __name__ == "__main__": print("entry history: %d changes" % len(update()))
