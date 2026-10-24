"""Point 7 (24 Oct 2026): Yell / Charity Commission gap check - offline core.
Reads a LOCAL CSV export (e.g. a Charity Commission register extract or a Yell list saved by hand) and lists
food-bank-like organisations whose postcode is not on the map, into reports/gap_check.md. It does not download anything:
fetching the register / Yell is a new external source and waits for Dean's approval.
Usage: gap_check.py export.csv [name_column] [postcode_column]"""
import csv, json, os, re, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data.full.js"); MD = os.path.join(ROOT, "reports", "gap_check.md")
FOODISH = re.compile(r"food\s*bank|foodbank|food\s*pantry|community\s*pantry|food\s*share|food\s*larder|soup\s*kitchen", re.I)
norm = lambda p: re.sub(r"\s", "", p or "").upper()
def gaps(rows, on_map_pcs, name_col, pc_col):
    return [r for r in rows if FOODISH.search(r.get(name_col) or "") and norm(r.get(pc_col)) and norm(r.get(pc_col)) not in on_map_pcs]
def main(path, name_col="charity_name", pc_col="charity_contact_postcode"):
    s = open(DATA, encoding="utf-8").read(); pcs = {norm(i.get("postcode")) for i in json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]}
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", errors="replace")))
    g = gaps(rows, pcs, name_col, pc_col)
    L = ["# Gap check - %s" % os.path.basename(path), "", "%d food-bank-like names whose postcode is not on the map (to check by hand, not added automatically)." % len(g), ""]
    L += ["- %s - %s" % (r.get(name_col), r.get(pc_col)) for r in g]
    open(MD, "w", encoding="utf-8").write("\n".join(L) + "\n"); return g
if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(0)
    print("gap check:", len(main(*sys.argv[1:])))
