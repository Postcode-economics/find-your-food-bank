"""Full shelter directories, classification, and evidence (audit 31 Oct 2026).

Reads Homeless Link accommodation (every results page, not keyword search), Street Support
overnight services, Salvation Army Lifehouse place pages, and the NIHE self-referral hostel
list. Nothing here is published. Verified new shelters are written to
reports/verified_new_places.json for review.

A directory postcode is a referral address, never the pin. A shelter is proposable only when
its own page, or an official council/operator page, names it and shows a building postcode.
Women's refuges are dropped and never mapped. Phones are copied only from that confirming
page. Council-line fields are never set. This module does not write overrides/phone_baseline.json.
"""
import html, json, os, re, time, hashlib, datetime, threading, urllib.parse
import discover

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HL_SEARCH = "https://homeless.org.uk/homeless-england/"
SS_API = "https://www.streetsupport.net/api/services"
SA_SITEMAP = "https://www.salvationarmy.org.uk/sitemap.xml"
SA_INDEX = "https://www.salvationarmy.org.uk/homelessness/lifehouses"
NIHE_PAGE = "https://www.nihe.gov.uk/self-referral-hostels-for-homeless-applicants"
NIHE_PDF = "https://www.housingrights.org.uk/sites/default/files/documents/advice/Self%20referral%20hostels_June%202025.pdf"
PROPOSALS = os.path.join("reports", "verified_new_places.json")
INDEX = os.path.join("logs", "shelter_source_index.json")
CACHE = os.path.join("logs", "shelter_source_cache")
UA = {"User-Agent": "Mozilla/5.0 (compatible; HelpMapBot/1.0; +https://helpmap.uk/; shelter directory check, a few pages a day)"}

PC_RE = discover.PC_RE
GENERIC = {"ymca", "salvation", "army", "hostel", "hostels", "house", "centre", "center", "project",
           "trust", "housing", "association", "homeless", "night", "shelter", "shelters", "lifehouse",
           "street", "road", "lane", "place", "court", "lodge", "women", "womens", "men", "young",
           "supported", "independent", "services", "service", "community", "south", "north", "east", "west",
           "western", "eastern", "northern", "southern"}
REFUGE = re.compile(r"women'?s?\s+refuges?|domestic (?:abuse|violence) refuges?|women at risk of domestic abuse|women'?s\s+aid|\brefuges?\b", re.I)
PUBLISHABLE = re.compile(r"direct access|night ?shelter|emergency accommodation|emergency bed|\bhostels?\b|temporary (?:furnished )?accommodation|rapid access|rough sleep", re.I)
SUPPORTED = re.compile(r"\bemmaus\b|supported housing|supported accommodation|longer[- ]term|long[- ]term|move[- ]on|\bfoyer\b|shared (?:houses|flats)|supported lodgings", re.I)
DAY = re.compile(r"day ?centre|drop[- ]in", re.I)
SEASONAL = re.compile(r"night ?shelter|winter shelter|\bswep\b|severe weather|cold weather", re.I)
SEASON_DATES = re.compile(r"2026\s*[-/–]\s*27|2026\s*/\s*2027|winter\s+2026|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+202[67]", re.I)
# '12-24 hours' is a reply time, not opening hours. 'No referral needed' is not a referral.
ACCESS_RE = re.compile(r"(?<![\d-])24\s*/\s*7|(?<![\d-])24\s*hours|direct access|(?<![\w-])self[- ]referr|(?<!\bno\s)referral (?:only|needed|required|via)|(?<!\bno\s)by referral|referred by|must be referred|(?<![\w-])walk[- ]in", re.I)
REFERRAL_ACCESS = re.compile(r"(?<!\bno\s)referral (?:only|needed|required|via)|(?<!\bno\s)by referral|must be referred|referred by", re.I)
NOT_ACCESS = re.compile(r"do not accept self|not accept self|no self[- ]referral|\bno referral\b", re.I)
OPEN_ACCESS = re.compile(r"self[- ]referral|direct access|open access|walk[- ]in", re.I)
TIMES_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|–|to)\s*\d{1,2}|24\s*/\s*7|24\s*hours|open 24", re.I)
FOOTER = re.compile(r"territorial headquarters|registered charity|champion park|company number|charity number", re.I)
HQ_PHONE = re.compile(r"territorial headquarters|champion park|head office", re.I)
REFERRAL_CTX = re.compile(r"referral address|referral via|housing options|council office|head office|for referrals", re.I)
WHERE = re.compile(r"where we are|our address|find us", re.I)
PHONE_RE = re.compile(r"(?:\+44\s?|0)\d(?:[\d\s-]{8,14})\d")
LOCATE = re.compile(r"Locate\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")
SS_OVERNIGHT = {"emergency", "hostel", "shelter"}
SS_SUPPORTED = {"supported", "social", "rented"}
COUNCIL_KEYS = ("council", "council_phone", "council_ooh", "council_url", "council_label", "council_label_cy")

def norm_pc(p): return discover.norm_pc(p)
def _text(h): return discover.text_of(h or "")
def distinctive(name):
    return discover.tokens(name) - GENERIC
def split_pc(p):
    n = norm_pc(p)
    if not re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", n or ""): return None
    return n[:-3], n[-3:]
def postcodes_near(a, b):
    """Same postcode, or the same sector with the unit letters one step apart (CV1 4EZ and CV1 4EY)."""
    A, B = split_pc(a), split_pc(b)
    if not A or not B: return False
    if A == B: return True
    if A[0] != B[0] or A[1][0] != B[1][0]: return False
    return sum(x != y for x, y in zip(A[1][1:], B[1][1:])) <= 1
def same_place(name_a, pcs_a, name_b, pc_b):
    """Same listing under a slightly different postcode: shared distinctive name and a near postcode."""
    if not pc_b: return False
    da, db = distinctive(name_a), distinctive(name_b)
    pcs = [p for p in pcs_a if p]
    if any(norm_pc(p) == norm_pc(pc_b) for p in pcs):
        if da & db: return True
        if not da and not db and discover.tokens(name_a) & discover.tokens(name_b): return True
    return bool(da and db and da & db and any(postcodes_near(p, pc_b) for p in pcs))
def names_place(text, name):
    words = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    d = distinctive(name)
    if not d: return bool(discover.tokens(name) & words)
    need = d if len(d) <= 3 else set(sorted(d)[:3])
    return need <= words
def _snip(text, m):
    start = max(0, (text.rfind(".", 0, m.start()) + 1))
    end = text.find(".", m.end())
    return re.sub(r"\s+", " ", text[start: end if end != -1 else m.end() + 60]).strip(" -")[:180]
def access_route(text):
    """A quoted access route. Satisfies the 21 Oct rule ('opening times or how to get in') without clock times.
    A referral sentence wins when the page also says direct access, so the card can say a referral is needed.
    'No referral needed' and 'we do not accept self-referrals' are not those routes."""
    snips = []
    for m in ACCESS_RE.finditer(text or ""):
        snip = _snip(text, m)
        if NOT_ACCESS.search(snip): continue
        snips.append(snip)
    for snip in snips:
        if REFERRAL_ACCESS.search(snip): return snip
    return snips[0] if snips else ""
def referral_based(route):
    if not route or NOT_ACCESS.search(route) or not REFERRAL_ACCESS.search(route): return False
    if OPEN_ACCESS.search(route) and not REFERRAL_ACCESS.search(route): return False
    return True
def access_type_of(route):
    if not route: return ""
    if referral_based(route): return "referral_only"
    if re.search(r"self[- ]referral", route, re.I): return "self_referral"
    if re.search(r"direct access|open access|walk[- ]in|24\s*/\s*7|24\s*hours", route, re.I): return "open_access"
    return ""
def has_times(text): return bool(TIMES_RE.search(text or ""))
def seasonal_reason(name, text):
    blob = (name or "") + " " + (text or "")
    if re.search(r"all year|year[- ]round|\b365\b", blob, re.I): return ""
    if re.search(r"winter\s+20(?:1\d|2[0-5])\b", blob, re.I) and not SEASON_DATES.search(blob):
        return "seasonal night shelter: held until 2026-27 dates appear"
    if not SEASONAL.search(blob): return ""
    if SEASON_DATES.search(blob): return ""
    return "seasonal night shelter: held until 2026-27 dates appear"
def is_refuge(name, text):
    blob = (name or "") + " " + (text or "")
    if re.search(r"women'?s\s+aid|women at risk of domestic abuse|women'?s?\s+refuges?|domestic (?:abuse|violence) refuges?", blob, re.I):
        return True
    return bool(re.search(r"\brefuges?\b", blob, re.I) and re.search(r"women|domestic", blob, re.I))
EMERGENCY_BEDS = re.compile(r"direct access|emergency accommodation|emergency beds?|night shelter|emergency shelter", re.I)
def veterans_supported_only(name, page_text):
    """Stoll is veterans' supported housing. Propose it only when its own page describes emergency or direct-access beds."""
    blob = (name or "") + " " + (page_text or "")
    if not (re.search(r"\bstoll\b", name or "", re.I) or re.search(r"veterans?'\s+supported", blob, re.I)):
        return False
    return not EMERGENCY_BEDS.search(page_text or "")
def shared_housing_only(name, page_text):
    """Shared houses are supported housing unless that same page describes emergency or direct-access beds."""
    if not re.search(r"shared (?:houses|flats)|semi[- ]independent", name or "", re.I):
        return False
    return not EMERGENCY_BEDS.search(page_text or "")
def publishable_label(name, text, hint=""):
    blob = " ".join(x for x in (name, text, hint) if x)
    if re.search(r"direct access", blob, re.I): return "direct access"
    if re.search(r"night ?shelter|\bswep\b|winter shelter", blob, re.I): return "night shelter"
    if re.search(r"emergency", blob, re.I): return "emergency"
    return "hostel"
def classify(name, text, hint=""):
    """publishable | supported | day_centre | hosted | excluded | unclassified.
    hint is a Street Support subcategory, 'lifehouse', or 'hostel' for the NIHE list."""
    blob = " ".join(x for x in (name, text, hint) if x)
    if is_refuge(name, text) or is_refuge("", hint): return "excluded"
    if re.search(r"\bnightstop\b", blob, re.I): return "hosted"
    sub = (hint or "").lower().strip()
    longer = bool(re.search(r"longer[- ]term|long[- ]term|move[- ]on", blob, re.I))
    if sub == "lifehouse":
        if is_refuge(name, text): return "excluded"
        if DAY.search(blob) and not PUBLISHABLE.search(blob): return "day_centre"
        if longer: return "supported"
        if re.search(r"employment service", blob, re.I) and not PUBLISHABLE.search(blob): return "unclassified"
        return "publishable"
    if sub in SS_OVERNIGHT: kind = "publishable"
    elif sub in ("dropin", "drop-in"): kind = "day_centre"
    elif sub in SS_SUPPORTED: kind = "supported"
    elif sub == "hosted": kind = "hosted"
    else: kind = ""
    if DAY.search(blob) and not PUBLISHABLE.search(blob): return "day_centre"
    if re.search(r"\bemmaus\b", blob, re.I): return "supported"
    overnight = bool(PUBLISHABLE.search(blob)) or kind == "publishable"
    if overnight and not longer: return "publishable"
    if SUPPORTED.search(blob) or kind == "supported": return "supported"
    if kind == "hosted": return "hosted"
    if kind == "day_centre": return "day_centre"
    return "unclassified"

