"""Point 20 (24 Oct 2026, approved by Dean 08:59): CSV/JSON download files of the map data - files only, NO button (layout held).
Licence check (24 Oct 2026):
- Food banks: listings come via Give Food (givefood.org.uk/api rules: 'do good with the data, and credit us with a link';
  don't modify needed-item lists - none exported; don't bulk email/call). Exported with Give Food credit + link.
- Shelters: OpenStreetMap-sourced and Homeless Link-directory ones EXCLUDED (Homeless Link: no reuse licence found) (ODbL share-alike would bind the whole file); the rest are facts from
  operators' own public pages, exported with their source URL.
- Warm spaces: EXCLUDED - Warm Welcome (most entries) and the council/VCS directories state no reuse licence.
Only basic public facts are exported (no notes, internal flags or copied opening-times text).
Writes export/foodbanks.csv|json and export/shelters.csv|json + export/README.txt."""
import csv, datetime, json, os
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "export")
FB = ["id", "name", "network", "address", "postcode", "lat", "lng", "phone", "website"]
SH = ["id", "name", "operator", "address", "postcode", "lat", "lng", "phone", "website", "source", "source_url"]
CREDIT_FB = "Food bank listings: Give Food (https://www.givefood.org.uk) and helpmap.uk (https://helpmap.uk)"
def items(f):
    s = open(os.path.join(ROOT, f), encoding="utf-8").read(); return json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", [])
def shareable_shelter(i): s = (i.get("source") or "").lower(); return "openstreetmap" not in s and "homeless link" not in s  # Homeless Link directory: no reuse licence found
def write(name, rows, cols, credit, today):
    rows = [{c: r.get(c, "") for c in cols} for r in rows]
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols); w.writeheader(); w.writerows(rows)
    json.dump({"generated": today, "attribution": credit, "items": rows}, open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return len(rows)
def main(today=None):
    today = today or datetime.date.today().isoformat(); os.makedirs(OUT, exist_ok=True)
    n = {"foodbanks": write("foodbanks", items("data.full.js"), FB, CREDIT_FB, today),
         "shelters": write("shelters", [i for i in items("shelters.js") if shareable_shelter(i)], SH, "Shelter listings: helpmap.uk (https://helpmap.uk), from each operator's own page (see source_url)", today)}
    open(os.path.join(OUT, "README.txt"), "w").write("helpmap.uk data download - %s\n\n%s\nIf you reuse this data, credit Give Food and helpmap.uk with a link. Do not bulk email, call or message the contacts.\nDetails change daily - always check with the service before travelling.\nWarm spaces and OpenStreetMap / Homeless Link-sourced shelters are not included (no reuse licence / share-alike terms).\n" % (today, CREDIT_FB))
    return n
if __name__ == "__main__":
    try: print("export:", main())
    except Exception as e: print("export failed (not fatal):", e)
