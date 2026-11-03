"""Put a SWEP shelter or emergency provision on the map when the watch confirms it is open.

The page has to be the council's or the provider's own page, and the existing SWEP
wording check has to say it is active. Each place is judged on its own: one place
without a verified phone is held, and the others on that page still go on. A hold
lasts for this run only. The next run reads the page again. Nothing here writes a
skip list or a permanent freeze.

A confirmed place is a normal shelter pin (blue square, house symbol) with the label
"Severe weather shelter (SWEP)" and the badge "Rough sleeper shelter open tonight".
It is not a red incident rest-centre pin and it is not added to the incident banner.
"""
import datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone_rule

LABEL = "Severe weather shelter (SWEP)"
LABEL_CY = "Lloches tywydd garw (SWEP)"
BADGE = "Rough sleeper shelter open tonight"
HELD_LOG = "logs/swep_live_held.json"
PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
PROVISION = re.compile(
    r"night ?shelter|emergency accommodation|emergency beds?|winter shelter|"
    r"severe weather shelter|cold weather (?:shelter|provision)|emergency provision|"
    r"\bSWEP\b|rough sleeper shelter",
    re.I)
TIME_WORDS = re.compile(
    r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*(?:-|–|to)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
    re.I)
TIME_24 = re.compile(r"\b((?:[01]?\d|2[0-3]):[0-5]\d)\s*(?:-|–|to)\s*((?:[01]?\d|2[0-3]):[0-5]\d)\b")
DENY_HOSTS = (
    "homeless.org.uk", "streetsupport.net", "wikipedia.org", "facebook.com", "twitter.com",
    "x.com", "bbc.co.uk", "bbc.com", "theguardian.com", "google.com", "google.co.uk",
    "instagram.com", "youtube.com",
)
GOV_SUFFIX = (".gov.uk", ".gov.scot", ".gov.wales", ".gov.ni", ".llyw.cymru")


def host_of(url):
    import urllib.parse
    return urllib.parse.urlparse(url or "").netloc.split(":")[0].lower().removeprefix("www.")


def is_own_page(url, site=None):
    """Council site, a .gov host, or the provider page this watch was given. Directories and news sites are not."""
    h = host_of(url)
    if not h:
        return False
    if site:
        import weather
        if weather.own_site(url, site):
            return True
    if any(h == d or h.endswith("." + d) for d in DENY_HOSTS):
        return False
    if h.endswith(GOV_SUFFIX):
        return True
    return True


def _sites(root):
    path = os.path.join(root or ".", "scripts", "sweep_sources.json")
    try:
        rows = json.load(open(path, encoding="utf-8")).get("councils") or []
    except Exception:
        return {}
    return {c.get("code"): c.get("site") for c in rows if c.get("code")}


def _norm_pc(m):
    return (m.group(1) + " " + m.group(2)).upper()


def _blocks(text):
    """One chunk per postcode. Text after a postcode stays with that place until the next 'at <name>'."""
    found = list(PC_RE.finditer(text or ""))
    starts = []
    for i, m in enumerate(found):
        if i == 0:
            starts.append(max(0, m.start() - 400))
            continue
        between = text[found[i - 1].end():m.start()]
        at = between.rfind(" at ")
        if at >= 0:
            sentence = between.rfind(". ", 0, at)
            starts.append(found[i - 1].end() + (sentence + 2 if sentence >= 0 else at))
            continue
        dot = between.rfind(". ")
        starts.append(found[i - 1].end() + (dot + 2 if dot >= 0 else 0))
    out = []
    for i, m in enumerate(found):
        end = starts[i + 1] if i + 1 < len(found) else len(text)
        out.append((text[starts[i]:end], _norm_pc(m), starts[i], end))
    return out


