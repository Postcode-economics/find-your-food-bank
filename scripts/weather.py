"""Point 27 (24 Oct 2026, approved by Dean 08:59): weather / flood trigger. Official sources only (all Open Government Licence):
  Met Office UK warnings RSS, Environment Agency flood-monitoring API (England), SEPA flood warning feed (Scotland).
  Natural Resources Wales (24 Oct 2026, Dean): Live Flood Warnings & Alerts API v3 (key from env NRW_FLOOD_API_KEY or
  /workspace/secrets/nrw_flood_key.txt, never printed; 1 call per run, limit 10/min). Points mapped to a council via postcodes.io.
  Credit shown wherever NRW data is used: NRW_CREDIT.
Matches warning areas (council / county names) against shelter and warm space addresses and active SWEP councils, and
writes reports/weather.json + reports/weather.md. Immediate alerts (via digest.py) only for Met Office AMBER/RED and
severe flood warnings (EA severity 1, SEPA 'severe'). No map change. Never fails the job.
Emergency shelter preview (25 Oct 2026): same feeds, extended with a red area banner, open-until expiry,
999 and Floodline on cards, and a text-only list. Nothing is shown on the live site unless the page is
opened with ?preview=emergency."""
import datetime, json, os, re, sys, urllib.request, urllib.error, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
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
def error_line(name, exc):
    """Name the feed and, for an HTTP error, the status code. Never the body, and never a key."""
    if isinstance(exc, urllib.error.HTTPError): return "%s: HTTP %s" % (name, exc.code)
    return "%s: %s" % (name, exc.__class__.__name__)
def get(u, headers=None):
    import rate_ledger
    if not rate_ledger.LEDGER.allow(u):
        rate_ledger.LEDGER.record(u, 429)
        raise urllib.error.HTTPError(u, 429, "paused this run", None, None)
    try:
        body = urllib.request.urlopen(urllib.request.Request(u, headers=dict({"User-Agent": "helpmap.uk"}, **(headers or {}))), timeout=30).read()
    except urllib.error.HTTPError as e:
        rate_ledger.LEDGER.record(u, e.code); raise
    rate_ledger.LEDGER.record(u, 200)
    return body
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
NATIONS = {"england", "wales", "scotland", "northern ireland"}
def triggering(w): return w["level"] in ("amber", "red", "flood warning")   # Met Office amber/red, EA/SEPA/NRW (severe) flood warnings, live UK Emergency Alerts
def councils_hit(w, councils):
    out = []
    for c in councils:
        for a in w.get("areas", []):
            if (a.strip().lower() in NATIONS and c.get("nation", "").lower() == a.strip().lower()) or hits(a, c["name"]) or hits(c["name"], a):
                out.append(c); break
    return out
def own_site(url, site):
    import urllib.parse as up
    h = lambda u: up.urlparse(u).netloc.split(":")[0].lower().replace("www.", "")
    return bool(site) and (h(url) == h(site) or h(url).endswith("." + h(site)))
def recheck(warnings, councils, sources, fetcher, run_day, threads=8):
    """Point 27 add-on (Dean 24 Oct 2026): when an alert covers a council area, re-check that council's own severe weather
    shelter page in this run. Only a page on the council's own site saying it is active sets open_tonight. Everything
    else (no page, unreachable, unclear, third-party page) goes to the review list. Never changes the map."""
    import swep, concurrent.futures as cf
    hit = {}
    for w in warnings:
        if not triggering(w): continue
        for c in councils_hit(w, councils): hit.setdefault(c["code"], (c, []))[1].append(w["source"] + ": " + w["title"])
    by = {}
    for x in sources: by.setdefault(x.get("code") or x.get("council"), []).append(x)
    def one(item):
        c, why = item
        urls = [x["url"] for x in by.get(c["code"], []) + by.get(c["name"], []) if x.get("url")]
        urls = list(dict.fromkeys(urls))[:3]
        res = {"code": c["code"], "council": c["name"], "alerts": why, "open_tonight": False, "pages": [], "review": None}
        for u in urls:
            r = fetcher(u); h = r.get("html") or r.get("text") or ""
            txt = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", h))
            st, q = swep.classify(txt, run_day) if r.get("http") == 200 else ("unreachable", "")
            res["pages"].append({"url": u, "http": r.get("http"), "status": st, "quote": q, "own_site": own_site(u, c.get("site"))})
        cond = lambda q: re.search(r"\b(if|when|whenever|until|will be updated)\b", q or "", re.I)   # e.g. "updated if SWEP is activated" is not an activation
        good = [p for p in res["pages"] if p["status"] == "active" and p["own_site"] and not cond(p["quote"])]
        if good: res["open_tonight"] = True; res["source_url"] = good[0]["url"]; res["quote"] = good[0]["quote"]
        elif not urls: res["review"] = "no severe weather shelter page on file - check the council's homelessness page"
        else: res["review"] = "council page not clear: " + "; ".join("%s (%s)" % (p["url"], p["status"]) for p in res["pages"])
        return res
    with cf.ThreadPoolExecutor(threads) as ex: return sorted(ex.map(one, hit.values()), key=lambda r: r["council"])