def _windows(text):
    """`wide` is the address sentence before the postcode. `tight` is only the words against the
    postcode, so a footer postcode is not excused by a building address further up the page, and the
    next card on a list page is not read as this building."""
    raw = text or ""
    out = []
    for m in PC_RE.finditer(raw.upper()):
        pc = m.group(1) + m.group(2)
        wide = raw[max(0, m.start() - 180): min(len(raw), m.end() + 40)]
        tight = raw[max(0, m.start() - 70): min(len(raw), m.end() + 40)]
        out.append((pc, wide, tight, m.start()))
    return out
SKIP_WIN = re.compile(r"privacy|cookie notice|sitemap|registered office|company limited|recruitment event|mailing preferences", re.I)
STREET = re.compile(r"\d+(?:-\d+)?\s+(?:st\.?\s+)?[\w'.-]+\s+(?:street|st|road|rd|lane|avenue|ave|drive|close|way|terrace|place|court|gardens)\b", re.I)
def _host_brand(url):
    return re.sub(r"[^a-z0-9]", "", discover.host(url or "").split(".")[0])
def ties_place(window, url, name):
    """The postcode's own sentence names this place, not only the charity that runs several sites."""
    words = set(re.findall(r"[a-z0-9]+", (window or "").lower()))
    d = distinctive(name)
    if not d or not (d & words): return False
    brand = {w for w in d if w and w in _host_brand(url)}
    specific = {w for w in d - brand if len(w) >= 4}
    long = {w for w in specific if len(w) >= 5}
    # two or more place-specific words: the postcode sentence must carry all of them,
    # so a charity footer that only says the brand is not this building
    if len(long) >= 2:
        return long <= words
    if specific and not (specific & words): return False
    path = urllib.parse.urlparse(url or "").path.lower()
    if not specific and not any(w in path for w in d if len(w) >= 4):
        # the domain is the only name we share: a site-wide 'call us' footer is not this building
        if re.search(r"call us on", window or "", re.I): return False
    return True
def building_postcodes(text):
    """Postcodes that read as a building. Footer words are judged on the tight window only."""
    found = []
    for pc, wide, tight, at in _windows(text):
        if not WHERE.search(tight) and (SKIP_WIN.search(tight) or FOOTER.search(tight) or re.search(r"get in touch", tight, re.I)):
            continue
        if re.search(r"\boffice\b", tight, re.I) and not re.search(r"\bhostel\b", tight, re.I):
            continue
        if re.search(r"registered address", tight, re.I) and not re.search(r"\bhostel\b", tight, re.I):
            continue
        if re.search(r"payroll|general enquir|human resources", tight, re.I) and not re.search(r"\bhostel\b", tight, re.I):
            continue
        if REFERRAL_CTX.search(tight) and not WHERE.search(tight) and not STREET.search(tight):
            continue
        found.append((pc, at, wide, tight))
    return found
def best_building(text, name, url=""):
    """The one postcode tied to this place. Several unnamed postcodes on one page are not a pin.
    A search title that names the place does not make the only other postcode on the page the building.
    Returns (postcode, offset, wide_window) or None."""
    cands = building_postcodes(text)
    if not cands: return None
    # tie on the words touching the postcode, so a later footer postcode cannot borrow the building's name
    named = [c for c in cands if ties_place(c[3], url, name)]
    if len(cands) == 1 and not named:
        parts = urllib.parse.urlparse(url or "")
        blob = ((parts.path or "") + " " + (parts.netloc or "")).lower()
        long = {w for w in distinctive(name) if len(w) >= 5}
        short = {w for w in distinctive(name) if len(w) >= 4}
        # every specific word of the name has to be in this place's own URL, and the postcode
        # has to sit on a street. A search title, or a charity homepage used for a different site, does not.
        url_names = all(w in blob for w in long) if long else bool(short) and any(w in blob for w in short)
        tight = cands[0][3]
        if url_names and (WHERE.search(tight) or STREET.search(tight)) and not SKIP_WIN.search(tight):
            named = [cands[0]]
    if len(named) > 1:
        hostelish = [c for c in named if re.search(r"\bhostel\b|\bnight shelter\b", c[3], re.I)]
        streeted = [c for c in named if STREET.search(c[3]) or WHERE.search(c[3])]
        if len(hostelish) == 1: named = hostelish
        elif len(streeted) == 1: named = streeted
        else: named = []
    if len(named) != 1: return None
    pc, at, wide, tight = named[0]
    return pc, at, wide
def _uk_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("44"): digits = "0" + digits[2:]
    if digits.startswith("0") and len(digits) in (10, 11):
        return re.sub(r"\s+", " ", raw).strip()
    return ""
def phone_near(text, postcode):
    """The UK number closest to the building postcode, not a headquarters number further up the page."""
    if not text or not postcode: return ""
    n = norm_pc(postcode)
    best, best_d = "", 10 ** 9
    for m in PC_RE.finditer(text.upper()):
        if norm_pc(m.group(1) + m.group(2)) != n: continue
        start, end = max(0, m.start() - 400), min(len(text), m.end() + 80)
        window = text[start:end]
        for p in PHONE_RE.findall(window):
            shown = _uk_phone(p)
            if not shown: continue
            i = window.find(p)
            local = window[max(0, i - 50): i + len(p) + 50]
            if HQ_PHONE.search(local): continue
            dist = abs((start + i) - m.start())
            if dist < best_d:
                best_d, best = dist, shown
        break
    return best
def locate_near(text, postcode):
    if not text or not postcode: return None
    n = norm_pc(postcode)
    for m in PC_RE.finditer(text.upper()):
        if norm_pc(m.group(1) + m.group(2)) != n: continue
        window = text[max(0, m.start() - 300): m.end() + 300]
        hit = LOCATE.search(window)
        if hit:
            lat, lng = float(hit.group(1)), float(hit.group(2))
            if 49 <= lat <= 61 and -9 <= lng <= 2: return lat, lng
    return None
def address_line(text, postcode):
    if not text or not postcode: return ""
    shown = postcode if " " in postcode else postcode
    flex = r"\s*".join(re.escape(norm_pc(postcode)))
    m = re.search(r"Where we are\s+(.{5,220}?" + flex + r")", text, re.I)
    if m: return re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
    for pc, wide, tight, _ in _windows(text):
        if norm_pc(pc) == norm_pc(postcode) and not FOOTER.search(tight):
            return re.sub(r"\s+", " ", wide).strip(" ,.")[:180]
    return shown

def strip_council(rec):
    for k in list(rec):
        if k in COUNCIL_KEYS or k.startswith("council_"): rec.pop(k, None)
    return rec

# ---------- parsers (fixtures are the contract) ----------
def parse_hl_cards(page_html):
    out = []
    seen = set()
    for m in re.finditer(r'(?is)<a\s+[^>]*href="(?:https://homeless\.org\.uk)?/?service/([a-z0-9-]+)/?"[^>]*>(.*?)</a>', page_html or ""):
        slug, body = m.group(1), m.group(2)
        if slug in seen: continue
        seen.add(slug)
        title = re.search(r'(?is)card__title[^>]*>(.*?)</', body)
        blurb = re.search(r'(?is)card__blurb[^>]*>(.*?)</div>', body)
        name = _text(title.group(1) if title else "") or slug.replace("-", " ").title()
        out.append({"slug": slug, "name": name, "blurb": _text(blurb.group(1) if blurb else "")})
    return out
def hl_page_count(page_html):
    m = re.search(r"Page\s+\d+\s+of\s+(\d+)", page_html or "")
    return int(m.group(1)) if m else 0
def _heading_blocks(page_html):
    cleaned = re.sub(r"(?is)<svg\b.*?</svg>", " ", page_html or "")
    blocks = []
    for m in re.finditer(r"(?is)<h([1-4])[^>]*>(.*?)</h\1>(.*?)(?=<h[1-4]\b|$)", cleaned):
        blocks.append((_text(m.group(2)), _text(m.group(3))[:2500]))
    return blocks
def parse_hl_service(page_html, slug):
    blocks = _heading_blocks(page_html)
    fields = {}
    name = ""
    for title, body in blocks:
        key = title.lower().strip(" ?")
        if title and not name and key not in ("phone", "email", "website", "share", "contact", "info", "connect"):
            if "who is" not in key: name = title
        if key: fields[key] = body
    def take(*keys):
        for k in keys:
            if fields.get(k): return fields[k]
        return ""
    referral_address = take("referral address")
    pcs = [a + " " + b for a, b in PC_RE.findall(referral_address.upper())]
    web = take("website")
    wm = re.search(r"https?://[^\s<>]+", web)
    text = " ".join(body for _, body in blocks)
    return {"id": "hl-" + slug, "slug": slug, "name": name or slug.replace("-", " ").title(),
            "phone_directory": take("phone"), "email": take("email"),
            "website": (wm.group(0).rstrip(".,)") if wm else ""),
            "referral_address": referral_address, "referral_postcode": pcs[0] if pcs else "",
            "referral_procedure": take("referral procedure", "referral agencies", "how to get a referral"),
            "support": take("support offered", "units", "who do we help?"),
            "directory_text": text, "directory": "Homeless Link",
            "directory_url": HL_SEARCH + "service/" + slug + "/"}

def parse_ss_record(rec):
    if not isinstance(rec, dict): return None
    addr = rec.get("Address") if isinstance(rec.get("Address"), dict) else {}
    parts = [addr.get(k) or "" for k in ("Street1", "Street2", "Street3", "City", "Postcode")]
    referral_address = ", ".join(p.strip() for p in parts if p and str(p).strip())
    pc = (addr.get("Postcode") or "").upper().strip()
    blob = " ".join(str(rec.get(k) or "") for k in ("name", "description", "ServiceProviderName"))
    urls = [u.rstrip(").,]") for u in re.findall(r"https?://[^\s\"'\\<>]+", json.dumps(rec))]
    web = next((u for u in urls if discover.usable_site(u) and "streetsupport.net" not in u), "")
    sub = (rec.get("SubCategoryKey") or "").lower()
    parent = (rec.get("ParentCategoryKey") or "").lower()
    return {"id": "ss-" + str(rec.get("_id") or rec.get("ServiceProviderKey") or ""),
            "name": (rec.get("name") or rec.get("ServiceProviderName") or "").strip(),
            "referral_address": referral_address, "referral_postcode": pc if split_pc(pc) else "",
            "website": web, "directory_text": blob, "hint": sub if parent == "accom" else ("dropin" if parent == "dropin" else sub),
            "parent": parent, "sub": sub, "directory": "Street Support",
            "directory_url": "https://www.streetsupport.net/find-help"}