def _venue_name(block):
    m = PC_RE.search(block or "")
    before = block[:m.start()] if m else (block or "")
    before = before.strip(" ,.;")
    ats = list(re.finditer(r"\bat\s+((?:the\s+)?[A-Z0-9][^,]{2,80})", before))
    if ats:
        raw = ats[-1].group(1)
    else:
        parts = [p.strip(" ,.;") for p in before.split(",") if p.strip(" ,.;")]
        raw = parts[-1] if parts else ""
        if re.match(r"\d", raw) and len(parts) >= 2:
            raw = parts[-2]
    raw = re.split(r"\b(for|open|call|tel|from|tonight|people|phone)\b", raw, maxsplit=1, flags=re.I)[0]
    raw = re.sub(r"^(?:the\s+)?(?:emergency accommodation|night shelter|severe weather shelter)\s+", "", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw).strip(" ,.;-–—")
    if len(raw) < 3 or len(raw) > 80:
        return ""
    if raw.lower() in {"the", "swep", "council", "tonight"}:
        return ""
    return raw


def _address(block, name, pc):
    m = PC_RE.search(block or "")
    before = block[:m.start()] if m else ""
    idx = before.rfind(name) if name else -1
    street = before[idx:] if idx >= 0 else (name or "")
    street = re.sub(r"\s+", " ", street).strip(" ,.;")
    if pc and pc not in street.upper():
        street = (street + " " + pc).strip()
    return street


def _numbers(text):
    out, seen = [], set()
    for m in phone_rule.PHONE_RE.finditer(text or ""):
        raw = re.sub(r"\s+", " ", m.group(0)).strip()
        d = phone_rule.digits(raw)
        if d in seen or len(d) not in (10, 11) or not d.startswith("0"):
            continue
        seen.add(d)
        out.append((d, raw))
    return out


def _usable_number(text, pair):
    d, raw = pair
    if phone_rule.is_dean(d, text=text):
        return False
    if phone_rule.other_label(text, d):
        return False
    return True


def _groups(block):
    found = []
    rules = (
        (r"\bmen only\b|\bfor men\b", "Men"),
        (r"\bwomen only\b|\bfor women\b", "Women"),
        (r"\bfamilies\b", "Families"),
        (r"people sleeping rough|rough sleepers?|street homeless|anyone who is (?:street )?homeless", "People sleeping rough"),
    )
    for pat, label in rules:
        if re.search(pat, block or "", re.I) and label not in found:
            found.append(label)
    return found


def _wheelchair(block):
    text = block or ""
    if re.search(r"wheelchair accessible toilets?\b", text, re.I) and not re.search(r"wheelchair accessible(?!\s+toilet)", text, re.I):
        if not re.search(r"\bwheelchair access\b", text, re.I):
            return ""
    if re.search(r"\bnot wheelchair\b|\bno wheelchair access\b", text, re.I):
        return "no"
    if re.search(r"\bpartial(?:ly)? wheelchair\b", text, re.I):
        return "partial"
    if re.search(r"\bwheelchair accessible\b|\bwheelchair access\b", text, re.I):
        return "yes"
    return ""


def _access(block):
    import shelter_sources
    route = shelter_sources.access_route(block or "")
    if re.search(r"\bno referral\b|walk[- ]in|direct access|open access", block or "", re.I) and not re.search(r"no walk[- ]in", block or "", re.I):
        at = "open_access"
        route = re.sub(r"^walk[- ]in\s*[,.:;-]?\s*", "", route or "", flags=re.I).strip()
    else:
        at = shelter_sources.access_type_of(route)
    return route, at


def _not_this_provision(name, block):
    import shelter_sources
    if shelter_sources.is_refuge(name, block):
        return "women's refuge"
    if re.search(r"\bfoyers?\b|young people'?s housing", name or "", re.I):
        return "young people's housing"
    if re.search(r"\bfoyers?\b", block or "", re.I) and re.search(r"16\s*[-–to]{1,3}\s*25", block or "", re.I):
        if not re.search(r"night shelter|emergency accommodation|emergency bed", name or "", re.I):
            return "young people's housing"
    day = re.search(r"day ?centre|daytime only", block or "", re.I) or re.search(r"day ?centre", name or "", re.I)
    overnight = re.search(r"night|overnight|tonight|emergency bed|emergency accommodation|\bSWEP\b", block or "", re.I)
    if day and not overnight:
        return "day centre"
    return ""


