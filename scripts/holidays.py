"""Point 4 (24 Oct 2026, approved by Dean 08:59): holiday hours calendar - data and logic only, no layout change.
- Bank holidays per nation from https://www.gov.uk/bank-holidays.json (official, Open Government Licence). If the fetch
  fails the previous file is kept.
- Places whose own opening-times text mentions Christmas / bank holidays / school holidays are listed with that text.
- holiday_ahead(item, today) says whether a bank holiday in that place's nation falls in the next N days, so a later
  (approved) layout can show 'hours may differ'. School holidays: no single official UK source (set per council), so
  none are invented here.
Writes reports/holidays.json. Never fails the job."""
import datetime, json, os, re, sys, urllib.request
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "reports", "holidays.json"); URL = "https://www.gov.uk/bank-holidays.json"
SCOT = {"AB", "DD", "DG", "EH", "FK", "G", "HS", "IV", "KA", "KW", "KY", "ML", "PA", "PH", "TD", "ZE"}
TEXT = re.compile(r"christmas|xmas|boxing day|new year|bank holiday|easter|school holiday|half[- ]term", re.I)
def nation(pc):
    a = re.match(r"[A-Z]+", (pc or "").upper().strip()); a = a.group(0) if a else ""
    if a == "BT": return "northern-ireland"
    if a in SCOT: return "scotland"
    return "england-and-wales"
def bank_holidays(raw, today):
    return {n: [e for e in v.get("events", []) if e["date"] >= today.isoformat()] for n, v in raw.items()}
def holiday_ahead(item, today, bh, days=14):
    end = (today + datetime.timedelta(days=days)).isoformat()
    return [e for e in bh.get(nation(item.get("postcode")), []) if today.isoformat() <= e["date"] <= end]
def holiday_text(item):
    ot = item.get("opening_times") or item.get("hours"); t = json.dumps(ot, ensure_ascii=False) if ot else ""
    return [l for l in ((ot or {}).get("lines") or [(ot or {}).get("raw") or ""] if isinstance(ot, dict) else [str(ot)]) if l and TEXT.search(l)] if TEXT.search(t) else []
def main(today=None):
    today = today or datetime.date.today()
    old = json.load(open(OUT)) if os.path.exists(OUT) else {}
    try:
        raw = json.load(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "helpmap.uk"}), timeout=30))
        bh = bank_holidays(raw, today)
    except Exception as e:
        print("bank holiday fetch failed, keeping previous:", e); bh = old.get("bank_holidays", {})
    places = []
    for f in ("data.full.js", "shelters.js", "warmspaces.js"):
        p = os.path.join(ROOT, f)
        if not os.path.exists(p): continue
        s = open(p, encoding="utf-8").read()
        for i in json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", []):
            t = holiday_text(i)
            if t: places.append({"id": i.get("id"), "name": i.get("name"), "text": t})
    out = {"generated": today.isoformat(), "source": URL + " (Open Government Licence v3.0)", "bank_holidays": bh,
           "school_holidays": "not included - no single official UK source", "places_with_holiday_text": places}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False); return out
if __name__ == "__main__":
    try: o = main(); print("holidays:", {k: len(v) for k, v in o["bank_holidays"].items()}, "places with holiday text:", len(o["places_with_holiday_text"]))
    except Exception as e: print("holidays failed (not fatal):", e)