# --- Emergency shelter preview (25 Oct 2026). Dean's final colours: every red is #FF3B30, text on red is white.
# Not shown on the live site unless ?preview=emergency. Official numbers and stated facts only; never invent a shelter.
RED = "#FF3B30"
WHITE = "#FFFFFF"
FONT_STACK = 'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif'
OUTLINE_PX = 2
LEFT_EDGE_PX = 6
BADGE_PX = 16
BADGE_WEIGHT = 900
FLOODLINE = "0345 988 1188"
NI_FLOOD = "0300 2000 100"
BADGE = "Emergency shelter"
SWEP_BADGE = "Severe weather: open tonight"
FORBIDDEN = "Emergency: " + "open now"   # rejected wording; kept split so it is never a shown sentence
PREVIEW_FLAG = "emergency"
RUN_EVERY_MINUTES = 10
WATCHDOG_MINUTES = 60
OPEN_UNTIL_GRACE_H = 6
OPEN_UNTIL_CAP_H = 24
STALE_NOTE_MIN = 30
STALE_HIDE_H = 2
SWEP_UNREAD_H = 24
SWEP_DAILY_FROM = datetime.date(2026, 11, 1)
WEATHER_SOURCES = ("Met Office", "Environment Agency", "SEPA", "Natural Resources Wales")
SEARCH_TERMS = ("emergency shelter", "rest centre", "power cut", "emergency", "evacuation", "evacuate", "earthquake", "flood", "storm", "fire", "gas")
KEY_ENTRY = "Emergency shelter: a rest centre opened by the council in an emergency, such as a flood, fire, evacuation or power loss."
KEY_BADGE = "A red Emergency shelter badge means the council has opened it for an emergency."
KEY_SWEP = "A red Severe weather: open tonight badge means the council's Severe Weather Emergency Protocol (SWEP) is active, so extra emergency beds are open for people sleeping rough."
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
BGS_FEED = "https://www.earthquakes.bgs.ac.uk/feeds/MhSeismology.xml"

def _as_dt(v):
    if v is None: return None
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=datetime.timezone.utc)
    if isinstance(v, datetime.date):
        return datetime.datetime(v.year, v.month, v.day, tzinfo=datetime.timezone.utc)
    d = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)

def _td(v):
    if v is None: return None
    if isinstance(v, datetime.timedelta): return v
    return datetime.timedelta(hours=float(v))

def _vet(text):
    if text and FORBIDDEN in text: raise RuntimeError("refusing rejected emergency wording")
    return text

def is_ni(postcode=None, nation=None):
    if nation and str(nation).lower().replace(" ", "") in ("northernireland", "ni"): return True
    return (postcode or "").upper().replace(" ", "").startswith("BT")

def flood_contact(nation=None, postcode=None):
    if is_ni(postcode, nation): return ("Flooding NI", NI_FLOOD)
    return ("Floodline", FLOODLINE)

def flood_phrase(nation=None, postcode=None):
    label, num = flood_contact(nation, postcode)
    if label == "Flooding NI": return "Flooding NI: %s" % num
    return "Flood advice: Floodline %s" % num