def _times(block, pc, name):
    ot = None
    try:
        import discover
        ot = discover.extract_times(block, pc, name=name)
    except Exception:
        ot = None
    if ot and ot.get("status") == "TIMES_FOUND":
        try:
            import discover
            hours = discover.hours_from_ot(ot)
        except Exception:
            hours = None
        if hours:
            return hours
    m = TIME_WORDS.search(block or "") or TIME_24.search(block or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(0)).strip()


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s or "place")[:60]


def _geocode(pc, geocoder):
    if geocoder:
        return geocoder(pc)
    import urllib.request
    try:
        u = "https://api.postcodes.io/postcodes/" + pc.replace(" ", "")
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "helpmap.uk"}), timeout=8).read())
        res = r.get("result") or {}
        if r.get("status") == 200 and res.get("latitude") is not None:
            return res.get("latitude"), res.get("longitude")
    except Exception:
        return None
    return None


def _hold(name, url, reason, pc=""):
    return {"name": name or "", "url": url or "", "postcode": pc or "", "reason": reason}


def places_from_page(page, run_day, geocoder=None, used=None, shared_numbers=None):
    """One page. Each postcode block is accepted or held on its own."""
    text = re.sub(r"\s+", " ", page.get("_text") or "").strip()
    url = page.get("url") or ""
    council = page.get("council") or ""
    used = used if used is not None else set()
    live, held = [], []
    if page.get("status") != "active" or page.get("http") != 200:
        return live, held
    if not is_own_page(url, page.get("site")):
        held.append(_hold("", url, "not the council's or provider's own page"))
        return live, held
    blocks = _blocks(text)
    covered = []
    for m in phone_rule.PHONE_RE.finditer(text):
        if any(a <= m.start() < b for _, _, a, b in blocks):
            covered.append(phone_rule.digits(m.group(0)))
    intro = [p for p in _numbers(text) if p[0] not in covered and _usable_number(text, p)]
    if shared_numbers is not None:
        intro = list(shared_numbers)
    for block, pc, _a, _b in blocks:
        near = block
        name = _venue_name(near)
        why = _not_this_provision(name, near)
        if not PROVISION.search(near):
            if why and name:
                held.append(_hold(name, url, why, pc))
            continue
        if not name:
            held.append(_hold("", url, "no place name on the page", pc))
            continue
        if why:
            held.append(_hold(name, url, why, pc))
            continue
        nums = [p for p in _numbers(near) if _usable_number(near, p)]
        if not nums and len(intro) == 1:
            nums = list(intro)
        if len(nums) != 1:
            held.append(_hold(name, url, "no verified phone", pc))
            continue
        digits, raw = nums[0]
        if phone_rule.is_dean(digits, text=text):
            held.append(_hold("", url, "not published", pc))
            continue
        loc = _geocode(pc, geocoder)
        if not loc or loc[0] is None or loc[1] is None:
            held.append(_hold(name, url, "location not confirmed", pc))
            continue
        groups = _groups(near)
        route, access_type = _access(near)
        wheel = _wheelchair(near)
        hours = _times(near, pc, name)
        iid = "swep-" + _slug(council) + "-" + _slug(pc)
        n = 2
        while iid in used:
            iid = "swep-" + _slug(council) + "-" + _slug(pc) + "-" + str(n)
            n += 1
        used.add(iid)
        item = {
            "id": iid,
            "name": name,
            "address": _address(near, name, pc),
            "postcode": pc,
            "lat": loc[0],
            "lng": loc[1],
            "phone": raw,
            "tel": digits,
            "website": url,
            "hours": hours or "",
            "referral": route or "",
            "access_type": access_type or "",
            "groups": groups,
            "who_for": "" if groups else "Not stated",
            "season": "Not stated",
            "kind": "severe_weather",
            "label": LABEL,
            "label_cy": LABEL_CY,
            "badge": BADGE,
            "source": council,
            "source_url": url,
            "evidence_url": url,
            "evidence_name": host_of(url),
            "last_verified": run_day,
            "verified_on": run_day,
            "checked_on": run_day,
            "tier": "verified",
            "verified": True,
            "swep_live": True,
            "council": council,
        }
        if groups:
            item["groups_source"] = url
        if hours:
            item["hours_checked"] = run_day
        if wheel:
            item["wheelchair"] = wheel
            item["wheelchair_source"] = url
        if access_type:
            item["referral"] = route or item["referral"]
        live.append(item)
    return live, held


