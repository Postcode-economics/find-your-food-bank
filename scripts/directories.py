"""Machine-readable national directories used for discovery each run. Each returns (candidates, status_dict).
On any failure the candidate list is empty and status says why: callers keep their existing data (fail safe)."""
import re, json, html, urllib.request, urllib.parse, concurrent.futures as cf
from discover import fetch_raw, text_of, norm_pc
IFAN_URL = "https://www.foodaidnetwork.org.uk/"   # IFAN 'find an independent food bank' map data (embedded page payload)
TRUSSELL_URL = "https://www.trussell.org.uk/emergency-food/find-a-foodbank"
HL_SEARCH = "https://homeless.org.uk/homeless-england/"
OI_PLACES = "https://open-innovations.github.io/warm-spaces/data/places.json"
OI_SOURCES = "https://open-innovations.github.io/warm-spaces/data/sources.json"
def _jsstr(s): return html.unescape(s.encode().decode("unicode_escape", "ignore")) if "\\" in s else html.unescape(s)

IFAN_REC = re.compile(r'\{_id:"(\w+)",contact:\[(.*?)\],locations:\[(.*?)\],name:"((?:[^"\\]|\\.)*)"')
IFAN_LOC = re.compile(r'lat:(-?[\d.]+),lng:(-?[\d.]+)\},postcode:"([^"]*)"')
IFAN_WEB = re.compile(r'_type:"website",value:"([^"]+)"')
def parse_ifan(page):
    out = []
    for oid, contact, locs, name in IFAN_REC.findall(page):
        web = IFAN_WEB.search(contact); n = _jsstr(name).strip()
        for k, (la, ln, pc) in enumerate(IFAN_LOC.findall(locs)):
            out.append({"id": f"ifan-{oid}-{k}", "name": n, "foodbank": n, "network": "IFAN", "postcode": pc.upper().strip(),
                        "lat": float(la), "lng": float(ln), "website": web.group(1) if web else "", "address": "",
                        "directory": "IFAN", "directory_url": IFAN_URL})
    return out
def ifan(fetcher=fetch_raw):
    r = fetcher(IFAN_URL)
    if r["http"] != 200: return [], {"status": f"failed: HTTP {r['http']}"}
    c = parse_ifan(r["html"])
    if len(c) < 200: return [], {"status": f"failed: schema check ({len(c)} records parsed, expected 500+)", "sha256": r.get("sha256")}
    return c, {"status": "ok", "count": len(c), "sha256": r.get("sha256"), "last_modified": r.get("last_modified")}
def trussell(fetcher=fetch_raw):
    """Trussell's finder is a postcode search behind Google reCAPTCHA with no public data feed. We do not bypass it.
    Trussell food banks are already in Give Food (network='Trussell'), so coverage comes from there."""
    r = fetcher(TRUSSELL_URL)
    blocked = "recaptcha" in (r.get("html") or "").lower()
    return [], {"status": "not scraped: " + ("finder is behind reCAPTCHA with no public feed; Trussell food banks come via Give Food" if blocked or r["http"] == 200 else f"HTTP {r['http']}")}

HL_Q = ["night shelter", "winter shelter", "direct access", "emergency accommodation", "emergency bed", "severe weather", "SWEP", "hostel", "rough sleepers", "assessment centre"]
def _field(t, a, b):
    m = re.search(re.escape(a) + r"\s*(.*?)\s*(?:" + b + ")", t); return m.group(1).strip() if m else ""