def fmt_until(v):
    t = _as_dt(v).astimezone(ZoneInfo("Europe/London"))
    return "%02d:%02d %s %d %s" % (t.hour, t.minute, _DAYS[t.weekday()], t.day, _MONTHS[t.month - 1])

def fetch_all(getter, key):
    """Same four public feeds as main(), then NRW only when a key is present. The key is never copied into errors."""
    ws, errs, notes = [], [], []
    for name, url, fn in (("Met Office", MET, met), ("Environment Agency", EA, ea), ("SEPA", SEPA, sepa), ("UK Emergency Alerts", GOVUK, govuk)):
        try: ws += fn(getter(url))
        except Exception as e: errs.append(error_line(name, e))
    if not key:
        errs.append("Natural Resources Wales: no API key")
        notes.append("NRW skipped (no API key); other feeds still run")
    else:
        try: ws += nrw(getter(NRW, {"Ocp-Apim-Subscription-Key": key}))
        except Exception as e: errs.append(error_line("Natural Resources Wales", e))   # status code only: never echo the key
    return ws, errs, notes

def area_hit(warning, area):
    if not area: return False
    for a in warning.get("areas") or []:
        if not a: continue
        if a.strip().lower() == str(area).strip().lower() or hits(a, area) or hits(area, a): return True
    return False

def stated_cause(w):
    c = (w.get("cause") or "").strip()
    return c or None

def is_evacuation(w):
    if w.get("evacuation"): return True
    text = " ".join(str(w.get(k) or "") for k in ("title", "cause", "body"))
    if re.search(r"evacuat", text, re.I): return True
    return w.get("source") in WEATHER_SOURCES and w.get("level") == "red"

def allows_banner(w):
    if w.get("level") in ("yellow", "test", "trigger"): return False
    if w.get("banner") is False: return False
    if w.get("source_kind") in ("power", "bgs"): return False
    if w.get("level") in ("amber", "red", "flood warning"): return True
    if w.get("source") == "UK Emergency Alerts": return True
    return bool(w.get("evacuation"))

def should_ping(w):
    """Immediate ping for Dean: severe flood, Met Office red, a live Emergency Alert, or an evacuation. Not a power cut or an earthquake feed on its own."""
    if w.get("level") == "test" or w.get("source_kind") in ("power", "bgs"): return False
    if w.get("source") == "UK Emergency Alerts": return True
    if w.get("source") in WEATHER_SOURCES and w.get("level") == "red": return True
    return bool(is_evacuation(w))

def ping_for(w):
    if not should_ping(w): return None
    if w.get("source") == "UK Emergency Alerts": reason = "emergency alert"
    elif is_evacuation(w): reason = "evacuation"
    else: reason = "severe warning"
    return {"to": "Dean", "when": "immediately", "reason": reason, "title": w.get("title"), "source": w.get("source"), "sent": False}

def freshness(fetched_at, now):
    if not fetched_at: return "ok"
    age = _as_dt(now) - _as_dt(fetched_at)
    if age >= datetime.timedelta(hours=STALE_HIDE_H): return "hidden"
    if age >= datetime.timedelta(minutes=STALE_NOTE_MIN): return "stale"
    return "ok"

def weather_text(area, sources, updated, nation, postcode, evacuation):
    head = ("Evacuation alert in %s. Follow official instructions." % area) if evacuation else ("Severe weather warning for %s." % area)
    return _vet("⚠ %s If you are in danger, call 999. %s. Emergency shelters near you are shown in red. Source: %s, updated %s." % (head, flood_phrase(nation, postcode), sources, updated))

def general_text(area, cause, sources, updated, evacuation):
    if evacuation: head = "Evacuation alert in %s. Follow official instructions." % area
    elif cause: head = "Emergency in %s: %s." % (area, cause)
    else: head = "Emergency in %s." % area
    return _vet("⚠ %s If you are in danger, call 999. Follow instructions from the council and emergency services. Emergency shelters near you are shown in red. Source: %s, updated %s." % (head, sources, updated))