def _page_site(page, sites):
    if page.get("site"):
        return page.get("site")
    return sites.get(page.get("code") or "") or ""


def apply(pages, run_day=None, root=None, geocoder=None):
    """Reconcile shelters.js with this run's confirmed places. Returns counts. Does not rewrite the file when nothing changed."""
    root = root or os.getcwd()
    run_day = run_day or datetime.date.today().isoformat()
    sites = _sites(root)
    import common
    import private_block
    path = os.path.join(root, "shelters.js")
    data = common.load_js(path, "SHELTERS") if os.path.exists(path) else None
    if not isinstance(data, dict):
        data = {"updated": run_day, "items": [], "recently_closed": [], "sources": {}}
    items = list(data.get("items") or [])
    by_url = {}
    for p in pages or []:
        url = p.get("url") or ""
        if not url or p.get("http") is None:
            continue
        by_url[url] = p
    kept_urls, decided_urls = set(), set()
    for url, p in by_url.items():
        if p.get("http") != 200:
            kept_urls.add(url)
        else:
            decided_urls.add(url)
    live, held = [], []
    used = set()
    for url, p in by_url.items():
        if url not in decided_urls:
            continue
        work = dict(p)
        work["site"] = _page_site(p, sites)
        if work.get("status") != "active":
            continue
        found, holds = places_from_page(work, run_day, geocoder=geocoder, used=used)
        live.extend(found)
        held.extend(holds)
    secrets = os.environ.get("PRIVATE_BLOCKLIST", "")
    if secrets:
        kept_live = []
        for item in live:
            if private_block.matches(item, secrets):
                held.append(_hold("", item.get("source_url") or "", "not published", item.get("postcode") or ""))
            else:
                kept_live.append(item)
        live = kept_live
    live_ids = {i["id"] for i in live}
    new_items, removed = [], []
    for item in items:
        if not item.get("swep_live") and not str(item.get("id") or "").startswith("swep-"):
            new_items.append(item)
            continue
        url = item.get("source_url") or ""
        if url in kept_urls or url not in by_url:
            if item.get("id") not in live_ids:
                new_items.append(item)
            continue
        removed.append(item.get("id"))
    new_items.extend(live)
    changed = [i for i in items if i.get("swep_live") or str(i.get("id") or "").startswith("swep-")]
    same = json.dumps(changed, sort_keys=True, default=str) == json.dumps(
        [i for i in new_items if i.get("swep_live") or str(i.get("id") or "").startswith("swep-")],
        sort_keys=True, default=str)
    if not same:
        data["items"] = new_items
        os.makedirs(os.path.dirname(path), exist_ok=True)
        common.write_js(path, "SHELTERS", data)
    held_path = os.path.join(root, HELD_LOG)
    os.makedirs(os.path.dirname(held_path), exist_ok=True)
    json.dump({"run": run_day, "held": held}, open(held_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return {"live": [i["id"] for i in live], "held": held, "removed": removed, "wrote": not same}