def parse_hl_service(slug, page_html):
    t = text_of(page_html)
    name = _field(t, "Share Accommodation", "Who is the project for") or slug.replace("-", " ").title()
    addr = _field(t, "Referral address", "Phone|Email|Website|Share")
    pcs = re.findall(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b", addr.upper())
    ref = _field(t, "Referral agencies", "Referral procedure|Support and accommodation")
    return {"id": "hl-" + slug, "name": name, "address": addr, "postcode": pcs[0] if pcs else "", "lat": None, "lng": None,
            "website": _field(t, "Website", "Share"), "phone": _field(t, "Phone", "Email|Website|Share"),
            "referral": ref, "who": _field(t, "Who do we help?", "Who we cannot help|Gender"),
            "directory": "Homeless Link", "directory_url": f"https://homeless.org.uk/homeless-england/service/{slug}/", "source_url": f"https://homeless.org.uk/homeless-england/service/{slug}/"}
def homeless_link(fetcher=fetch_raw, known=(), maxpages=15):
    """Search Homeless Link 'Find help' for accommodation services each run; fetch each service page not already known."""
    slugs, fails = set(), 0
    def run(q):
        out = set()
        for p in range(1, maxpages + 1):
            r = fetcher(HL_SEARCH + "?" + urllib.parse.urlencode({"query": q, "service_types": "accommodation", "page": p}))
            if r["http"] != 200: return q, out, True
            s = set(re.findall(r"service/([a-z0-9-]+)", r["html"]))
            if not s - out: break
            out |= s
        return q, out, False
    with cf.ThreadPoolExecutor(6) as ex:
        for q, s, f in ex.map(run, HL_Q): slugs |= s; fails += f
    if not slugs: return [], {"status": f"failed: no services returned ({fails} query failures)"}
    todo = sorted(s for s in slugs if "hl-" + s not in set(known))
    def one(s):
        r = fetcher(f"https://homeless.org.uk/homeless-england/service/{s}/")
        return parse_hl_service(s, r["html"]) if r["http"] == 200 else None
    with cf.ThreadPoolExecutor(12) as ex: c = [x for x in ex.map(one, todo) if x]
    return c, {"status": "ok", "services_listed": len(slugs), "fetched_new": len(c), "query_failures": fails}

def parse_oi(places, sources):
    out = []
    for n, p in enumerate(places):
        if p.get("_source") == "warm_welcome" or not p.get("title") or p.get("lat") is None: continue  # WW is pulled directly
        src = sources.get(p["_source"], {}) if isinstance(sources, dict) else {}
        contact = html.unescape(p.get("contact") or "")
        web = re.search(r"https?://[^\s<>\"']+", contact)
        addr = re.sub(r"\s+", " ", p.get("address") or "").strip()
        pcs = re.findall(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b", (addr + " " + (p.get("postcode") or "")).upper())
        hrs = (p.get("hours") or {}).get("_text", "") if isinstance(p.get("hours"), dict) else str(p.get("hours") or "")
        key = re.sub(r"[^a-z0-9]+", "-", (p["_source"] + "-" + p["title"] + "-" + (pcs[0] if pcs else str(round(p["lat"], 4)))).lower())[:90]
        out.append({"id": "oi-" + key, "name": html.unescape(p["title"]).strip(), "address": addr, "postcode": pcs[0] if pcs else "",
                    "lat": float(p["lat"]), "lng": float(p["lon"]), "website": web.group(0).rstrip(".,;)") if web else "",
                    "hours_text": hrs, "notes": re.sub(r"\s+", " ", p.get("description") or "")[:240],
                    "directory": "Open Innovations: " + (src.get("title") or p["_source"]),
                    "directory_url": p.get("url") or src.get("url") or OI_PLACES, "source_url": p.get("url") or src.get("url") or ""})
    return out
def open_innovations(fetcher=fetch_raw):
    r = fetcher(OI_PLACES); s = fetcher(OI_SOURCES)
    if r["http"] != 200: return [], {"status": f"failed: HTTP {r['http']}"}
    try:
        places = json.loads(r["html"]); srcs = json.loads(s["html"]) if s["http"] == 200 else {}
        if isinstance(srcs, list): srcs = {x.get("id") or x.get("_source") or str(i): x for i, x in enumerate(srcs)}
    except Exception as e: return [], {"status": f"failed: not JSON ({e})"}
    if not isinstance(places, list) or len(places) < 1000 or not all("_source" in p for p in places[:50]):
        return [], {"status": "failed: schema check"}
    c = parse_oi(places, srcs)
    return c, {"status": "ok", "count": len(c), "last_modified": r.get("last_modified"), "sha256": r.get("sha256")}
