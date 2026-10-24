"""Point 10 (24 Oct 2026): snapshot retention - safe core, NOT wired into any workflow yet.
take(dir): write a gzipped copy of data.full.js / shelters.js / warmspaces.js as <dir>/YYYY-MM-DD.json.gz
plan(dates, today): which snapshots are kept live vs moved to the archive:
  daily kept 30 days; after that a weekly one (Monday) is kept for 1 year; the first of each month is kept forever.
  Anything else older than 30 days goes to <dir>/archive/ - it is MOVED, never deleted.
Where snapshots live is Dean's decision (the repo is published by GitHub Pages; see point 17 off-GitHub backup)."""
import datetime, gzip, json, os, shutil, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
FILES = ("data.full.js", "shelters.js", "warmspaces.js")
def take(d, today=None, root=ROOT):
    today = today or datetime.date.today(); os.makedirs(d, exist_ok=True); p = os.path.join(d, "%s.json.gz" % today)
    with gzip.open(p, "wt", encoding="utf-8") as fh: json.dump({f: open(os.path.join(root, f), encoding="utf-8").read() for f in FILES if os.path.exists(os.path.join(root, f))}, fh)
    return p
def plan(dates, today):
    keep, archive = [], []
    for x in sorted(dates):
        age = (today - x).days
        if age <= 30 or x.day == 1 or (x.weekday() == 0 and age <= 365): keep.append(x)
        else: archive.append(x)
    return keep, archive
def apply(d, today=None):
    today = today or datetime.date.today()
    ds = {datetime.date.fromisoformat(f[:10]): f for f in os.listdir(d) if f.endswith(".json.gz")}
    _, arch = plan(ds, today); os.makedirs(os.path.join(d, "archive"), exist_ok=True)
    for x in arch: shutil.move(os.path.join(d, ds[x]), os.path.join(d, "archive", ds[x]))
    return arch
if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    print("snapshot:", take(sys.argv[1]), "archived:", apply(sys.argv[1]))