def banner_for(warnings, area, nation="england", postcode=None, now=None, fetched_at=None, updated="20:10"):
    now = _as_dt(now or datetime.datetime.now(datetime.timezone.utc))
    qualifying = [w for w in (warnings or []) if area_hit(w, area) and allows_banner(w)]
    fresh = freshness(fetched_at, now)
    links = [{"name": w.get("source"), "url": w.get("link")} for w in qualifying if w.get("link")]
    base = {"show": False, "text": None, "links": [], "stale_note": None, "layer_on": False, "ping": False, "pings": [], "swep_recheck": bool(qualifying), "fresh": fresh}
    if not qualifying: return base
    if fresh == "hidden":
        base["links"] = links
        return base
    weather = [w for w in qualifying if w.get("source") in WEATHER_SOURCES]
    non_weather = [w for w in qualifying if w.get("source") not in WEATHER_SOURCES]
    evac = any(is_evacuation(w) for w in qualifying)
    cause = next((stated_cause(w) for w in qualifying if stated_cause(w)), None)
    sources = ", ".join(dict.fromkeys(w.get("source") or "source" for w in qualifying))
    if weather and not non_weather:
        text = weather_text(area, sources, updated, nation, postcode, evac)
    else:
        text = general_text(area, cause, sources, updated, evac)
        if weather: text = _vet(text.replace("Follow instructions from the council and emergency services.", "Follow instructions from the council and emergency services. " + flood_phrase(nation, postcode) + "."))
    pings = [p for p in (ping_for(w) for w in qualifying) if p]
    note = None
    if fresh == "stale" and links:
        note = "Warning info may be out of date, check %s" % links[0]["url"]
    return {"show": True, "text": text, "links": links, "stale_note": note, "layer_on": True, "ping": bool(pings), "pings": pings, "swep_recheck": True, "fresh": fresh}

def resolve_open_until(stated, added, warning_end=None):
    """Source time if it states one. Otherwise the warning end plus 6 hours, and never more than 24 hours after it was added."""
    added = _as_dt(added)
    cap = added + datetime.timedelta(hours=OPEN_UNTIL_CAP_H)
    if stated: return _as_dt(stated)
    if warning_end: return min(_as_dt(warning_end) + datetime.timedelta(hours=OPEN_UNTIL_GRACE_H), cap)
    return cap

def browser_hide(open_until, now):
    """A cached page drops the card once open_until has passed. Equal to the deadline counts as passed."""
    if not open_until: return True
    return _as_dt(now) >= _as_dt(open_until)

def swep_show(active, unreadable_for=None):
    if not active: return False
    if _td(unreadable_for) is not None and _td(unreadable_for) > datetime.timedelta(hours=SWEP_UNREAD_H): return False
    return True

def swep_daily_due(day, alert=False):
    """From 1 Nov, every council SWEP page is re-checked daily. Any alert re-checks at once, including before then."""
    if alert: return True
    if isinstance(day, str): day = datetime.date.fromisoformat(day[:10])
    if isinstance(day, datetime.datetime): day = day.date()
    return day >= SWEP_DAILY_FROM