def lifehouse_place_urls(sitemap_xml):
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap_xml or "")
    out = []
    for u in urls:
        path = urllib.parse.urlparse(u).path.strip("/")
        if not path or "/" in path or "lifehouse" not in path.lower(): continue
        if path.startswith("news"): continue
        out.append(u.split("?")[0].rstrip("/"))
    return out
def parse_lifehouse_page(page_html, url):
    text = _text(page_html)
    title = ""
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", page_html or "")
    if m: title = _text(m.group(1))
    if not title:
        m = re.search(r"([A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,6}\s+Lifehouse)", text)
        title = m.group(1) if m else urllib.parse.urlparse(url).path.strip("/").replace("-", " ").title()
    return {"id": "sa-" + urllib.parse.urlparse(url).path.strip("/").strip("-")[:80],
            "name": title, "website": url, "operator_pages": [(url, text)],
            "directory_text": text, "hint": "lifehouse", "directory": "Salvation Army Lifehouses",
            "directory_url": url, "referral_address": "", "referral_postcode": ""}
def stated_lifehouse_count(page_html):
    m = re.search(r"operates\s+(\d+)\s+supported accommodation", _text(page_html), re.I)
    return int(m.group(1)) if m else None

NIHE_CLIENTS = (
    "women at risk of domestic abuse",
    "single women's homeless crisis accommodation service",
    "single womens homeless crisis accommodation service",
    "single homeless crisis accommodation service",
    "single people with support needs",
    "people with alcohol addiction issues",
    "men with alcohol addiction issues",
)
def parse_nihe_text(text):
    """Rows of: Service, client group, town, phone. Women's refuges are excluded, with no address or phone kept."""
    rows, excluded = [], []
    for raw in (text or "").splitlines():
        if not raw.strip() or raw.lower().startswith(("service ", "self-referral", "*self-referral", "table ")): continue
        phone, body = "", raw
        pm = PHONE_RE.search(raw)
        if pm:
            phone = re.sub(r"\s+", " ", pm.group(0)).strip()
            body = raw[:pm.start()] + " " + raw[pm.end():]
        line = re.sub(r"\s+", " ", body).strip(" |")
        if len(line) < 6: continue
        low = line.lower()
        client = next((c for c in NIHE_CLIENTS if c in low), "")
        if client:
            i = low.find(client)
            name, town = line[:i].strip(" -|"), line[i + len(client):].strip(" -|")
        else:
            bits = [b.strip() for b in re.split(r"\s{2,}|\s\|\s", body) if b.strip()]
            if len(bits) < 2: continue
            name, client, town = bits[0], " ".join(bits[1:-1]) if len(bits) >= 3 else bits[1], bits[-1] if len(bits) >= 3 else ""
        if len(name) < 3 or name.lower() in ("service", "location"): continue
        if is_refuge(name, client):
            excluded.append({"name": name, "reason": "women's refuge or domestic abuse service — never mapped"})
            continue
        rows.append({"name": name, "client": client, "town": town, "phone_official": phone,
                     "text": name + " " + client + " " + town})
    return rows, excluded

def pdf_to_text(data):
    if not data or not data.startswith(b"%PDF"): return ""
    try:
        import pypdf
        from io import BytesIO
        reader = pypdf.PdfReader(BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception: pass
    try:
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data); f.flush()
            r = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, timeout=30)
            if r.returncode == 0: return r.stdout.decode("utf-8", "ignore")
    except Exception: pass
    return ""

# ---------- fetching ----------
def _cache_path(cache_dir, url):
    return os.path.join(cache_dir, hashlib.sha256(url.encode()).hexdigest() + ".json")
def polite(fetcher, delay=0.0, cache_dir=None, ttl=20 * 3600):
    """One request at a time per host, with an optional disk cache. Tests pass delay 0 and no cache."""
    last, lock = {}, threading.Lock()
    def f(url):
        if cache_dir:
            p = _cache_path(cache_dir, url)
            try:
                if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
                    return json.load(open(p))
            except Exception: pass
        host = urllib.parse.urlparse(url).netloc
        if delay:
            with lock:
                wait = delay - (time.time() - last.get(host, 0))
                if wait > 0: time.sleep(wait)
                last[host] = time.time()
        res = fetcher(url)
        if cache_dir and isinstance(res, dict) and res.get("http") == 200 and res.get("html"):
            try:
                os.makedirs(cache_dir, exist_ok=True)
                json.dump({k: res.get(k) for k in ("http", "final_url", "html", "etag", "last_modified", "sha256")},
                          open(_cache_path(cache_dir, url), "w"), ensure_ascii=False)
            except Exception: pass
        return res
    return f
def _ok(res): return isinstance(res, dict) and res.get("http") == 200 and res.get("html")

def sitemap_follow(website, name, fetcher, already=(), home_html="", max_pages=4):
    """Place pages linked from the operator sitemap or homepage, for a multi-site operator whose
    homepage does not name this building. Returns [(url, text)] not already fetched."""
    if not discover.usable_site(website): return []
    have = {u for u, _ in already}
    home = None
    for u, _ in already:
        if discover.host(u) == discover.host(website):
            home = u; break
    if home is None:
        res = fetcher(website)
        if not _ok(res): return []
        home = res.get("final_url") or website
        have.add(home)
        if not home_html: home_html = res.get("html") or ""
    base = home
    locs, pages = [], []
    sm = fetcher(urllib.parse.urljoin(base, "/sitemap.xml"))
    if _ok(sm):
        found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm["html"])
        nested = [u for u in found if u.rstrip("/").endswith(".xml")][:3]
        locs = [u for u in found if not u.rstrip("/").endswith(".xml")]
        for u in nested:
            sub = fetcher(u)
            if _ok(sub): locs += [x for x in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub["html"]) if not x.rstrip("/").endswith(".xml")]
    d = distinctive(name)
    ranked = []
    for u in locs:
        if discover.host(u) != discover.host(base): continue
        path = urllib.parse.urlparse(u).path.lower()
        if any(x in path for x in ("/news", "/tag/", "/category/", "/author/")): continue
        score = sum(1 for w in d if w in path)
        if score: ranked.append((score, u))
    ranked.sort(key=lambda x: -x[0])
    # homepage anchors whose text or href names the place
    if home_html:
        for href, label in re.findall(r'(?is)<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', home_html):
            blob = (href + " " + _text(label)).lower()
            if d and any(w in blob for w in d):
                u = urllib.parse.urljoin(base, href)
                if discover.host(u) == discover.host(base): ranked.append((2, u))
    out, seen = [], set()
    for _, u in ranked:
        if u in have or u in seen: continue
        seen.add(u)
        if len(out) >= max_pages: break
        res = fetcher(u)
        if _ok(res): out.append((res.get("final_url") or u, _text(res["html"])))
    return out

def _place_url(url):
    """A page that can confirm a building or an area card. Search, news, blogs and directory hosts cannot."""
    if not url: return False
    host = discover.host(url)
    if host in ("homeless.org.uk", "www.homeless.org.uk", "streetsupport.net", "www.streetsupport.net"):
        return False
    parts = urllib.parse.urlparse(url)
    path = (parts.path or "").lower()
    query = (parts.query or "").lower()
    if re.search(r"(?:^|&)(?:s|q|keys|highlight)=", query): return False
    if re.search(r"/(?:blog|news|press-release|press|tag|category|author|search|careers|jobs|vacancies|post)(?:/|$)", path):
        return False
    if path.endswith(".xml") or "/sitemap" in path: return False
    if re.search(r"/page/\d+(?:/|$)|/\d{4}/\d{2}/|mourn|obituar", path): return False
    if re.search(r"cemetery|crematorium|register-office|registration-office|births-deaths|civil-partnership", path):
        return False
    slug = path.strip("/").split("/")[-1] if path.strip("/") else ""
    council = host == "gov.uk" or host.endswith(".gov.uk")
    if not council and slug.count("-") >= 4: return False
    return True
def confirm_operator(candidate, fetcher):
    """Building postcode from the place's own page or an official operator page. Directory postcodes are ignored."""
    pages = list(candidate.get("operator_pages") or [])
    website = candidate.get("website") or ""
    if website and discover.usable_site(website):
        res = None
        if not pages:
            res = fetcher(website)
            if _ok(res): pages.append((res.get("final_url") or website, _text(res["html"])))
            elif not pages:
                return {"ok": False, "reason": "operator site unreachable (HTTP %s)" % (res.get("http") if isinstance(res, dict) else "?")}
        if pages and not best_building(pages[-1][1], candidate.get("name"), pages[-1][0]):
            pages += sitemap_follow(website, candidate.get("name"), fetcher, pages, (res or {}).get("html") or "")
        elif not pages:
            return {"ok": False, "reason": "operator site unreachable (HTTP %s)" % (res.get("http") if isinstance(res, dict) else "?")}
    official = []
    for url, text in pages:
        if not _place_url(url): continue
        host = discover.host(url)
        if (host == "gov.uk" or host.endswith(".gov.uk")) and not re.search(
                r"hostel|homeless|night shelter|emergency accommodation", (url or "") + " " + (text or ""), re.I):
            continue
        if not names_place(text, candidate.get("name")): continue
        hit = best_building(text, candidate.get("name"), url)
        if not hit: continue
        official.append((url, text, hit))
    if not official:
        if not website and not pages:
            return {"ok": False, "reason": "no operator page to confirm a building address"}
        return {"ok": False, "reason": "no building postcode on the operator page (directory postcode is a referral address only)"}
    # the page whose URL names the place beats a homepage that lists several buildings
    official.sort(key=lambda row: -sum(1 for w in distinctive(candidate.get("name")) if w in urllib.parse.urlparse(row[0]).path.lower()))
    url, text, (pc, at, window) = official[0]
    shown = pc
    # prefer the spaced form if the page shows one
    m = re.search(r"\b" + re.escape(pc[:-3]) + r"\s*" + re.escape(pc[-3:]) + r"\b", text.upper())
    if m: shown = re.sub(r"\s+", " ", m.group(0)).strip()
    if len(norm_pc(shown)) >= 5 and " " not in shown:
        shown = shown[:-3] + " " + shown[-3:]
    latlng = locate_near(text, shown)
    phone = phone_near(text, shown)
    route = access_route(text) or access_route(candidate.get("directory_text") or "")
    return {"ok": True, "url": url, "postcode": shown.upper(), "address": address_line(text, shown),
            "lat": latlng[0] if latlng else None, "lng": latlng[1] if latlng else None,
            "phone": phone, "phone_source": url if phone else "", "access": route, "text": text}

