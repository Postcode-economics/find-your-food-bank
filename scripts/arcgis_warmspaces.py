"""Council ArcGIS FeatureServer warm-space feeds.

overrides/arcgis_warmspaces.json lists query URLs. Each refresh reads the feed, keeps times from it,
and skips a record with no postcode or no times that can be shown as a Mon–Sun table. Ids stay stable:
a place already on the Warm Welcome list or in logs/warmspaces_pending.json keeps that id. A new place
keeps an id from its name and postcode, not from the row order.

Phone and council-line fields are never set here.
"""
import datetime, json, os, re
import hours_norm as H

INVIS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
SEASON_START = datetime.date(2026, 9, 1)
WARM_ACTIVITY = re.compile(r"warm\s+welcome|warm\s+space", re.I)
ADDR_JUNK = re.compile(r"^(?:street\s+record|former)\s*,?\s*", re.I)
URL_OK = re.compile(r"^https?://[a-z0-9][-a-z0-9.+]*(?::\d+)?/", re.I)
LANCS_HOLD_REASON = "Lancashire feed not yet confirmed for 2026-27"

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FEEDS = os.path.join(ROOT, "overrides", "arcgis_warmspaces.json")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d - ([01]\d|2[0-3]):[0-5]\d$")
PC_RE = re.compile(r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b", re.I)
HARD_SKIP = re.compile(r"\b(term[\s-]?time|fortnightly|monthly|appointment|only when|except)\b", re.I)
DAY = (r"(?:mon(?:day)?s?|tues(?:day)?s?|tue|wed(?:nesday)?s?|thurs(?:day)?s?|thu|"
       r"fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?)")
GROUP = DAY + r"(?:\s*(?:,|&|and|to|-|–|—)\s*" + DAY + r")*"
CLOCK = r"(?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2}|12pm)"
RANGE = CLOCK + r"\s*(?:-|–|—|to|until|till)\s*" + CLOCK
RANGE_RX = re.compile(RANGE, re.I)
CLOSED_RX = re.compile(r"(" + GROUP + r")\s*[:\-]?\s*closed\b", re.I)
GAP_BAD = re.compile(r"\b(?:term|appoint|except|only when|young|aged|fortnight|month)\b", re.I)
GENERIC = {"library", "church", "centre", "center", "community", "sports", "leisure", "hall",
           "methodist", "group", "groups", "faith", "complex", "square"}


def load_config(path=None):
    path = path or FEEDS
    raw = json.load(open(path, encoding="utf-8"))
    return [f for f in raw.get("feeds") or [] if f.get("url")]


def _get_json(url, getter):
    body = getter(url)
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    return json.loads(body)


def fetch_features(url, getter):
    """Follow resultOffset when the server sets exceededTransferLimit."""
    features, offset, seen = [], 0, 0
    while seen < 8:
        page = url if offset == 0 else url + ("&" if "?" in url else "?") + "resultOffset=%d" % offset
        data = _get_json(page, getter)
        batch = data.get("features") or []
        features.extend(batch)
        if not data.get("exceededTransferLimit") or not batch:
            return features
        offset += len(batch)
        seen += 1
    return features


def _postcode(text):
    m = PC_RE.search(text or "")
    return (m.group(1) + " " + m.group(2)).upper() if m else ""


def _outward(pc):
    m = re.match(r"([A-Z]{1,2}\d[A-Z\d]?)", (pc or "").upper().strip())
    return m.group(1) if m else ""


def _pc_key(pc):
    return re.sub(r"[^A-Z0-9]", "", (pc or "").upper())


def _tokens(name):
    s = (name or "").lower().replace("’", "'").replace("@", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return [w for w in s.split() if w not in {"the", "and", "of", "at", "a"} and len(w) > 1]


def same_place(a, b):
    """Same venue: equal names in the same postcode district, or the same postcode with a shared distinctive word."""
    ta, tb = _tokens(a.get("name")), _tokens(b.get("name"))
    if not ta or not tb:
        return False
    pa, pb = _pc_key(a.get("postcode")), _pc_key(b.get("postcode"))
    if ta == tb and _outward(a.get("postcode")) and _outward(a.get("postcode")) == _outward(b.get("postcode")):
        return True
    if pa and pa == pb:
        if ta == tb:
            return True
        if (set(ta) & set(tb)) - GENERIC:
            return True
    return False


def _strip_invisible(text):
    return INVIS.sub("", str(text or ""))


def _clean_address(addr):
    s = re.sub(r"\s+", " ", _strip_invisible(addr or "")).strip()
    while True:
        n = ADDR_JUNK.sub("", s, count=1).strip()
        if n == s:
            break
        s = n
    return s


def _clean_phone(raw):
    return re.sub(r"\s+", " ", _strip_invisible(raw)).strip()


def _feed_website(raw, feed):
    fb = feed.get("website") or ""
    u = _http_url(_strip_invisible(raw))
    if not u or " " in u or not URL_OK.match(u):
        return fb
    if u.lower().count("http") > 1:
        return fb
    return u


def _arcgis_stamp(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        ms = float(v)
        if ms > 1e12:
            ms /= 1000.0
        try:
            return datetime.datetime.utcfromtimestamp(ms).date()
        except (OSError, ValueError, OverflowError):
            return None
    s = str(v).strip()[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def record_current_for_season(attrs, feed, run_day=None):
    """Feed row or layer must be current for 2026-27 (edited since 1 Sep 2026 or named 2026-27 in layer metadata)."""
    blob = " ".join(str(feed.get(k) or "") for k in ("id", "source", "url", "council"))
    if re.search(r"2026\s*[-/]?\s*27", blob, re.I):
        return True
    for key in ("editdate", "creationdate", "last_edited_date", "orglastupdated"):
        dt = _arcgis_stamp((attrs or {}).get(key))
        if dt and dt >= SEASON_START:
            return True
    return False


def _merge_day_cell(existing, new_cell):
    if not existing:
        return new_cell
    if existing == new_cell:
        return existing
    seen, parts = set(), []
    for cell in (existing + " / " + new_cell).split(" / "):
        cell = cell.strip()
        if cell and cell not in seen:
            seen.add(cell)
            parts.append(cell)
    return " / ".join(parts)


def _table_from_pairs(text):
    cleaned = _clean_hours_text(_prepare_council_hours_text(text))
    pairs = _pairs(cleaned)
    if not pairs:
        return None, "no times"
    table = {}
    for days, body in pairs:
        chunk = "%s %s" % (days, body)
        conv, _ = H.try_convert(chunk)
        part = H.struct_to_hours(conv) if conv else None
        if not part:
            continue
        for day in DAYS:
            if day not in part:
                continue
            cell = _uniform_cell(part[day])
            if cell:
                table[day] = _merge_day_cell(table.get(day), cell)
    if not table or not any(v != "Closed" for v in table.values()):
        return None, "no times"
    return {d: table[d] for d in DAYS if d in table}, ""


def _clean_hours_text(text):
    s = (text or "").replace("\u2013", "-").replace("\u2014", "-").replace("\xa0", " ")
    s = re.sub(r"\b12\s*noon\b", "12pm", s, flags=re.I)
    s = re.sub(r"\b(noon|midday)\b", "12pm", s, flags=re.I)
    s = re.sub(r"\bLibraries Extra\b", "", s, flags=re.I)
    s = re.sub(r"\bStaffed\b", "", s, flags=re.I)
    s = re.sub(r"\bweekends?\b", "Saturday and Sunday", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .;")
    return s


def _uniform_cell(cell):
    cell = re.sub(r"\s*\([^)]*\)", "", str(cell or "")).strip()
    if re.fullmatch(r"closed", cell, re.I):
        return "Closed"
    if cell == "24 hours":
        return cell
    parts = []
    for part in cell.split(" / "):
        part = part.strip()
        if not TIME_RE.match(part):
            return None
        parts.append(part)
    return " / ".join(parts) if parts else None


def _pairs(cleaned):
    """Day + clock range, allowing a short gap ('access from', 'drop in between'). A gap that changes the meaning is left out."""
    pairs = []
    for m in RANGE_RX.finditer(cleaned):
        window = cleaned[max(0, m.start() - 90):m.start()]
        days = list(re.finditer(GROUP, window, re.I))
        if not days:
            continue
        gap = window[days[-1].end():]
        if GAP_BAD.search(gap) or RANGE_RX.search(gap):
            continue
        pairs.append((days[-1].group(0), re.sub(r"\s+", " ", m.group(0))))
    for m in CLOSED_RX.finditer(cleaned):
        pairs.append((m.group(1), "Closed"))
    return pairs


def _prepare_council_hours_text(text):
    """Normalise common council free-text hours before try_convert / hours_table."""
    s = (text or "").replace("\r", "\n")
    s = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", s)
    s = re.sub(r"(\d)(am|pm)\b", r"\1 \2", s, flags=re.I)
    out = []
    for line in s.split("\n"):
        line = re.sub(r"\s+", " ", line.strip())
        if not line:
            continue
        line = re.sub(r"^(" + DAY + r")\s*:\s*", r"\1 ", line, flags=re.I)
        line = re.sub(r"^every\s+(" + DAY + r")\s+from\s+", r"\1 ", line, flags=re.I)
        m = re.match(r"^(\d{1,2}:\d{2}\s*-\s*\d{1,2}(?::\d{2})?)\s+(" + GROUP + r")\s*$", line, re.I)
        if m:
            line = "%s %s" % (m.group(2), m.group(1))
        out.append(line)
    return " | ".join(out)


def _hours_from_norm(text):
    """hours_norm.try_convert path -> uniform Mon..Sun table or (None, reason)."""
    cleaned = _prepare_council_hours_text(text)
    conv, err = H.try_convert(cleaned)
    table = H.struct_to_hours(conv) if conv else None
    if not table:
        return None, err or "times are not a plain weekly timetable"
    out = {}
    for day in DAYS:
        if day not in table:
            continue
        cell = _uniform_cell(table[day])
        if not cell:
            return None, "times are not in the uniform day format"
        out[day] = cell
    if not any(v != "Closed" for v in out.values()):
        return None, "no times"
    return {d: out[d] for d in DAYS if d in out}, ""


def hours_table(text):
    """Feed wording -> {'Mon': '09:00 - 17:00', ...} or (None, reason). No guessed days."""
    raw = text or ""
    if not re.search(r"\d|noon|midday", raw, re.I):
        return None, "no times"
    if not re.search(r"\d\s*(?::|\.|am|pm)|\d{1,2}\s*(?:am|pm)|noon|midday", raw, re.I):
        return None, "no times"
    if HARD_SKIP.search(raw):
        return None, "times are not a plain weekly timetable (term-time or similar)"
    cleaned = _clean_hours_text(raw)
    conv, err = H.try_convert(cleaned)
    table = H.struct_to_hours(conv) if conv else None
    if not table:
        found = _pairs(cleaned)
        if not found:
            norm, nwhy = _hours_from_norm(raw)
            if norm:
                return norm, ""
            if not re.search(r"\b(?:" + DAY + r")\b", cleaned, re.I):
                return None, "no weekday stated"
            return None, nwhy or err or "times are not a plain weekly timetable"
        pieces = ["%s %s" % (days, body) for days, body in found]
        conv, err = H.try_convert(" | ".join(pieces))
        table = H.struct_to_hours(conv) if conv else None
        if not table:
            norm, nwhy = _hours_from_norm(raw)
            if norm:
                return norm, ""
            return None, nwhy or err or "times are not a plain weekly timetable"
    out = {}
    for day in DAYS:
        if day not in table:
            continue
        cell = _uniform_cell(table[day])
        if not cell:
            norm, nwhy = _hours_from_norm(raw)
            if norm:
                return norm, ""
            return None, "times are not in the uniform day format"
        out[day] = cell
    pair_table, _ = _table_from_pairs(raw)
    if pair_table:
        for day in DAYS:
            if day in pair_table:
                out[day] = pair_table[day]
    if not any(v != "Closed" for v in out.values()):
        return None, "no times"
    return {d: out[d] for d in DAYS if d in out}, ""


def _surrey_cell(cell):
    cell = re.sub(r"\s+", " ", str(cell or "").replace("\xa0", " ")).strip()
    cell = re.sub(r"\s*\([^)]*\)", "", cell).strip()
    cell = cell.replace("\u2013", "-").replace("\u2014", "-")
    cell = re.sub(r"\s+until\s+", " - ", cell, flags=re.I)
    cell = re.sub(r"\bto\b", "-", cell, flags=re.I)
    cell = re.sub(r"(\d)(am|pm)\b", r"\1 \2", cell, flags=re.I)
    cell = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", cell)
    cell = re.sub(r"(\d{1,2}:\d{2}:\d{2})", lambda m: m.group(1)[:5], cell)
    if re.search(r"\bterm[\s-]?time\b", cell, re.I):
        return None
    if not cell or re.fullmatch(r"closed", cell, re.I):
        return "Closed" if cell else None
    parts = [p.strip() for p in re.split(r"\s+and\s+", cell, flags=re.I) if p.strip()]
    norm = []
    for part in parts:
        if TIME_RE.match(part):
            norm.append(part)
            continue
        conv, _ = H.try_convert("Monday %s" % part)
        table = H.struct_to_hours(conv) if conv else None
        if table and table.get("Mon"):
            u = _uniform_cell(table["Mon"])
            if u and u != "Closed":
                norm.append(u)
                continue
        m = re.fullmatch(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", part)
        if m:
            part = "%s - %s" % (m.group(1), m.group(2))
        if not TIME_RE.match(part):
            return None
        norm.append(part)
    return " / ".join(norm)


def hours_from_day_columns(attrs, columns):
    """ArcGIS columns Monday..Sunday -> day table. attrs keys may be any case."""
    low = {str(k).lower(): v for k, v in (attrs or {}).items()}
    out = {}
    quotes = []
    for col, day in zip(columns, DAYS):
        raw = low.get(str(col).lower())
        cell = _surrey_cell(raw)
        if cell is None:
            continue
        out[day] = cell
        quotes.append("%s %s" % (day, cell))
    if not out or not any(v != "Closed" for v in out.values()):
        return None, "", "no times"
    return {d: out[d] for d in DAYS if d in out}, " | ".join(quotes), ""


def _slug(name, postcode):
    pc = re.sub(r"[^a-z0-9]", "", (postcode or "").lower())
    name = (name or "").lower().replace("’", "'").replace("@", " ")
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    name = re.sub(r"-+", "-", name)[:48].strip("-")
    return "%s-%s" % (pc, name)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _attrs(feature):
    a = feature.get("attributes") or feature.get("properties") or {}
    return {str(k).lower(): v for k, v in a.items()}


def _coords(feature, attrs):
    lat, lng = _num(attrs.get("latitude")), _num(attrs.get("longitude"))
    if lat is not None and lng is not None:
        return lat, lng
    geom = feature.get("geometry") or {}
    if "y" in geom and "x" in geom:
        return _num(geom.get("y")), _num(geom.get("x"))
    return None, None


def _http_url(raw):
    u = re.sub(r"\s+", "", str(raw or ""))
    if not u or u.lower() in ("n/a", "none"):
        return ""
    if not re.match(r"https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    return u


def _record(feed, run_day, prefix, used, oid, name, address, pc, lat, lng, table, quote, notes, website, meta=None):
    sid = "%s-%s" % (prefix, _slug(name, pc))
    if sid in used:
        sid = "%s-%s" % (sid, oid if oid is not None else len(used))
    used.add(sid)
    row = {
        "id": sid,
        "name": name,
        "address": address,
        "postcode": pc,
        "lat": lat,
        "lng": lng,
        "phone": "",
        "website": website,
        "hours": table,
        "hours_quote": quote,
        "provided": [],
        "booking": "Not stated",
        "notes": notes[:240],
        "scheme_end": "",
        "scheme_dates": "Not stated by source",
        "ended": False,
        "source": feed.get("source") or "Council warm spaces",
        "source_url": feed.get("url") or "",
        "last_verified": run_day,
        "stale": False,
        "arcgis_objectid": oid,
    }
    if meta:
        row.update(meta)
    return row


def _parse_brighton(features, feed, run_day, kept, skipped, used):
    source = feed.get("source") or "Council warm spaces"
    website = feed.get("website") or ""
    prefix = (feed.get("id_prefix") or "bh").strip("-")
    for feature in features or []:
        a = _attrs(feature)
        name = re.sub(r"\s+", " ", str(a.get("venue") or a.get("name") or "")).strip()
        pc = _postcode(str(a.get("postcode") or ""))
        oid = a.get("objectid")
        label = name or ("object %s" % oid)
        if not name:
            skipped.append({"objectid": oid, "name": label, "reason": "no venue name"})
            continue
        if not pc:
            skipped.append({"objectid": oid, "name": name, "reason": "no postcode"})
            continue
        hours_raw = str(a.get("hours_of_access__opening_hours") or a.get("hours") or "").strip()
        table, why = hours_table(hours_raw)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        quote = re.sub(r"\s+", " ", hours_raw).strip()
        notes = source
        if a.get("category"):
            notes += " (" + re.sub(r"\s+", " ", str(a["category"])).strip() + ")"
        low_hours = hours_raw.lower()
        unnamed = [d for d, w in zip(DAYS, ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))
                   if d not in table and re.search(r"\b" + w[:3], low_hours)]
        if unnamed:
            notes += " Some days named in the feed had no clear clock time, so they are not shown."
        if why:
            notes += ". " + why
        kept.append(_record(feed, run_day, prefix, used, oid, name,
                            _clean_address(str(a.get("address") or "")), pc, lat, lng,
                            table, quote, notes, website))


def _cherwell_rows(attrs):
    keys = ("event_name", "opening_days", "opening_times")
    split = {k: re.split(r"\r?\n", str(attrs.get(k) or "")) for k in keys}
    n = max((len(split[k]) for k in keys), default=1)
    rows = []
    for i in range(n):
        rows.append({k: (split[k][i] if i < len(split[k]) else "").strip() for k in keys})
    return rows


def _cherwell_pick(attrs):
    rows = _cherwell_rows(attrs)
    if not rows:
        return None
    for row in rows:
        if WARM_ACTIVITY.search(row.get("event_name") or ""):
            return row
    if len(rows) == 1:
        return rows[0]
    addr = str(attrs.get("address") or "").lower()
    org = str(attrs.get("organisation") or "").lower()
    if "cornhill" in addr and "voluntary" in org:
        return rows[0]
    return None


def _cherwell_name(attrs, row):
    org = re.sub(r"\s+", " ", str(attrs.get("organisation") or "")).strip()
    ev = re.sub(r"\s+", " ", str(row.get("event_name") or "")).strip()
    addr = str(attrs.get("address") or "").lower()
    if "cornhill" in addr and "voluntary" in org.lower():
        return "Royal Voluntary Service Café, Cornhill Centre"
    if "highmarket" in addr and WARM_ACTIVITY.search(ev):
        return "Warm Welcome at Highmarket House"
    if WARM_ACTIVITY.search(ev):
        return ev if len(ev) > 8 else ("Warm Welcome at %s" % org if org else ev)
    return ev or org


def _parse_lancashire(features, feed, run_day, kept, skipped, used):
    prefix = (feed.get("id_prefix") or "lancs").strip("-")
    for feature in features or []:
        a = _attrs(feature)
        if str(a.get("orgapproved") or "").lower() != "yes":
            skipped.append({"objectid": a.get("objectid"), "name": a.get("orgname"), "reason": "not OrgApproved"})
            continue
        if feed.get("require_current_season") and not record_current_for_season(a, feed, run_day):
            skipped.append({"objectid": a.get("objectid"), "name": a.get("orgname"), "postcode": _postcode(str(a.get("orgaddress") or "")),
                            "reason": LANCS_HOLD_REASON})
            continue
        name = re.sub(r"\s+", " ", str(a.get("orgname") or "")).strip()
        addr = _clean_address(str(a.get("orgaddress") or ""))
        pc = _postcode(addr) or _postcode(str(a.get("postcode") or ""))
        oid = a.get("objectid")
        if not name:
            skipped.append({"objectid": oid, "name": "object %s" % oid, "reason": "no venue name"})
            continue
        if not pc:
            skipped.append({"objectid": oid, "name": name, "reason": "no postcode"})
            continue
        hours_raw = str(a.get("orgopentimes") or "").strip()
        table, why = hours_table(hours_raw)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        share = str(a.get("orgcontactshare") or "").strip()
        tel = _clean_phone(a.get("orgtelephone"))
        meta = {}
        if tel and share in ("Both", "Telephone number"):
            meta["_feed_phone"] = tel
            meta["_feed_phone_source"] = feed.get("url") or ""
        site = _feed_website(a.get("orgwebsite"), feed)
        quote = re.sub(r"\s+", " ", hours_raw).strip()
        notes = feed.get("source") or "Lancashire warm spaces"
        kept.append(_record(feed, run_day, prefix, used, oid, name, addr, pc, lat, lng, table, quote, notes, site, meta))


def _parse_surrey(features, feed, run_day, kept, skipped, used):
    prefix = (feed.get("id_prefix") or "surrey").strip("-")
    cols = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for feature in features or []:
        a = _attrs(feature)
        name = re.sub(r"\s+", " ", str(a.get("warm_welcome") or a.get("organisation") or "")).strip()
        addr = _clean_address(str(a.get("address") or ""))
        pc = _postcode(addr)
        oid = a.get("objectid")
        if not name:
            skipped.append({"objectid": oid, "name": "object %s" % oid, "reason": "no venue name"})
            continue
        if not pc:
            skipped.append({"objectid": oid, "name": name, "reason": "no postcode"})
            continue
        table, quote, why = hours_from_day_columns(a, cols)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        notes = feed.get("source") or "Surrey warm welcome"
        site = _http_url(a.get("library_accessibility_webpage")) or feed.get("website") or ""
        meta = {"_venue_page": site} if site else {}
        kept.append(_record(feed, run_day, prefix, used, oid, name, addr, pc, lat, lng, table, quote, notes,
                            feed.get("website") or site, meta))


def _parse_cherwell(features, feed, run_day, kept, skipped, used):
    prefix = (feed.get("id_prefix") or "cherwell").strip("-")
    for feature in features or []:
        a = _attrs(feature)
        row = _cherwell_pick(a)
        if not row:
            skipped.append({"objectid": a.get("objectid"), "name": a.get("event_name"), "reason": "no warm welcome / warm space row"})
            continue
        name = _cherwell_name(a, row)
        addr = _clean_address(str(a.get("address") or ""))
        pc = _postcode(addr)
        oid = a.get("objectid")
        times = str(row.get("opening_times") or "").strip()
        if re.search(r"check\s+website", times, re.I):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "hours say check website"})
            continue
        hours_raw = ("%s %s" % (row.get("opening_days") or "", times)).strip()
        table, why = hours_table(hours_raw)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        site = _feed_website(a.get("website"), feed)
        quote = re.sub(r"\s+", " ", hours_raw).strip()
        meta = {"_venue_page": site} if site else {}
        tel = _clean_phone(a.get("telephone"))
        if tel and "still waters" not in name.lower():
            meta["_feed_phone"] = tel
            meta["_feed_phone_source"] = feed.get("url") or ""
        elif tel and "still waters" in name.lower():
            meta["_hold_phone"] = True
        kept.append(_record(feed, run_day, prefix, used, oid, name, addr, pc, lat, lng, table, quote,
                            feed.get("source") or "Cherwell warm spaces", site, meta))


def _parse_northumberland(features, feed, run_day, kept, skipped, used):
    prefix = (feed.get("id_prefix") or "nland").strip("-")
    consent = "do_you_give_permission_to_share_your_details_on_the_northumberland_county_council_website_which_includes_the_details_on_a_map_"
    for feature in features or []:
        a = _attrs(feature)
        if str(a.get(consent) or "").lower() != "yes":
            skipped.append({"objectid": a.get("objectid"), "name": a.get("space_or_place_name"), "reason": "no website consent"})
            continue
        name = re.sub(r"\s+", " ", str(a.get("space_or_place_name") or "")).strip()
        addr = _clean_address(str(a.get("address") or ""))
        pc = _postcode(str(a.get("postcode") or "")) or _postcode(addr)
        oid = a.get("objectid")
        hours_raw = str(a.get("opening_times") or "").strip()
        table, why = hours_table(hours_raw)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        quote = re.sub(r"\s+", " ", hours_raw).strip()
        kept.append(_record(feed, run_day, prefix, used, oid, name, addr, pc, lat, lng, table, quote,
                            feed.get("source") or "Northumberland warm spaces", feed.get("website") or ""))


def _tower_hamlets_page(name):
    n = (name or "").strip().lower()
    if not n:
        return ""
    slug = n.replace("idea store ", "idea-store-")
    slug = re.sub(r"\s+library$", "-library", slug)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return "https://www.ideastore.co.uk/visit-us/%s" % slug


def _parse_tower_hamlets(features, feed, run_day, kept, skipped, used):
    prefix = (feed.get("id_prefix") or "th").strip("-")
    for feature in features or []:
        a = _attrs(feature)
        name = re.sub(r"\s+", " ", str(a.get("organisation_name") or "")).strip()
        addr = re.sub(r"\s+", " ", str(a.get("organisation_address") or "")).strip()
        pc = _postcode(addr)
        oid = a.get("objectid")
        hours_raw = str(a.get("openinghours") or "").strip()
        table, why = hours_table(hours_raw)
        if not table:
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": why or "no times"})
            continue
        lat, lng = _coords(feature, a)
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        site = _http_url(a.get("website")) or feed.get("website") or ""
        venue = _tower_hamlets_page(name) or site
        quote = re.sub(r"\s+", " ", hours_raw).strip()
        meta = {"_venue_page": venue} if venue else {}
        kept.append(_record(feed, run_day, prefix, used, oid, name, addr, pc, lat, lng, table, quote,
                            feed.get("source") or "Tower Hamlets warm hubs", venue or site, meta))


PARSERS = {
    "brighton": _parse_brighton,
    "lancashire": _parse_lancashire,
    "surrey": _parse_surrey,
    "cherwell": _parse_cherwell,
    "northumberland": _parse_northumberland,
    "tower-hamlets": _parse_tower_hamlets,
}


def parse_features(features, feed, run_day):
    """Return (records, skipped). records carry a provisional stable id; dedupe may replace it."""
    kept, skipped, used = [], [], set()
    parser = PARSERS.get((feed.get("format") or "brighton").lower(), _parse_brighton)
    parser(features, feed, run_day, kept, skipped, used)
    return kept, skipped


def choose_existing_id(record, candidates):
    """Prefer an exact postcode match, then the lowest id, so a refresh does not mint a second id."""
    hits = [c for c in candidates if same_place(record, c)]
    if not hits:
        return None
    exact = [c for c in hits if _pc_key(c.get("postcode")) == _pc_key(record.get("postcode"))]
    pool = exact or hits
    return sorted(pool, key=lambda c: str(c.get("id") or ""))[0]["id"]


def dedupe(records, existing):
    """existing: list of {id, name, postcode} from the Warm Welcome list and the pending log.
    Returns (records with stable ids, skipped duplicates inside this feed)."""
    catalog = list(existing or [])
    out, skipped = [], []
    for rec in records:
        eid = choose_existing_id(rec, catalog)
        if eid and any(r["id"] == eid for r in out):
            skipped.append({"objectid": rec.get("arcgis_objectid"), "name": rec["name"], "postcode": rec["postcode"],
                            "reason": "duplicate of %s" % eid})
            continue
        if eid:
            rec = dict(rec, id=eid)
        elif any(same_place(rec, r) for r in out):
            skipped.append({"objectid": rec.get("arcgis_objectid"), "name": rec["name"], "postcode": rec["postcode"],
                            "reason": "duplicate in this feed"})
            continue
        out.append(rec)
        catalog.append({"id": rec["id"], "name": rec["name"], "postcode": rec["postcode"]})
    return out, skipped


def evidence(record, feed):
    quote = record.get("hours_quote") or ""
    return {
        "name": record["name"],
        "evidence_url": feed.get("url") or record.get("source_url") or "",
        "evidence_name": feed.get("evidence_name") or feed.get("source") or "Council",
        "quote": quote,
        "day_time_quote": quote,
        "verified_on": record.get("last_verified") or "",
        "bar": "Council ArcGIS warm-space feed states the weekday and time (Dean 21 Oct evidence rule; blanket approval 30 Oct 2026).",
    }


def approval_note(feed, run_day):
    return ("Dean blanket approval 30 Oct 2026 for verified places from their own official source; "
            "%s warm-space feed, checked %s." % (feed.get("council") or feed.get("source") or "Council", run_day))


def merge_records(fresh, records):
    """Put feed rows on the warm-space list. An id already there keeps its phone and council lines; times come from the feed."""
    by_id = {x["id"]: x for x in fresh}
    added = []
    dont_blank = {"provided", "sign_url", "groups", "checked_on", "tier", "verified", "sign_url"}
    for rec in records:
        cur = by_id.get(rec["id"])
        fields = ("name", "address", "postcode", "lat", "lng", "hours", "website", "notes", "source", "source_url",
                  "booking", "scheme_end", "scheme_dates", "ended", "last_verified")
        if cur is None:
            row = {k: v for k, v in rec.items() if k not in ("hours_quote", "arcgis_objectid") and not str(k).startswith("_")}
            fresh.append(row)
            by_id[row["id"]] = row
            added.append(row["id"])
            continue
        for k in fields:
            if cur["id"].startswith("ww-") and rec.get("source_url") and "arcgis" in str(rec.get("source_url")):
                if k in ("source", "source_url", "notes", "booking"):
                    continue
            if k == "website" and cur.get("website"):
                continue
            if k in rec and rec[k] not in (None, ""):
                cur[k] = rec[k]
        for k in dont_blank:
            val = rec.get(k)
            if val in (None, "", []) and cur.get(k) not in (None, "", []):
                continue
            if k in rec and rec[k] not in (None, ""):
                cur[k] = rec[k]
        added.append(cur["id"])
    return added


def read_feed(feed, getter, run_day, existing):
    features = fetch_features(feed["url"], getter)
    records, skipped = parse_features(features, feed, run_day)
    records, dupes = dedupe(records, existing)
    return records, skipped + dupes


def pending_rows(path):
    if not path or not os.path.exists(path):
        return []
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("items") or data.get("pending") or []
    return [p for p in data if isinstance(p, dict) and p.get("id")]


def merge_into(fresh, run_day, config_path=None, pending_path=None, getter=None):
    """Fetch every configured feed and merge it into fresh. Returns (added ids, skipped, status)."""
    from common import get
    getter = getter or get
    feeds = load_config(config_path)
    pending = pending_rows(pending_path)
    existing = [{"id": x.get("id"), "name": x.get("name"), "postcode": x.get("postcode")} for x in fresh]
    existing += [{"id": p.get("id"), "name": p.get("name"), "postcode": p.get("postcode")} for p in pending]
    added, skipped, failed = [], [], []
    for feed in feeds:
        try:
            records, skip = read_feed(feed, getter, run_day, existing)
        except Exception as ex:
            failed.append({"id": feed.get("id"), "error": str(ex)[:180]})
            continue
        for rec in records:
            existing.append({"id": rec["id"], "name": rec["name"], "postcode": rec["postcode"]})
        added += merge_records(fresh, records)
        skipped += [dict(s, feed=feed.get("id")) for s in skip]
    status = {"status": "ok" if not failed else "partial", "feeds": len(feeds), "added": len(added),
              "ids": added, "skipped": skipped, "failed": failed}
    if failed and not added:
        status["status"] = "failed: " + "; ".join(f["error"] for f in failed)
    lancs_held = [s for s in skipped if s.get("reason") == LANCS_HOLD_REASON]
    if lancs_held:
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        seen, uniq = set(), []
        for s in lancs_held:
            key = s.get("objectid") or (s.get("name"), s.get("postcode"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(s)
        json.dump(uniq, open(os.path.join(ROOT, "logs", "arcgis_lancs_pending.json"), "w"), indent=1, ensure_ascii=False)
    return added, skipped, status