def card_from_source(src, now, warning_end=None, nation="england", postcode=None):
    """A card only from a council (or other official) announcement. Pets, access, beds and the cause are copied only when the source states them."""
    src = src or {}
    if src.get("example"): return {"publish": "hold", "tell_dean": "example data is never listed", "card": None}
    if not src.get("official_council"): return {"publish": "hold", "tell_dean": "needs OK first", "card": None}
    if src.get("closed"): return {"publish": "removed", "card": None, "tell_dean": "afterwards"}
    if not src.get("name"): return {"publish": "review", "tell_dean": "afterwards", "card": None, "reason": "no name stated by the source"}
    now = _as_dt(now)
    ou = resolve_open_until(src.get("open_until"), src.get("added") or now, warning_end)
    if browser_hide(ou, now): return {"publish": "expired", "card": None, "open_until": ou.isoformat()}
    label, num = flood_contact(nation or src.get("nation"), postcode or src.get("postcode"))
    card = {
        "badge": BADGE, "name": src["name"], "open_until": ou.isoformat(),
        "open_until_label": src.get("open_until_label") or fmt_until(ou), "address": src.get("address") or "",
        "emergency_number": "999", "flood_label": label, "flood_number": num, "official_council": True, "live": True,
    }
    if src.get("council"): card["opened_by"] = src["council"]
    if src.get("url") or src.get("source_url"): card["source_url"] = src.get("url") or src.get("source_url")
    if src.get("phone"): card["phone"] = src["phone"]
    if src.get("last_checked"): card["last_checked"] = src["last_checked"]
    if src.get("lat") is not None and src.get("lng") is not None: card["lat"], card["lng"] = src["lat"], src["lng"]
    cause = (src.get("opened_for") or src.get("cause") or "").strip()
    if cause: card["opened_for"] = cause
    for key in ("pets", "access", "beds"):
        if src.get(key) not in (None, "", False) and not re.search(r"not stated", str(src.get(key)), re.I): card[key] = src[key]
    if swep_show(src.get("swep_active"), src.get("swep_unreadable_for")): card["swep_badge"] = SWEP_BADGE
    _vet(json.dumps(card, default=str))
    return {"publish": "live", "tell_dean": "afterwards", "card": card}

def emergency_search(q):
    s = (q or "").lower()
    return any(t in s for t in SEARCH_TERMS)

def map_key(marker_live):
    """Fourth key entry. Wording still needs Dean's OK, and it is omitted until a shelter marker is actually live."""
    if not marker_live: return None
    return {"entry": KEY_ENTRY, "badge": KEY_BADGE, "swep": KEY_SWEP, "needs_dean_ok": True}

def low_data_list(postcode, checked, shelters, nation="england"):
    label, num = flood_contact(nation, postcode)
    lines = ["EMERGENCY SHELTERS near %s, checked %s" % (postcode, checked), "Danger to life: 999. %s: %s" % (label, num)]
    if not shelters: lines.append("No council rest centre is listed.")
    for i, s in enumerate(shelters or [], 1):
        lines.append("%d. %s, %s. Open until %s. Source: %s" % (i, s.get("name"), s.get("address") or "", s.get("open_until_label") or s.get("open_until"), s.get("source_url") or s.get("url") or ""))
    return _vet("\n".join(lines) + "\n")

def watchdog_due(last_success, now):
    """Alert Dean when the check has not succeeded for more than an hour."""
    if not last_success: return True
    return _as_dt(now) - _as_dt(last_success) > datetime.timedelta(minutes=WATCHDOG_MINUTES)

def monthly_drill(target="test"):
    """The monthly drill runs on a test copy only. A request to use the live site is refused and the live site is left unchanged."""
    if target != "test": return {"ok": False, "ran_on_live": False, "live_unchanged": True, "target": target}
    return {"ok": True, "ran_on_live": False, "live_unchanged": True, "target": "test"}

def inbox_trigger(message, warnings):
    """A flood-warning email to hello@ is a second trigger, and it is matched against the feed when the area is in both."""
    blob = "%s\n%s\n%s" % (message.get("from") or "", message.get("subject") or "", message.get("body") or "")
    low = blob.lower()
    if not re.search(r"flood warning|severe flood warning|flood alert", low): return None
    if not re.search(r"environment agency|sepa|natural resources wales|\bnrw\b|floodline", low): return None
    matched = None
    for w in warnings or []:
        for a in w.get("areas") or []:
            if a and a.lower() in low:
                matched = {"title": w.get("title"), "source": w.get("source"), "area": a}
                break
        if matched: break
    return {"trigger": True, "matched": matched}

def event_effect(kind, official_alert=False, council_notice=None, now=None, nation="england", postcode=None):
    """Power cuts, earthquakes, police and fire pages are triggers. They re-check the council. They do not create a shelter card by themselves."""
    now = _as_dt(now or datetime.datetime.now(datetime.timezone.utc))
    card, held = None, False
    if council_notice:
        d = card_from_source(council_notice, now, nation=nation, postcode=postcode)
        if d["publish"] == "live": card = d["card"]
        elif d["publish"] == "hold": held = True
    banner = bool(official_alert) and kind in ("bgs", "police", "fire")
    return {"trigger": True, "council_recheck": True, "banner": banner, "card": card, "held": held, "creates_card_from_event": False}