def assess(candidate, fetcher, today, existing):
    """One candidate → proposal, held, day centre, excluded, or already listed. Never a pin from a directory postcode."""
    name = candidate.get("name") or ""
    directory_text = candidate.get("directory_text") or ""
    kind = classify(name, directory_text, candidate.get("hint") or "")
    base = {"id": candidate.get("id"), "name": name, "directory": candidate.get("directory"),
            "directory_url": candidate.get("directory_url") or "", "website": candidate.get("website") or "",
            "referral_address": candidate.get("referral_address") or "",
            "referral_postcode": candidate.get("referral_postcode") or "",
            "category": kind}
    if candidate.get("town"): base["town"] = candidate["town"]
    if kind == "excluded" or is_refuge(name, directory_text):
        return "excluded", {"id": base["id"], "name": name, "reason": "women's refuge or domestic abuse service — never mapped"}
    pcs = [base["referral_postcode"]]
    for e in existing:
        if e.get("id") and e["id"] == base["id"]:
            return "already", None
        if same_place(name, pcs, e.get("name"), e.get("postcode")):
            return "already", None
    if kind == "day_centre":
        return "day_centre", dict(base, status="held", reason="day centre / drop-in — held candidate, not a shelter")
    if kind == "supported":
        return "held", dict(base, status="held", reason="longer-term supported housing or Emmaus — not published")
    if kind == "hosted":
        return "held", dict(base, status="held", reason="hosted accommodation (no fixed shelter building)")
    if kind != "publishable":
        return "held", dict(base, status="held", reason="not clearly an emergency, direct-access, night shelter or hostel")
    if shared_housing_only(name, directory_text):
        return "held", dict(base, status="held", category="supported",
                            reason="longer-term supported housing or Emmaus — not published")
    if not candidate.get("operator_pages"):
        season = seasonal_reason(name, directory_text)
        if season:
            return "held", dict(base, status="held", reason=season)
    op = confirm_operator(candidate, fetcher)
    if not op.get("ok"):
        held_rec = dict(base, status="held", reason=op.get("reason") or "not confirmed")
        # NIHE (and only that official list) may name a phone with no building. It stays on the held
        # record for review; it is not published and is not written to the phone baseline here.
        if candidate.get("phone_official") and candidate.get("directory_url"):
            held_rec["phone"] = candidate["phone_official"]
            held_rec["phone_source"] = candidate["directory_url"]
        return "held", strip_council(held_rec)
    # the confirmed building may show this place is already listed under a neighbouring postcode
    for e in existing:
        if same_place(name, [op["postcode"], base["referral_postcode"]], e.get("name"), e.get("postcode")):
            return "already", None
    route = op.get("access") or ""
    page_text = op.get("text") or ""
    if seasonal_reason(name, directory_text + " " + page_text):
        return "held", dict(base, status="held", reason=seasonal_reason(name, directory_text + " " + page_text), operator_page=op.get("url"))
    if is_refuge(name, page_text):
        return "excluded", {"id": base["id"], "name": name, "reason": "women's refuge or domestic abuse service — never mapped"}
    if veterans_supported_only(name, page_text) or shared_housing_only(name, page_text):
        return "held", dict(base, status="held", reason="longer-term supported housing or Emmaus — not published",
                            operator_page=op.get("url"), category="supported")
    if classify(name, page_text, candidate.get("hint") or "") == "supported" and not PUBLISHABLE.search(page_text):
        return "held", dict(base, status="held", reason="operator page describes longer-term supported housing", operator_page=op.get("url"))
    if not route and not has_times(page_text) and not has_times(directory_text):
        return "held", dict(base, status="held", reason="no opening times or access route on the operator or directory page",
                            operator_page=op.get("url"), postcode=op["postcode"], address=op.get("address") or "")
    at = access_type_of(route)
    rec = dict(base, status="verified", layer="shelters",
               category=publishable_label(name, (page_text + " " + directory_text), candidate.get("hint") or ""),
               address=op.get("address") or "", postcode=op["postcode"], lat=op.get("lat"), lng=op.get("lng"),
               phone=op.get("phone") or "", phone_source=op.get("phone_source") or "",
               access=route, access_type=at or "",
               operator_page=op.get("url") or "",
               evidence=("official directory entry + council page names the hostel and its address"
                         if (discover.host(op.get("url")) == "gov.uk" or discover.host(op.get("url") or "").endswith(".gov.uk"))
                         else "official directory entry + operator page names the place and shows the building postcode"))
    # directory postcode must not be reused as the building when the page showed a different one
    if rec.get("referral_postcode") and norm_pc(rec["postcode"]) == norm_pc(rec["referral_postcode"]):
        rec["postcode_note"] = "building postcode confirmed on the operator page; it matches the directory postcode"
    elif rec.get("referral_postcode"):
        rec["postcode_note"] = "building postcode is from the operator page; the directory postcode is only the referral address"
    else:
        rec["postcode_note"] = "building postcode is from the operator page; the directory listing had no postcode"
    if not rec["phone"]:
        rec.pop("phone", None); rec.pop("phone_source", None)
    return "verified", strip_council(rec)

# ---------- readers ----------
def read_homeless_link(fetcher, max_pages=None, service_limit=None, index=None):
    """Page every accommodation results page, then each service page. Fail safe: empty + a reason."""
    first = fetcher(HL_SEARCH + "?" + urllib.parse.urlencode({"service_types": "accommodation", "page": 1}))
    if not _ok(first):
        return [], {"status": "failed: HTTP %s" % (first.get("http") if isinstance(first, dict) else "?"), "found": 0}
    total = hl_page_count(first["html"]) or 1
    if max_pages: total = min(total, max_pages)
    cards = {c["slug"]: c for c in parse_hl_cards(first["html"])}
    pages_read, stopped = 1, ""
    for p in range(2, total + 1):
        res = fetcher(HL_SEARCH + "?" + urllib.parse.urlencode({"service_types": "accommodation", "page": p}))
        if not _ok(res):
            stopped = "stopped: HTTP %s on page %s" % (res.get("http") if isinstance(res, dict) else "?", p)
            break
        got = parse_hl_cards(res["html"])
        if not got: break
        pages_read = p
        for c in got: cards.setdefault(c["slug"], c)
        if os.environ.get("SHELTER_SOURCE_PROGRESS") and p % 10 == 0:
            print("homeless link page", p, "of", total, "listings", len(cards), flush=True)
    slugs = sorted(cards)
    if service_limit is not None: slugs = slugs[:service_limit]
    cached = (index or {}).get("hl_services") or {}
    out, failed = [], 0
    for slug in slugs:
        if slug in cached and cached[slug].get("name"):
            rec = dict(cached[slug]); rec["blurb"] = cards[slug].get("blurb") or ""
            out.append(rec); continue
        res = fetcher(HL_SEARCH + "service/" + slug + "/")
        if not _ok(res):
            failed += 1
            card = cards[slug]
            out.append({"id": "hl-" + slug, "slug": slug, "name": card["name"], "website": "",
                        "referral_address": "", "referral_postcode": "", "directory_text": card.get("blurb") or "",
                        "directory": "Homeless Link", "directory_url": HL_SEARCH + "service/" + slug + "/"})
            continue
        rec = parse_hl_service(res["html"], slug)
        if cards[slug].get("blurb"): rec["directory_text"] = (rec.get("directory_text") or "") + " " + cards[slug]["blurb"]
        if not rec.get("name"): rec["name"] = cards[slug]["name"]
        out.append(rec)
        if os.environ.get("SHELTER_SOURCE_PROGRESS") and len(out) % 50 == 0:
            print("homeless link services", len(out), "of", len(slugs), flush=True)
    status = {"status": "ok" if not stopped else stopped, "pages": total, "pages_read": pages_read, "found": len(cards), "services_read": len(out), "service_failures": failed}
    return out, status

def _ss_pages(fetcher, category):
    out, page, total = [], 1, None
    while True:
        res = fetcher(SS_API + "?" + urllib.parse.urlencode({"category": category, "limit": 100, "page": page}))
        if not _ok(res):
            return out, {"status": "failed: HTTP %s" % (res.get("http") if isinstance(res, dict) else "?")}
        try: data = json.loads(res["html"])
        except Exception as e: return out, {"status": "failed: not JSON (%s)" % e}
        if total is None: total = int(data.get("total") or 0)
        rows = data.get("results") or []
        if not rows: break
        out += rows
        if len(out) >= total or page > 50: break
        page += 1
    return out, {"status": "ok", "total": total if total is not None else len(out), "fetched": len(out)}

def read_street_support(fetcher):
    accom, st_a = _ss_pages(fetcher, "accom")
    drops, st_d = _ss_pages(fetcher, "dropin")
    if st_a["status"] != "ok" and st_d["status"] != "ok":
        return [], {"status": st_a["status"], "found": 0}
    recs = []
    for raw in accom:
        rec = parse_ss_record(raw)
        if rec and rec.get("name"): recs.append(rec)
    for raw in drops:
        rec = parse_ss_record(raw)
        if not rec or not rec.get("name"): continue
        rec["hint"] = "dropin"; rec["parent"] = "dropin"; recs.append(rec)
    return recs, {"status": "ok" if st_a["status"] == "ok" else st_a["status"],
                  "accommodation": st_a, "dropin": st_d, "found": len(recs)}

def read_lifehouses(fetcher):
    urls, pages_ok = [], 0
    index_html, stated = "", None
    idx = fetcher(SA_INDEX)
    if _ok(idx):
        index_html = idx["html"]; stated = stated_lifehouse_count(index_html)
    sm = fetcher(SA_SITEMAP)
    if not _ok(sm):
        return [], {"status": "failed: sitemap HTTP %s" % (sm.get("http") if isinstance(sm, dict) else "?"), "found": 0, "stated_on_page": stated}
    nested = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm["html"]) if "sitemap" in u]
    blobs = [sm["html"]]
    for u in nested[:5]:
        sub = fetcher(u)
        if _ok(sub): blobs.append(sub["html"]); pages_ok += 1
    for blob in blobs: urls += lifehouse_place_urls(blob)
    urls = sorted(set(urls))
    out, failed = [], 0
    for u in urls:
        res = fetcher(u if u.startswith("http") else "https://www.salvationarmy.org.uk/" + u)
        if not _ok(res):
            failed += 1; continue
        out.append(parse_lifehouse_page(res["html"], res.get("final_url") or u))
    status = {"status": "ok", "found": len(out), "sitemap_place_pages": len(urls), "page_fetch_failures": failed, "stated_on_page": stated}
    if stated and stated != len(out):
        status["note"] = "Lifehouses page says %s services; sitemap exposed %s place pages (news URLs excluded)" % (stated, len(out))
    return out, status

