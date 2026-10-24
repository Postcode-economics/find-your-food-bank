"""Point 27 (24 Oct 2026, approved by Dean 08:59): weather / flood trigger. Official sources only (all Open Government Licence):
  Met Office UK warnings RSS, Environment Agency flood-monitoring API (England), SEPA flood warning feed (Scotland).
  Natural Resources Wales: its flood API needs a registered key, so Wales is covered by Met Office warnings only.
Matches warning areas (council / county names) against shelter and warm space addresses and active SWEP councils, and
writes reports/weather.json + reports/weather.md. Immediate alerts (via digest.py) only for Met Office AMBER/RED and
severe flood warnings (EA severity 1, SEPA 'severe'). No map change. Never fails the job."""
import json, os, re, urllib.request, xml.etree.ElementTree as ET
ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)
MET = "https://www.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/UK"
EA = "https://environment.data.gov.uk/flood-monitoring/id/floods?min-severity=2"
SEPA = "https://floodline.sepa.org.uk/feed/"
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "helpmap.uk"}), timeout=30).read()
def met(xml):
    out = []
    for it in ET.fromstring(xml).iter("item"):
        t = it.findtext("title") or ""; d = it.findtext("description") or ""
        lvl = (re.match(r"(Yellow|Amber|Red)", t) or [None, "Yellow"])[1].lower()
        areas = [a.strip() for a in re.sub(r" valid from .*$", "", d.split(":", 1)[1] if ":" in d else "").split(",") if a.strip()]
        out.append({"source": "Met Office", "title": t, "level": lvl, "areas": areas, "link": it.findtext("link")})
    return out
def ea(js):
    return [{"source": "Environment Agency", "title": "%s: %s" % (i.get("severity"), i.get("description")), "level": "red" if i.get("severityLevel") == 1 else "flood warning",
             "areas": [x for x in [(i.get("floodArea") or {}).get("county")] if x], "link": i.get("@id")} for i in json.loads(js).get("items", []) if i.get("severityLevel") in (1, 2)]
def sepa(xml):
    out = []
    for it in ET.fromstring(xml).iter("item"):
        t = it.findtext("title") or ""
        if "ALERT" in t.upper() and "WARNING" not in t.upper(): continue   # flood alerts are routine; warnings only
        m = re.search(r"issued for (.+)$", t)
        out.append({"source": "SEPA", "title": t, "level": "red" if "SEVERE" in t.upper() else "flood warning", "areas": [m.group(1).strip()] if m else [], "link": it.findtext("link")})
    return out
def norm(a): return re.sub(r"\b(city of|county|council|borough|district|metropolitan|london borough of|royal borough of|and)\b", " ", a.lower()).split()
def hits(area, text):
    w = norm(area); t = " %s " % re.sub(r"[^a-z ]", " ", (text or "").lower())
    return bool(w) and " %s " % " ".join(w) in t
def items(f):
    try: s = open(P(f), encoding="utf-8").read(); return json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", [])
    except Exception: return []
def match(warnings, places, swep):
    for w in warnings:
        w["places"] = sorted({p.get("name") for p in places for a in w["areas"] for f in (p.get("address"), p.get("council")) if hits(a, f)})
        w["swep"] = sorted({c for c in swep for a in w["areas"] if hits(a, c)})
    return warnings
def urgent(warnings): return [w for w in warnings if w["level"] in ("amber", "red")]
def main():
    ws, errs = [], []
    for name, url, fn in (("Met Office", MET, met), ("Environment Agency", EA, ea), ("SEPA", SEPA, sepa)):
        try: ws += fn(get(url))
        except Exception as e: errs.append("%s: %s" % (name, e.__class__.__name__))
    places = items("shelters.js") + items("warmspaces.js")
    try: swep = json.load(open(P("logs", "swep_status.json"))).get("active", [])
    except Exception: swep = []
    match(ws, places, swep)
    json.dump({"warnings": ws, "errors": errs}, open(P("reports", "weather.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# Weather and flood warnings (point 27)", "", "Sources: Met Office, Environment Agency, SEPA (NRW needs an API key - Wales via Met Office only).", ""]
    L += ["- **%s** [%s] %s - shelters/warm spaces in area: %s; SWEP active: %s" % (w["source"], w["level"], w["title"], ", ".join(w["places"]) or "none matched", ", ".join(w["swep"]) or "none") for w in ws] or ["- no warnings"]
    L += ["", "Source errors: " + (", ".join(errs) or "none")]
    open(P("reports", "weather.md"), "w", encoding="utf-8").write("\n".join(L) + "\n"); return ws
if __name__ == "__main__":
    try: w = main(); print("weather warnings:", len(w), "urgent:", len(urgent(w)))
    except Exception as e: print("weather failed (not fatal):", e)