def bgs_triggers(xml):
    out = []
    for it in ET.fromstring(xml).iter("item"):
        out.append({"source": "BGS", "source_kind": "bgs", "title": it.findtext("title") or "", "level": "trigger", "areas": [], "trigger_only": True, "banner": False, "link": it.findtext("link")})
    return out

def power_trigger(source, area):
    return {"source": source, "source_kind": "power", "level": "trigger", "areas": [area] if area else [], "trigger_only": True, "banner": False, "title": "Power cut listed by %s" % source}

def parse_announcement(text, council, url, now=None):
    """Pull a rest centre only from a plain statement that it is open. Missing pets, access, beds or cause stay missing."""
    if re.search(r"\bif\b[^.]{0,50}\b(open|opened)\b", text or "", re.I): return None
    closed = re.search(r"\b(rest centre|emergency shelter|reception centre|evacuation centre)\b[^.]{0,120}\b(is (now )?closed|has closed|stood down)\b", text or "", re.I)
    if closed: return {"official_council": True, "closed": True, "council": council, "url": url}
    if not re.search(r"\b(rest centre|emergency shelter|reception centre|evacuation centre)\b", text or "", re.I): return None
    if not re.search(r"\b(is (now )?open|has opened|opened|opens)\b", text or "", re.I): return None
    m = re.search(r"\bat ([A-Z][^.\n]{2,80})", text)
    if not m: return {"official_council": True, "review": True, "council": council, "url": url, "reason": "no name stated by the source"}
    rec = {"official_council": True, "name": m.group(1).strip().rstrip(","), "council": council, "url": url, "added": _as_dt(now) if now else None, "address": ""}
    cm = re.search(r"\b(?:opened for|due to|because of)\s*:?\s*([A-Za-z][A-Za-z \-]{0,40})", text, re.I)
    if cm:
        cause = re.split(r"\b(open until|pets|access|beds)\b", cm.group(1).strip().rstrip("."), flags=re.I)[0].strip()
        if cause: rec["opened_for"] = cause
    if re.search(r"\bpets?\b[^.]{0,40}\ballowed\b", text, re.I): rec["pets"] = "allowed"
    if re.search(r"\bstep-free\b", text, re.I): rec["access"] = "step-free"
    bm = re.search(r"\b(\d+)\s+beds?\b", text, re.I)
    if bm: rec["beds"] = int(bm.group(1))
    return rec

def load_centres(path=None):
    path = path or P("overrides", "emergency_centres.json")
    try: data = json.load(open(path, encoding="utf-8"))
    except Exception: return []
    return [c for c in data if not c.get("example") and not c.get("invented")]

def compose(warnings, centres, area, now, fetched_at=None, nation="england", postcode=None, updated="20:10", preview=PREVIEW_FLAG, warning_end=None):
    """Full preview view for one searched area. preview other than 'emergency' returns an empty view: the live default stays unchanged."""
    now = _as_dt(now)
    banner = banner_for(warnings, area, nation=nation, postcode=postcode, now=now, fetched_at=fetched_at, updated=updated)
    cards, held = [], []
    for src in centres or []:
        d = card_from_source(src, now, warning_end=warning_end, nation=nation, postcode=postcode)
        if d["publish"] == "live" and d.get("card"):
            if not browser_hide(d["card"]["open_until"], now): cards.append(d["card"])
        elif d["publish"] == "hold": held.append({"name": src.get("name"), "tell_dean": d["tell_dean"]})
    checked = updated.split(" ")[0] if updated else fmt_until(now)
    state = {"preview": True, "banner": banner, "cards": cards, "held": held, "layer_on": bool(banner["layer_on"]),
             "key": map_key(bool(cards)), "pings": banner.get("pings") or [], "swep_recheck": banner.get("swep_recheck"),
             "text": low_data_list(postcode or area, checked, cards, nation)}
    if preview != PREVIEW_FLAG:
        return {"preview": False, "banner": {"show": False, "text": None, "layer_on": False, "ping": False, "pings": [], "stale_note": None, "links": []},
                "cards": [], "held": [], "layer_on": False, "key": None, "pings": [], "text": None, "swep_recheck": False, "live_default_unchanged": True}
    return state

