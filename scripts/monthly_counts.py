"""Point 34 (24 Oct 2026): historical trends. Writes reports/monthly_counts.csv with one row per month
(month, foodbanks, shelters, warmspaces). Re-running in the same month updates that month's row; past months are never changed.
Counts are read straight from the data files; a missing file is written as blank, never 0."""
import csv, datetime, json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
FILES = {"foodbanks": "data.full.js", "shelters": "shelters.js", "warmspaces": "warmspaces.js"}
OUT = os.path.join(ROOT, "reports", "monthly_counts.csv")
COLS = ["month"] + list(FILES)
def count(path):
    if not os.path.exists(path): return ""
    s = open(path, encoding="utf-8").read(); return len(json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", []))
def update(out=OUT, root=ROOT, month=None):
    month = month or datetime.date.today().strftime("%Y-%m")
    rows = list(csv.DictReader(open(out, encoding="utf-8"))) if os.path.exists(out) else []
    row = {"month": month, **{k: count(os.path.join(root, f)) for k, f in FILES.items()}}
    rows = [r for r in rows if r["month"] != month] + [row]; rows.sort(key=lambda r: r["month"])
    t = out + ".tmp"
    with open(t, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS); w.writeheader(); w.writerows(rows)
    os.replace(t, out); return row
if __name__ == "__main__": print("monthly counts:", update())