def _pdf_bytes(url):
    import urllib.request
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)
        return r.status, r.read(8_000_000)
    except Exception as e:
        return getattr(e, "code", "error"), b""
def read_nihe(fetcher):
    """Official list. nihe.gov.uk often returns 403; the Housing Rights copy of the June 2025 NIHE list is the fallback.
    Women's refuges are excluded and not given addresses or phones."""
    page = fetcher(NIHE_PAGE)
    text, source = "", ""
    if _ok(page):
        plain = _text(page["html"])
        if "self-referral" in plain.lower() or "women at risk of domestic abuse" in plain.lower():
            text, source = plain, page.get("final_url") or NIHE_PAGE
    if not text:
        pdf = fetcher(NIHE_PDF)
        html_s = pdf.get("html") if isinstance(pdf, dict) else ""
        if isinstance(html_s, str) and not html_s.startswith("%PDF") and ("single people" in html_s.lower() or "women at risk" in html_s.lower()):
            text, source = html_s, NIHE_PDF
        else:
            code, data = _pdf_bytes(NIHE_PDF)
            text = pdf_to_text(data) if code == 200 else ""
            source = NIHE_PDF
            if not text:
                nihe_http = page.get("http") if isinstance(page, dict) else "?"
                pdf_http = pdf.get("http") if isinstance(pdf, dict) else code
                return [], [], {"status": "failed: NIHE page HTTP %s; Housing Rights PDF HTTP %s" % (nihe_http, pdf_http), "found": 0}
    rows, excluded = parse_nihe_text(text)
    out = []
    for r in rows:
        out.append({"id": "nihe-" + re.sub(r"[^a-z0-9]+", "-", r["name"].lower()).strip("-")[:70],
                    "name": r["name"], "website": "", "referral_address": "", "referral_postcode": "",
                    "town": r.get("town") or "", "directory_text": r["text"], "hint": "hostel",
                    "directory": "NIHE self-referral hostels", "directory_url": source,
                    "phone_official": r.get("phone_official") or "", "client": r.get("client") or ""})
    note = ""
    if source == NIHE_PDF:
        note = ("nihe.gov.uk did not return the hostel list; used the Housing Rights copy of the NIHE "
                "self-referral list (June 2025). That public list is the self-referral subset, not a full hostel inventory.")
    return out, excluded, {"status": "ok", "found": len(rows) + len(excluded), "kept": len(rows),
                           "refuges_excluded": len(excluded), "source": source, "note": note}

def load_existing(root=None):
    root = root or ROOT
    path = os.path.join(root, "shelters.js")
    try:
        t = open(path, encoding="utf-8").read()
        t = t[t.index("=") + 1:].strip().rstrip(";")
        items = json.loads(t).get("items") or []
    except Exception:
        items = []
    return [{"id": i.get("id"), "name": i.get("name"), "postcode": i.get("postcode")} for i in items if i.get("id")]

def build_report(groups, existing, fetcher, today, evidence_limit=None):
    """groups: list of (source_key, candidates, status, extra_excluded)."""
    by, proposals, held, day, excluded, already = {}, [], [], [], [], {}
    checked = 0
    for key, cands, status, extra_ex in groups:
        excluded += extra_ex or []
        counts = {"found": status.get("found", len(cands)) if isinstance(status, dict) else len(cands),
                  "verified": 0, "held": 0, "excluded": len(extra_ex or []), "already_listed": 0, "day_centre_candidates": 0}
        if isinstance(status, dict): counts["reader"] = {k: v for k, v in status.items() if k != "found"}
        for c in cands:
            kind = classify(c.get("name"), c.get("directory_text"), c.get("hint") or "")
            # refuges and non-publishable categories do not need an operator fetch
            needs_op = kind == "publishable"
            if needs_op and evidence_limit is not None and checked >= evidence_limit:
                held.append(strip_council({"id": c.get("id"), "name": c.get("name"), "directory": c.get("directory"),
                                            "directory_url": c.get("directory_url"), "status": "held", "category": kind,
                                            "referral_postcode": c.get("referral_postcode") or "",
                                            "reason": "not evidence-checked this run (limit)"}))
                counts["held"] += 1
                continue
            if needs_op: checked += 1
            if os.environ.get("SHELTER_SOURCE_PROGRESS") and needs_op and checked % 25 == 0:
                print("evidence", checked, c.get("name"), flush=True)
            bucket, rec = assess(c, fetcher, today, existing)
            if bucket == "verified" and rec:
                proposals.append(rec); counts["verified"] += 1
                existing.append({"id": rec["id"], "name": rec["name"], "postcode": rec["postcode"]})
            elif bucket == "held" and rec:
                held.append(strip_council(rec)); counts["held"] += 1
            elif bucket == "day_centre" and rec:
                day.append(strip_council(rec)); counts["day_centre_candidates"] += 1
            elif bucket == "excluded" and rec:
                excluded.append(rec); counts["excluded"] += 1
            elif bucket == "already":
                counts["already_listed"] += 1
                already[c.get("id") or c.get("name")] = c.get("name")
        by[key] = counts
    uncertain = []
    for key, _, status, _ in groups:
        if isinstance(status, dict) and status.get("note"): uncertain.append(status["note"])
        if isinstance(status, dict) and str(status.get("status", "")).startswith("failed"):
            uncertain.append("%s: %s" % (key, status.get("status")))
    doc = {"generated": today, "layer": "shelters",
           "about": "Verified new shelters for review. Not published. A directory postcode is a referral address, never the pin. "
                    "A proposal is only listed when an operator or official page names the place and shows a building postcode, "
                    "with opening times or an access route. Phones are present only when that confirming page showed them; "
                    "applying a proposal means adding the phone to overrides/phone_baseline.json in a reviewed change. "
                    "Council-line fields are not set. Women's refuges are excluded and not mapped. "
                    "Day centres are held candidates (no Day centre map label until that change is on main).",
           "day_centre_label": "held candidates only",
           "counts": {"by_source": by, "verified": len(proposals), "held": len(held),
                      "day_centre_candidates": len(day), "excluded": len(excluded), "already_listed": len(already)},
           "proposals": proposals, "held": held, "day_centre_candidates": day, "excluded": excluded,
           "uncertain": uncertain}
    return doc