def write_emergency_preview(warnings, errs, notes, root=None, now=None):
    """Write the preview report only. Does not change the map, weather.json, or the live default."""
    root = root or ROOT
    now = _as_dt(now or datetime.datetime.now(datetime.timezone.utc))
    cards = []
    for src in load_centres():
        d = card_from_source(src, now)
        if d["publish"] == "live" and d.get("card") and not browser_hide(d["card"]["open_until"], now): cards.append(d["card"])
    payload = {"preview_only": True, "goes_live_only_with_dean_ok": True, "generated": now.isoformat(timespec="seconds"),
               "errors": list(errs or []), "watchdog_notes": list(notes or []), "urgent": [w.get("title") for w in urgent(warnings or [])],
               "warnings": [{k: w.get(k) for k in ("source", "title", "level", "areas", "link", "cause", "source_kind", "evacuation")} for w in (warnings or [])],
               "cards": cards, "key": map_key(bool(cards)), "text_list": low_data_list("you", fmt_until(now), cards)}
    os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    json.dump(payload, open(os.path.join(root, "reports", "emergency_preview.json"), "w"), indent=1, ensure_ascii=False)
    return payload

def main():
    ws, errs, _notes = fetch_all(get, nrw_key())
    places = items("shelters.js") + items("warmspaces.js")
    try: swep = json.load(open(P("logs", "swep_status.json"))).get("active", [])
    except Exception: swep = []
    match(ws, places, swep)
    import datetime
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import swep as _s
        cs = json.load(open(P("scripts", "sweep_sources.json")))["councils"]
        srcs = json.load(open(P("overrides", "swep_sources.json"))) if os.path.exists(P("overrides", "swep_sources.json")) else []
        rc = recheck(ws, cs, srcs, _s._fetch, datetime.date.today().isoformat())
    except Exception as e: rc = []; errs.append("shelter page re-check: %s" % e.__class__.__name__)
    json.dump({"run": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "councils": rc}, open(P("logs", "swep_triggered.json"), "w"), indent=1, ensure_ascii=False)
    json.dump({"warnings": ws, "errors": errs, "credits": [NRW_CREDIT]}, open(P("reports", "weather.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# Weather and flood warnings (point 27)", "", "Sources: Met Office, Environment Agency, SEPA, Natural Resources Wales, UK Emergency Alerts (gov.uk/alerts).", "", NRW_CREDIT + ".", ""]
    L += ["- **%s** [%s] %s - shelters/warm spaces in area: %s; SWEP active: %s" % (w["source"], w["level"], w["title"], ", ".join(w["places"]) or "none matched", ", ".join(w["swep"]) or "none") for w in ws] or ["- no warnings"]
    L += ["", "## Alert-triggered council shelter page re-check", "", "Only the council's own page can turn on 'open tonight'. Nothing here changes the map.", ""]
    L += ["- **%s**: open tonight per council page %s" % (r["council"], r["source_url"]) for r in rc if r["open_tonight"]] or ["- no council page says open"]
    L += ["", "### Review list (unclear - not on the map)", ""] + (["- %s: %s (alerts: %s)" % (r["council"], r["review"], "; ".join(r["alerts"][:3])) for r in rc if r["review"]] or ["- none"])
    L += ["", "Source errors: " + (", ".join(errs) or "none")]
    open(P("reports", "weather.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    try:
        import rate_ledger
        if rate_ledger.LEDGER.counts: rate_ledger.save(day=datetime.date.today().isoformat())
    except Exception: pass
    return ws
if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "preview":
            got = fetch_all(get, nrw_key())
            print("emergency preview", write_emergency_preview(*got)["generated"])
        else:
            w = main(); print("weather warnings:", len(w), "urgent:", len(urgent(w)))
    except Exception as e: print("weather failed (not fatal):", e)
