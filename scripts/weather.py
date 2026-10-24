"""Point 27 (24 Oct 2026, approved by Dean 08:59): weather / flood trigger. Official sources only (all Open Government Licence):
  Met Office UK warnings RSS, Environment Agency flood-monitoring API (England), SEPA flood warning feed (Scotland).
  Natural Resources Wales (24 Oct 2026, Dean): Live Flood Warnings & Alerts API v3 (key from env NRW_FLOOD_API_KEY or
  /workspace/secrets/nrw_flood_key.txt, never printed; 1 call per run, limit 10/min). Points mapped to a council via postcodes.io.
  Credit shown wherever NRW data is used: NRW_CREDIT.
Matches warning areas (council / county names) against shelter and warm space addresses and active SWEP councils, and
writes reports/weather.json + reports/weather.md. Immediate alerts (via digest.py) only for Met Office AMBER/RED and
severe flood warnings (EA severity 1, SEPA 'severe'). No map change. Never fails the job."""
import json, os, re, urllib.request, xml.etree.ElementTree as ET
ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)
MET = "https://www.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/UK"
EA = "https://environment.data.gov.uk/flood-monitoring/id/floods?min-severity=2"
SEPA = "https://floodline.sepa.org.uk/feed/"
GOVUK = "https://www.gov.uk/alerts/feed.atom"   # UK Emergency Alerts (OGL); point 27 add-on, Dean 24 Oct 2026
NRW = "https://api.naturalresources.wales/floodwarnings/v3/all"
NRW_CREDIT = "Contains Natural Resources Wales information \u00a9 Natural Resources Wales and database right"
def nrw_key():
    k = os.environ.get("NRW_FLOOD_API_KEY", "").strip()
    if not k:
        try: k = open("/workspace/secrets/nrw_flood_key.txt").read().strip()
        except Exception: k = ""
    return k
def get(u, headers=None): return urllib.request.urlopen(urllib.request.Request(u, headers=dict({"User-Agent": "helpmap.uk"}, **(headers or {}))), timeout=30).read()
def council_at(lat, lon):
    """Council (admin_district) for a point via postcodes.io reverse lookup; None if no postcode within 2 km."""
    try:
        r = json.loads(get("https://api.postcodes.io/postcodes?lon=%s&lat=%s&radius=2000&limit=1" % (lon, lat))).get("result") or []
        return r[0].get("admin_district") if r else None
    except Exception: return None
def nrw(js, locate=council_at):
    """NRW severity 1 = severe flood warning, 2 = flood warning (kept); 3 = flood alert, 4 = no longer in force (skipped, like SEPA alerts)."""
    out = []
    for f in json.loads(js).get("features", []):
        q = f.get("properties") or {}
        if q.get("SEVERITYVALUE") not in (1, 2): continue
        c = (f.get("geometry") or {}).get("coordinates") or [None, None]
        d = locate(c[1], c[0]) if c[0] is not None else None
        out.append({"source": "Natural Resources Wales", "title": "%s: %s" % (q.get("SEVERITY"), q.get("DESCRIPTION")), "level": "red" if q.get("SEVERITYVALUE") == 1 else "flood warning",
                    "areas": [d] if d else [], "link": "https://naturalresources.wales/flooding/check-flood-warnings/", "credit": NRW_CREDIT})
    return out
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
def govuk(xml, now=None):
    """UK Emergency Alerts still in force: entries whose summary has no 'Stopped:' time, or one still in the future.
    Government test alerts are kept out of the trigger (level 'test')."""
    import datetime as dt
    A = "{http://www.w3.org/2005/Atom}"; now = now or dt.datetime.now(dt.timezone.utc); out = []
    for e in ET.fromstring(xml).findall(A + "entry"):
        summ = e.findtext(A + "summary") or ""; title = e.findtext(A + "title") or ""
        m = re.search(r"Stopped: .*?\[(\d{4}-\d\d-\d\d \d\d:\d\d) (GMT|BST)\]", summ)
        if m:
            stop = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone(dt.timedelta(hours=1 if m.group(2) == "BST" else 0)))
            if stop <= now: continue
        body = " ".join(e.find(A + "content").itertext()) if e.find(A + "content") is not None else ""
        lnk = e.find(A + "link")
        out.append({"source": "UK Emergency Alerts", "title": "Emergency Alert: " + title, "level": "test" if re.search(r"\btest(ing)?\b", body, re.I) else "red",
                    "areas": [a.strip() for a in title.split(",") if a.strip()], "link": lnk.get("href") if lnk is not None else GOVUK})
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
    for name, url, fn in (("Met Office", MET, met), ("Environment Agency", EA, ea), ("SEPA", SEPA, sepa), ("UK Emergency Alerts", GOVUK, govuk)):
        try: ws += fn(get(url))
        except Exception as e: errs.append("%s: %s" % (name, e.__class__.__name__))
    k = nrw_key()
    if not k: errs.append("Natural Resources Wales: no API key")
    else:
        try: ws += nrw(get(NRW, {"Ocp-Apim-Subscription-Key": k}))
        except Exception as e: errs.append("Natural Resources Wales: %s" % e.__class__.__name__)   # class name only: never echo the key
    places = items("shelters.js") + items("warmspaces.js")
    try: swep = json.load(open(P("logs", "swep_status.json"))).get("active", [])
    except Exception: swep = []
    match(ws, places, swep)
    json.dump({"warnings": ws, "errors": errs, "credits": [NRW_CREDIT]}, open(P("reports", "weather.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# Weather and flood warnings (point 27)", "", "Sources: Met Office, Environment Agency, SEPA, Natural Resources Wales, UK Emergency Alerts (gov.uk/alerts).", "", NRW_CREDIT + ".", ""]
    L += ["- **%s** [%s] %s - shelters/warm spaces in area: %s; SWEP active: %s" % (w["source"], w["level"], w["title"], ", ".join(w["places"]) or "none matched", ", ".join(w["swep"]) or "none") for w in ws] or ["- no warnings"]
    L += ["", "Source errors: " + (", ".join(errs) or "none")]
    open(P("reports", "weather.md"), "w", encoding="utf-8").write("\n".join(L) + "\n"); return ws
if __name__ == "__main__":
    try: w = main(); print("weather warnings:", len(w), "urgent:", len(urgent(w)))
    except Exception as e: print("weather failed (not fatal):", e)