def write_report(path, doc):
    """Write shelter proposals. Keep any non-shelter proposals already in the file (shared with other work)."""
    prev = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f: prev = json.load(f)
        except Exception: prev = {}
    if isinstance(prev, dict):
        others = [p for p in (prev.get("proposals") or []) if isinstance(p, dict) and p.get("layer") not in (None, "", "shelters")]
        merged, seen = [], set()
        for p in list(doc.get("proposals") or []) + others:
            if not isinstance(p, dict): continue
            i = p.get("id")
            if i and i in seen: continue
            if i: seen.add(i)
            merged.append(p)
        doc["proposals"] = merged
        for k, v in prev.items():
            if k not in doc: doc[k] = v
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(doc, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return doc

def refresh(root=None, today=None, fetcher=None, delay=0.4, evidence_limit=None, max_hl_pages=None, service_limit=None, write=True):
    root = root or ROOT
    today = today or datetime.date.today().isoformat()
    index_path = os.path.join(root, INDEX) if not os.path.isabs(INDEX) else INDEX
    if root != ROOT: index_path = os.path.join(root, "logs", "shelter_source_index.json")
    index = {}
    try: index = json.load(open(index_path, encoding="utf-8"))
    except Exception: index = {}
    raw = fetcher or discover.fetch_raw
    cache = None if fetcher else os.path.join(root, CACHE)
    fetch = polite(raw, delay=0 if fetcher else delay, cache_dir=cache)
    hl, st_hl = read_homeless_link(fetch, max_pages=max_hl_pages, service_limit=service_limit, index=index if not service_limit else None)
    ss, st_ss = read_street_support(fetch)
    sa, st_sa = read_lifehouses(fetch)
    nihe, nihe_ex, st_ni = read_nihe(fetch)
    # remember HL service fields so the next run does not refetch unchanged pages the same day
    if st_hl.get("status") == "ok" and not service_limit:
        index = {"fetched": today, "hl_services": {c.get("slug") or c["id"][3:]: {k: c.get(k) for k in
                 ("id", "slug", "name", "website", "referral_address", "referral_postcode", "directory_text", "directory", "directory_url", "support", "referral_procedure")}
                 for c in hl if c.get("id")}}
        try:
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            json.dump(index, open(index_path, "w"), ensure_ascii=False)
        except Exception: pass
    existing = load_existing(root)
    doc = build_report([
        ("homeless_link", hl, st_hl, []),
        ("street_support", ss, st_ss, []),
        ("lifehouses", sa, st_sa, []),
        ("nihe", nihe, st_ni, nihe_ex),
    ], existing, fetch, today, evidence_limit=evidence_limit)
    doc["sources"] = {"homeless_link": st_hl, "street_support": st_ss, "lifehouses": st_sa, "nihe": st_ni}
    if write:
        path = os.path.join(root, "reports", "verified_new_places.json")
        write_report(path, doc)
    return {"status": "ok", "verified": len(doc["proposals"]), "held": len(doc["held"]),
            "day_centre_candidates": len(doc["day_centre_candidates"]), "excluded": len(doc["excluded"]),
            "by_source": doc["counts"]["by_source"]}

def search_urls(website, name):
    """Same-site search URLs. A result only counts once a fetched page names the place and a building postcode."""
    if not discover.usable_site(website): return []
    parts = urllib.parse.urlparse(website)
    root = "%s://%s" % (parts.scheme or "https", parts.netloc)
    q = urllib.parse.quote(name or "")
    return [root + "/?s=" + q, root + "/search?q=" + q, root + "/search?keys=" + q]
def _same_site_links(html, base, name, pred):
    out = []
    for href, label in re.findall(r'(?is)<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html or ""):
        blob = href + " " + _text(label)
        if not pred(blob): continue
        u = urllib.parse.urljoin(base, href)
        if discover.host(u) == discover.host(base) and u not in out:
            out.append(u)
    return out
def council_follow(council_url, name, fetcher, cap=6):
    """Homelessness / hostel pages on a council site. A hit still has to name this hostel and a building postcode."""
    res = fetcher(council_url)
    if not _ok(res): return []
    base = res.get("final_url") or council_url
    pages = [(base, _text(res["html"]))]
    d = distinctive(name)
    def pred(blob):
        low = blob.lower()
        if any(w in low for w in d): return True
        return bool(re.search(r"hostel|homeless|night shelter|emergency accommodation", low))
    links = _same_site_links(res["html"], base, name, pred)
    pages += sitemap_follow(base, name, fetcher, pages, res["html"], max_pages=cap)
    for u in links:
        if len(pages) >= cap + 1: break
        if any(u == p[0] for p in pages): continue
        r = fetcher(u)
        if _ok(r): pages.append((r.get("final_url") or u, _text(r["html"])))
    return pages
def operator_second_look(website, name, fetcher, cap=8):
    """Sitemap plus site search, deeper than the first pass."""
    if not discover.usable_site(website): return []
    home = fetcher(website)
    pages = []
    html = ""
    if _ok(home):
        pages.append((home.get("final_url") or website, _text(home["html"])))
        html = home["html"]
    pages += sitemap_follow(website, name, fetcher, pages, html, max_pages=cap)
    for u in search_urls(website, name):
        if any(u == p[0] for p in pages): continue
        r = fetcher(u)
        if not _ok(r): continue
        pages.append((r.get("final_url") or u, _text(r["html"])))
        for link in _same_site_links(r["html"], r.get("final_url") or u, name, lambda b: any(w in b.lower() for w in distinctive(name))):
            if len(pages) >= cap + 4: break
            if any(link == p[0] for p in pages): continue
            rr = fetcher(link)
            if _ok(rr): pages.append((rr.get("final_url") or link, _text(rr["html"])))
    return pages
def norm_area(s):
    s = re.sub(r"\b(city|council|borough|district|county|metropolitan|london|royal|of|the|and)\b", " ", (s or "").lower())
    return re.sub(r"[^a-z]+", " ", s).strip()
def load_council_homes(root=None):
    """Council name -> homelessness page, from the SWEP source list. Used only to find a page to read."""
    root = root or ROOT
    out = {}
    try:
        rows = json.load(open(os.path.join(root, "overrides", "swep_sources.json"), encoding="utf-8"))
    except Exception:
        return out
    for row in rows:
        url = row.get("homeless_url") or ""
        if not url or not (discover.host(url).endswith(".gov.uk") or discover.host(url) == "gov.uk"): continue
        name = re.sub(r"\s*\(news\)\s*$", "", row.get("council") or "", flags=re.I).strip()
        if name and norm_area(name) not in out:
            out[norm_area(name)] = url
    return out
def council_url_for(district, homes):
    key = norm_area(district)
    if not key: return ""
    if key in homes: return homes[key]
    for name, url in homes.items():
        if key in name or name in key: return url
    return ""
ROUTE_BIT = re.compile(r"housing options|streetlink|referral (?:only|needed|via|through)|referred by|via (?:the )?(?:council|outreach)|outreach team", re.I)
WITHHELD = re.compile(r"address is not (?:public|published|disclosed)|no public address|do not (?:publish|share) the address|do not turn up|referral only|housing options|streetlink", re.I)
def _route_sentence(text):
    m = ROUTE_BIT.search(text or "")
    if not m: return ""
    return _snip(text, m)
_TOWN_STOP = {"housing", "council", "local", "the", "referral", "street", "options", "city", "borough", "hostel", "england", "wales", "scotland", "northern", "ireland"}
def _operator_from(text, url):
    m = re.search(r"(?:run by|operated by|provided by|managed by)\s+([^.]{3,80})", text or "", re.I)
    if not m: return ""
    op = re.split(r"\s+in\s+", m.group(1), maxsplit=1)[0]
    op = re.sub(r"\s+", " ", op).strip(" ,")
    if op.lower() in ("the council", "council", "housing options", "streetlink"): return ""
    return op
def _name_window(text, name, pad=700):
    """Words around the place name, so a footer phone or a housing-options line further down the page does not count."""
    raw = text or ""
    low = raw.lower()
    words = [w for w in distinctive(name) if len(w) >= 4] or list(discover.tokens(name))
    idxs = [low.find(w) for w in words if w and low.find(w) >= 0]
    if not idxs: return ""
    i = min(idxs)
    return raw[max(0, i - pad): i + pad]
def _phone_on_page(text):
    best = ""
    for p in PHONE_RE.findall(text or ""):
        shown = _uk_phone(p)
        if not shown: continue
        i = (text or "").find(p)
        local = (text or "")[max(0, i - 40): i + len(p) + 40]
        if HQ_PHONE.search(local): continue
        best = shown
        break
    return best
CARD_ROUTE = re.compile(r"housing options|streetlink|(?<!\bno\s)referral(?:s)? (?:only|needed|required|via|through|from)|(?<!\bno\s)by referral|referred by|must be referred|(?<![\w-])self[- ]referr|(?<![\d-])direct access|(?<![\w-])walk[- ]in|referrals? from", re.I)
_OP_BAD = re.compile(r"cookie|skip to|menu|search|newsletter|privacy|preferences|donate", re.I)
def _url_names(url, name):
    path = urllib.parse.urlparse(url or "").path.lower()
    return any(w in path for w in distinctive(name) if len(w) >= 5)
def _name_positions(text, name):
    low = (text or "").lower()
    out = []
    for w in distinctive(name):
        if len(w) < 4: continue
        start = 0
        while len(out) < 24:
            j = low.find(w, start)
            if j < 0: break
            out.append(j)
            start = j + len(w)
    return out
def _near_name(text, name, at, pad=900):
    pos = _name_positions(text, name)
    if not pos: return False
    return min(abs(at - p) for p in pos) <= pad
def _quote_at(text, at):
    raw = text or ""
    start = max(0, raw.rfind(".", 0, at) + 1)
    end = raw.find(".", at)
    if end == -1: end = min(len(raw), at + 90)
    return re.sub(r"\s+", " ", raw[start:end]).strip(" -")[:200]
def _sentences(text):
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        s = re.sub(r"\s+", " ", s).strip()
        if 30 <= len(s) <= 240 and not re.search(r"livechat|cookie|skip to|tweet|powered by", s, re.I):
            out.append(s)
    return out
def _best_sentence(text, *need):
    need = [n.lower() for n in need if n]
    best = ""
    for s in _sentences(text):
        low = s.lower()
        if need and not all(n in low for n in need): continue
        if not best or len(s) < len(best):
            best = s
    return best
def _town_ok(town):
    words = [w.lower() for w in (town or "").split()]
    extra = {"families", "helping", "services", "residents", "information", "access", "about", "contact", "search", "home", "menu", "skip", "support", "people", "young", "single"}
    if not words or words[0] in _TOWN_STOP or words[0] in extra: return ""
    if all(w in _TOWN_STOP or w in extra for w in words): return ""
    return town.strip()
def _town_from(text):
    raw = text or ""
    found = []
    for rx in (
        r"(?:run by|operated by|provided by|managed by)\s+[^.]{3,70}?\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+Housing Options\b",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:City |Borough |District |County )?Council\b",
        r"(?:based in|hostel in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    ):
        for m in re.finditer(rx, raw):
            town = _town_ok(m.group(1))
            if town: found.append((m.start(), town, _quote_at(raw, m.start())))
    return found
def _operator_ok(op, name):
    op = re.sub(r"\s+", " ", op or "").strip(" ,-|")
    if not op or len(op) < 3 or len(op) > 70: return ""
    if _OP_BAD.search(op): return ""
    if op.lower() in ("the council", "council", "housing options", "streetlink"): return ""
    if op.lower() == (name or "").lower(): return ""
    return op
def _operators(text, name, url):
    raw = text or ""
    found = []
    for m in re.finditer(r"(?:run by|operated by|provided by|managed by)\s+([^.]{3,80})", raw, re.I):
        op = _operator_ok(re.split(r"\s+in\s+", m.group(1), maxsplit=1)[0], name)
        if op: found.append((m.start(), op, _quote_at(raw, m.start())))
    host = discover.host(url)
    if host == "gov.uk" or host.endswith(".gov.uk"):
        for m in re.finditer(r"((?:City of |London Borough of )?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+Council)\b", raw):
            op = _operator_ok(m.group(1), name)
            if op: found.append((m.start(), op, _quote_at(raw, m.start())))
    head = raw[:240]
    for m in re.finditer(r"[|–-]\s*((?:[A-Z][A-Za-z0-9'&]+(?:\s+|$)){1,5})", head):
        op = _operator_ok(re.split(r"\s+(?:Our|Skip|Search|Menu|Home|News|Contact|What|Get|Chat|Show|Back|With)\b", m.group(1))[0], name)
        if op: found.append((m.start(), op, _quote_at(raw, m.start())))
    return found
def _phones(text, name):
    raw = text or ""
    found = []
    for p in PHONE_RE.findall(raw):
        shown = _uk_phone(p)
        if not shown: continue
        i = raw.find(p)
        local = raw[max(0, i - 60): i + len(p) + 60]
        if HQ_PHONE.search(local) or re.search(r"fundraising|donate", local, re.I): continue
        pos = _name_positions(raw, name)
        dist = min((abs(i - n) for n in pos), default=10 ** 9)
        found.append((dist, i, shown, _quote_at(raw, i)))
    found.sort()
    return found
def _routes(text):
    raw = text or ""
    found = []
    for m in CARD_ROUTE.finditer(raw):
        snip = _quote_at(raw, m.start())
        if NOT_ACCESS.search(snip): continue
        if re.search(r"preferences|livechat|skip to|powered by|cookie", snip, re.I): continue
        found.append((m.start(), snip))
    return found
_AREA_GENERIC = GENERIC | {"council", "city", "borough", "district", "county", "homelessness", "homeless",
    "scheme", "schemes", "project", "projects", "accommodation", "emergency", "temporary", "living",
    "services", "partnership", "association", "group", "people", "single", "young", "support",
    "resettlement", "options", "access", "point", "pathway", "advice", "team", "rough", "sleepers", "sleeper"}
def _area_names(text, name):
    """The specific part of the hostel name, not only the council or the word hostel.
    One short leftover such as 'york' is not enough."""
    words = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    d = {w for w in (discover.tokens(name) - _AREA_GENERIC) if len(w) >= 4}
    long = {w for w in d if len(w) >= 5}
    if len(long) >= 2: return long <= words
    if len(long) == 1: return bool(long & words)
    if len(d) >= 2: return d <= words
    return False
def _already_named(name, existing):
    """A hostel already on the map under the same specific name should not also become an area card."""
    d = {w for w in (discover.tokens(name) - _AREA_GENERIC) if len(w) >= 4}
    if len(d) < 2 and not any(len(w) >= 6 for w in d):
        return False
    for e in existing or []:
        ed = {w for w in (discover.tokens(e.get("name") or "") - _AREA_GENERIC) if len(w) >= 4}
        if len(d) >= 2 and d <= ed:
            return True
        if len(d) == 1 and d == ed:
            return True
    return False
def _page_supported_only(name, text):
    blob = (name or "") + " " + (text or "")
    if not SUPPORTED.search(blob): return False
    return not re.search(r"\bhostel\b|direct access|night shelter|emergency accommodation|emergency bed", blob, re.I)
def referral_area_card(name, pages):
    """An area card when an operator or council page names the hostel, who runs it, the town,
    a phone, and how to get a bed (referral, self-referral or direct access).
    No postcode and no pin. The page does not have to say the address is withheld.
    A building postcode on that page is a pin, not an area card. A refuge, a supported-only
    service, or a seasonal shelter without current dates is not a card."""
    blob = " ".join(t for _, t in pages or [])
    if is_refuge(name, blob) or is_refuge(name, ""): return None
    if re.search(r"domestic (?:abuse|violence)|\brefuge\b|women'?s\s+aid", name or "", re.I): return None
    if seasonal_reason(name, blob) and not any(not seasonal_reason(name, t) for _, t in pages or []):
        return None
    for url, text in pages or []:
        if _place_url(url) and best_building(text, name, url): return None
    for url, text in pages or []:
        if not _place_url(url): continue
        if seasonal_reason(name, text): continue
        if _page_supported_only(name, text): continue
        host = discover.host(url)
        council = host == "gov.uk" or host.endswith(".gov.uk")
        if council and not re.search(r"hostel|homeless|night shelter|emergency accommodation|direct access", url + " " + (text or ""), re.I):
            continue
        if not _area_names(text, name): continue
        wide = _url_names(url, name)
        routes = [r for r in _routes(text) if wide or _near_name(text, name, r[0])]
        if not routes: continue
        route, route_q = routes[0][1], routes[0][1]
        phones = [p for p in _phones(text, name) if wide or p[0] <= 1500]
        in_route = ""
        for p in PHONE_RE.findall(route_q):
            shown = _uk_phone(p)
            if shown:
                in_route = shown
                break
        if in_route:
            phones = [(0, 0, in_route, route_q)] + phones
        towns = [t for t in _town_from(text) if wide or _near_name(text, name, t[0])]
        ops = [o for o in _operators(text, name, url) if wide or _near_name(text, name, o[0])]
        if not (phones and towns and ops): continue
        phone, phone_q = phones[0][2], phones[0][3]
        town, town_q = towns[0][1], towns[0][2]
        operator, op_q = ops[0][1], ops[0][2]
        referralish = bool(re.search(r"referr|housing options", route, re.I)) and not re.search(r"\bno referral\b", route, re.I)
        notice = "Referral needed, don't turn up without one" if referralish else "Call before you go"
        name_at = (_name_positions(text, name) or [0])[0]
        specific = sorted((w for w in distinctive(name) if len(w) >= 5), key=len)
        name_q = _best_sentence(text, specific[-1] if specific else name.split()[0]) or _quote_at(text, name_at)
        op_sentence = _best_sentence(text, operator) or op_q
        town_sentence = route_q if town.lower() in route_q.lower() else (_best_sentence(text, town) or town_q)
        phone_digits = re.sub(r"\D", "", phone)
        phone_sentence = ""
        for s in _sentences(text):
            if phone_digits and phone_digits in re.sub(r"\D", "", s):
                phone_sentence = s
                break
        phone_sentence = phone_sentence or phone_q
        return {"id": "", "name": name, "card_type": "referral_hostel", "status": "proposal", "layer": "shelters",
                "operator": operator, "area": town, "town": town, "phone": phone, "phone_source": url,
                "referral_route": route, "label": "Referral hostel", "notice": notice,
                "postcode": "", "lat": None, "lng": None, "address": "",
                "operator_page": url, "evidence_url": url, "no_pin": True,
                "quotes": [
                    {"field": "name", "text": name_q},
                    {"field": "operator", "text": op_sentence},
                    {"field": "town", "text": town_sentence},
                    {"field": "phone", "text": phone_sentence},
                    {"field": "referral_route", "text": route_q},
                ],
                "evidence": ("council page names the hostel, the operator, the area, a phone and how to get a bed; no building postcode is used as a pin"
                             if council else
                             "operator page names the hostel, the operator, the area, a phone and how to get a bed; no building postcode is used as a pin")}
    return None
def second_pass_one(hold, fetcher, council_url="", directory_text="", existing=()):
    """One publishable hold. A council page counts only when it names this hostel and a building postcode.
    The directory postcode is still not the pin. A refuge is excluded."""
    name = hold.get("name") or ""
    text = directory_text or hold.get("directory_text") or ""
    if is_refuge(name, text):
        return "excluded", {"id": hold.get("id"), "name": name, "reason": "women's refuge or domestic abuse service — never mapped"}
    pages = operator_second_look(hold.get("website") or "", name, fetcher)
    if council_url:
        pages += council_follow(council_url, name, fetcher)
    cand = {"id": hold.get("id"), "name": name, "website": hold.get("website") or council_url or "",
            "directory": hold.get("directory"), "directory_url": hold.get("directory_url") or "",
            "referral_address": hold.get("referral_address") or "", "referral_postcode": hold.get("referral_postcode") or "",
            "directory_text": text, "hint": "hostel", "operator_pages": pages}
    return assess(cand, fetcher, datetime.date.today().isoformat(), list(existing or []))

def _districts(postcodes):
    """Council area for a postcode, used only to choose which council page to read. Never a pin."""
    cache = {}
    try:
        cache = json.load(open(os.path.join(ROOT, "overrides", "district_cache.json"), encoding="utf-8"))
    except Exception:
        cache = {}
    out = {}
    missing = []
    for pc in postcodes:
        if not split_pc(pc): continue
        shown = pc if " " in pc else (pc[:-3] + " " + pc[-3:] if len(norm_pc(pc)) > 3 else pc)
        hit = cache.get(shown) or cache.get(norm_pc(pc)) or cache.get(pc.upper())
        if hit: out[norm_pc(pc)] = hit
        else: missing.append(shown)
    if missing:
        try:
            import urllib.request
            for i in range(0, len(missing), 100):
                batch = missing[i:i + 100]
                req = urllib.request.Request("https://api.postcodes.io/postcodes",
                                              json.dumps({"postcodes": batch}).encode(),
                                              {"Content-Type": "application/json", "User-Agent": "helpmap.uk shelter check"})
                body = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
                for row in (body or {}).get("result") or []:
                    res = row.get("result") or {}
                    if res.get("admin_district") and row.get("query"):
                        out[norm_pc(row["query"])] = res["admin_district"]
        except Exception as ex:
            print("postcodes.io district lookup skipped:", ex)
    return out
SECOND_REASONS = ("no building postcode", "no operator page", "operator site unreachable", "operator link was a news")
def run_second_pass(root=None, fetcher=None, delay=0.25):
    """Re-check publishable holds against the operator sitemap and site search, and the council homelessness page."""
    root = root or ROOT
    path = os.path.join(root, "reports", "verified_new_places.json")
    doc = json.load(open(path, encoding="utf-8"))
    homes = load_council_homes(root)
    targets = []
    for h in doc.get("held") or []:
        if h.get("directory") not in ("Homeless Link", "Street Support"): continue
        if h.get("category") != "publishable": continue
        if not any((h.get("reason") or "").startswith(s) for s in SECOND_REASONS): continue
        targets.append(h)
    districts = _districts([h.get("referral_postcode") for h in targets if h.get("referral_postcode")])
    index = {}
    try: index = json.load(open(os.path.join(root, "logs", "shelter_source_index.json"), encoding="utf-8"))
    except Exception: index = {}
    texts = {("hl-" + k): (v.get("directory_text") or "") for k, v in (index.get("hl_services") or {}).items()}
    raw = fetcher or discover.fetch_raw
    fetch = raw if fetcher else polite(raw, delay=delay, cache_dir=os.path.join(root, CACHE))
    existing = load_existing(root)
    for p in doc.get("proposals") or []:
        existing.append({"id": p.get("id"), "name": p.get("name"), "postcode": p.get("postcode")})
    newly, still = [], []
    seen = {h.get("id") for h in targets}
    for n, h in enumerate(targets, 1):
        council = ""
        if (h.get("website") or "").endswith(".gov.uk") or discover.host(h.get("website")).endswith(".gov.uk"):
            council = h.get("website") or ""
        elif h.get("referral_postcode"):
            council = council_url_for(districts.get(norm_pc(h["referral_postcode"]), ""), homes)
        bucket, rec = second_pass_one(h, fetch, council_url=council, directory_text=texts.get(h.get("id"), ""), existing=existing)
        if bucket == "verified" and rec:
            newly.append(rec)
            existing.append({"id": rec["id"], "name": rec["name"], "postcode": rec["postcode"]})
        else:
            still.append(h.get("id"))
        if os.environ.get("SHELTER_SOURCE_PROGRESS"):
            print("second pass", n, "of", len(targets), "new", len(newly), h.get("name"), flush=True)
    doc["held"] = [h for h in doc["held"] if h.get("id") not in {r["id"] for r in newly}]
    doc["proposals"] = list(doc.get("proposals") or []) + newly
    doc["second_pass"] = {"checked": len(targets), "newly_verified": len(newly),
                          "ids": [r["id"] for r in newly]}
    doc["counts"]["verified"] = len(doc["proposals"])
    doc["counts"]["held"] = len(doc["held"])
    by = doc["counts"].get("by_source") or {}
    for key, label in (("homeless_link", "Homeless Link"), ("street_support", "Street Support")):
        if key not in by: continue
        got = [r for r in newly if r.get("directory") == label]
        by[key]["verified"] = by[key].get("verified", 0) + len(got)
        by[key]["held"] = max(0, by[key].get("held", 0) - len(got))
    write_report(path, doc)
    return doc["second_pass"]
def review_open_proposals(root=None, fetcher=None):
    """Stoll stays proposed only if its own page describes emergency or direct-access beds.
    Contact Hostel stays proposed only with a phone read on its own page."""
    root = root or ROOT
    path = os.path.join(root, "reports", "verified_new_places.json")
    doc = json.load(open(path, encoding="utf-8"))
    raw = fetcher or discover.fetch_raw
    fetch = raw if fetcher else polite(raw, delay=0.2, cache_dir=os.path.join(root, CACHE))
    kept, demoted = [], []
    for p in doc.get("proposals") or []:
        res = fetch(p.get("operator_page") or p.get("website") or "")
        text = _text(res["html"]) if _ok(res) else ""
        if veterans_supported_only(p.get("name"), text):
            q = dict(p, status="held", category="supported",
                     reason="longer-term supported housing or Emmaus — not published")
            for k in ("postcode", "address", "lat", "lng", "phone", "phone_source", "access", "access_type"):
                q.pop(k, None)
            demoted.append(q)
            continue
        if re.search(r"contact hostel", p.get("name") or "", re.I):
            phone = phone_near(text, p.get("postcode") or "")
            if not phone:
                q = dict(p, status="held", reason="no phone on the place's own page")
                q.pop("phone", None); q.pop("phone_source", None)
                demoted.append(q)
                continue
            p = dict(p, phone=phone, phone_source=res.get("final_url") or p.get("operator_page"))
        kept.append(strip_council(p))
    doc["proposals"] = kept
    doc["held"] = list(doc.get("held") or []) + demoted
    doc["counts"]["verified"] = len(kept)
    doc["counts"]["held"] = len(doc["held"])
    hl = (doc.get("counts") or {}).get("by_source", {}).get("homeless_link")
    if hl:
        hl["verified"] = sum(1 for p in kept if p.get("directory") == "Homeless Link")
        hl["held"] = hl.get("held", 0) + sum(1 for p in demoted if p.get("directory") == "Homeless Link")
    write_report(path, doc)
    return {"kept": [p["name"] for p in kept], "demoted": [p["name"] for p in demoted]}
def _drop_pin(rec, reason, category=None):
    q = dict(rec, status="held", reason=reason)
    if category: q["category"] = category
    for k in ("postcode", "address", "lat", "lng", "phone", "phone_source", "access", "access_type", "postcode_note", "evidence", "no_pin"):
        q.pop(k, None)
    return strip_council(q)
def audit_open_proposals(root=None, fetcher=None):
    """Drop a pin whose page is a search, news or office page, or whose postcode is not that building.
    Stoll and shared houses stay held unless the page describes emergency beds. Contact Hostel needs its own phone."""
    root = root or ROOT
    path = os.path.join(root, "reports", "verified_new_places.json")
    doc = json.load(open(path, encoding="utf-8"))
    raw = fetcher or discover.fetch_raw
    fetch = raw if fetcher else polite(raw, delay=0.15, cache_dir=os.path.join(root, CACHE))
    kept, demoted, excluded_n = [], [], []
    for p in doc.get("proposals") or []:
        if not isinstance(p, dict) or p.get("layer") not in (None, "", "shelters") or p.get("card_type") == "referral_hostel":
            kept.append(p)
            continue
        url = p.get("operator_page") or ""
        if not _place_url(url):
            demoted.append(_drop_pin(p, "confirming page was a search, news or office page, not the building"))
            continue
        res = fetch(url)
        text = _text(res["html"]) if _ok(res) else ""
        host = discover.host(url)
        if text and (host == "gov.uk" or host.endswith(".gov.uk")) and not re.search(
                r"hostel|homeless|night shelter|emergency accommodation", url + " " + text, re.I):
            demoted.append(_drop_pin(p, "council page does not describe a hostel or homelessness service"))
            continue
        if not text or not names_place(text, p.get("name")):
            demoted.append(_drop_pin(p, "no building postcode on the operator page (directory postcode is a referral address only)"))
            continue
        if is_refuge(p.get("name"), text):
            excluded_n.append({"id": p.get("id"), "name": p.get("name"), "directory": p.get("directory"),
                               "reason": "women's refuge or domestic abuse service — never mapped"})
            continue
        if veterans_supported_only(p.get("name"), text) or shared_housing_only(p.get("name"), text):
            demoted.append(_drop_pin(p, "longer-term supported housing or Emmaus — not published", "supported"))
            continue
        hit = best_building(text, p.get("name"), url)
        if not hit or norm_pc(hit[0]) != norm_pc(p.get("postcode")):
            demoted.append(_drop_pin(p, "no building postcode on the operator page (directory postcode is a referral address only)"))
            continue
        if re.search(r"contact hostel", p.get("name") or "", re.I):
            phone = phone_near(text, p.get("postcode") or "")
            if not phone:
                demoted.append(_drop_pin(p, "no phone on the place's own page"))
                continue
            p = dict(p, phone=phone, phone_source=res.get("final_url") or url)
        kept.append(strip_council(p))
    doc["proposals"] = kept
    held_ids = {h.get("id") for h in doc.get("held") or []}
    for d in demoted:
        if d.get("id") not in held_ids:
            doc.setdefault("held", []).append(d)
            held_ids.add(d.get("id"))
    if excluded_n:
        doc["excluded"] = list(doc.get("excluded") or []) + excluded_n
    doc.setdefault("counts", {})
    doc["counts"]["verified"] = len([p for p in kept if p.get("layer") in (None, "", "shelters")])
    doc["counts"]["held"] = len(doc.get("held") or [])
    doc["counts"]["excluded"] = len(doc.get("excluded") or [])
    labels = {"homeless_link": "Homeless Link", "street_support": "Street Support",
              "lifehouses": "Salvation Army Lifehouses", "nihe": "NIHE self-referral hostels"}
    for key, label in labels.items():
        row = (doc["counts"].get("by_source") or {}).get(key)
        if not row: continue
        row["verified"] = sum(1 for p in kept if p.get("directory") == label)
        row["held"] = sum(1 for h in doc.get("held") or [] if h.get("directory") == label)
    doc["audit"] = {"kept": [p.get("name") for p in kept if p.get("layer") in (None, "", "shelters")],
                    "demoted": [p.get("name") for p in demoted],
                    "excluded": [p.get("name") for p in excluded_n]}
    write_report(path, doc)
    return doc["audit"]
def run_area_cards(root=None, fetcher=None, delay=0.15):
    """Area cards for publishable hostels whose building address is not public.
    Written to area_cards for review. Not added to shelters.js, not pinned, not put in SWEP or emergency banners."""
    root = root or ROOT
    path = os.path.join(root, "reports", "verified_new_places.json")
    doc = json.load(open(path, encoding="utf-8"))
    homes = load_council_homes(root)
    verified_ids = {p.get("id") for p in doc.get("proposals") or [] if isinstance(p, dict)}
    targets = []
    for h in doc.get("held") or []:
        if h.get("id") in verified_ids: continue
        name = h.get("name") or ""
        if is_refuge(name, h.get("reason") or "") or is_refuge(name, ""): continue
        if re.search(r"domestic (?:abuse|violence)|\brefuge\b|women'?s\s+aid", name, re.I): continue
        if h.get("category") == "supported": continue
        reason = h.get("reason") or ""
        if reason.startswith("seasonal") or "supported housing" in reason: continue
        directory = h.get("directory") or ""
        if directory in ("Homeless Link", "Street Support"):
            if not reason.startswith("no building postcode"): continue
            if h.get("category") not in ("publishable", "hostel", "emergency", "night shelter", "direct access"): continue
        elif "NIHE" not in directory or h.get("category") != "publishable":
            continue
        targets.append(h)
    districts = _districts([h.get("referral_postcode") for h in targets if h.get("referral_postcode")])
    index = {}
    try: index = json.load(open(os.path.join(root, "logs", "shelter_source_index.json"), encoding="utf-8"))
    except Exception: index = {}
    texts = {("hl-" + k): (v.get("directory_text") or "") for k, v in (index.get("hl_services") or {}).items()}
    raw = fetcher or discover.fetch_raw
    fetch = raw if fetcher else polite(raw, delay=delay, cache_dir=os.path.join(root, CACHE))
    existing = load_existing(root)
    cards, seen = [], set()
    by_source, by_place = {}, {}
    for n, h in enumerate(targets, 1):
        src = h.get("directory") or "unknown"
        by_source.setdefault(src, {"checked": 0, "proposed": 0})
        by_source[src]["checked"] += 1
        name = h.get("name") or ""
        pages = operator_second_look(h.get("website") or "", name, fetch) if h.get("website") else []
        council = ""
        if discover.host(h.get("website")).endswith(".gov.uk"):
            council = h.get("website") or ""
        elif h.get("referral_postcode"):
            council = council_url_for(districts.get(norm_pc(h["referral_postcode"]), ""), homes)
        elif h.get("town"):
            council = council_url_for(h.get("town"), homes)
        if council:
            pages += council_follow(council, name, fetch)
        pages = [(u, t) for u, t in pages if _place_url(u)]
        if _already_named(name, existing):
            if os.environ.get("SHELTER_SOURCE_PROGRESS"):
                print("area card", n, "of", len(targets), "kept", len(cards), "already listed", name, flush=True)
            continue
        card = referral_area_card(name, pages)
        if os.environ.get("SHELTER_SOURCE_PROGRESS"):
            print("area card", n, "of", len(targets), "kept", len(cards), name, flush=True)
        if not card: continue
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        if key in seen: continue
        seen.add(key)
        place_type = publishable_label(name, texts.get(h.get("id"), "") or h.get("directory_text") or "", h.get("hint") or "hostel")
        card.update({"id": h.get("id") or "", "directory": src, "directory_url": h.get("directory_url") or "",
                     "website": h.get("website") or "", "place_type": place_type})
        card.pop("referral_postcode", None)
        card.pop("referral_address", None)
        cards.append(strip_council(card))
        by_source[src]["proposed"] += 1
        by_place[place_type] = by_place.get(place_type, 0) + 1
    doc["area_cards"] = cards
    doc["area_card_counts"] = {"by_source": by_source, "by_type": {"referral_hostel": len(cards)},
                               "by_place_type": by_place, "checked": len(targets), "proposed": len(cards),
                               "note": "Proposals only. Not published. No building pin. A directory postcode is not a location. Not shown in emergency or SWEP banners."}
    extra = " Referral hostel area cards are listed under area_cards for review: no building pin, and not published."
    if extra.strip() not in (doc.get("about") or ""):
        doc["about"] = (doc.get("about") or "") + extra
    write_report(path, doc)
    return doc["area_card_counts"]
def _main():
    import sys
    did = False
    if "--second-pass" in sys.argv:
        print(json.dumps(review_open_proposals(), indent=1))
        print(json.dumps(run_second_pass(), indent=1)[:4000])
        did = True
    if "--audit" in sys.argv:
        print(json.dumps(audit_open_proposals(), indent=1)[:4000])
        did = True
    if "--area-cards" in sys.argv:
        print(json.dumps(run_area_cards(), indent=1)[:4000])
        did = True
    if did: return
    delay = float(os.environ.get("SHELTER_SOURCE_DELAY", "0.4"))
    lim = os.environ.get("SHELTER_EVIDENCE_LIMIT")
    pages = os.environ.get("SHELTER_HL_PAGES")
    services = os.environ.get("SHELTER_HL_SERVICES")
    doc_status = refresh(delay=delay,
                         evidence_limit=int(lim) if lim else None,
                         max_hl_pages=int(pages) if pages else None,
                         service_limit=int(services) if services else None)
    print(json.dumps(doc_status, indent=1)[:4000])

if __name__ == "__main__":
    _main()
