"""Council ArcGIS FeatureServer warm-space feeds.

overrides/arcgis_warmspaces.json lists query URLs. Each refresh reads the feed, keeps times from it,
and skips a record with no postcode or no times that can be shown as a Mon–Sun table. Ids stay stable:
a place already on the Warm Welcome list or in logs/warmspaces_pending.json keeps that id. A new place
keeps an id from its name and postcode, not from the row order.

Phone and council-line fields are never set here.
"""
import json, os, re
import hours_norm as H

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
            if not re.search(r"\b(?:" + DAY + r")\b", cleaned, re.I):
                return None, "no weekday stated"
            return None, err or "times are not a plain weekly timetable"
        pieces = ["%s %s" % (days, body) for days, body in found]
        conv, err = H.try_convert(" | ".join(pieces))
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


def parse_features(features, feed, run_day):
    """Return (records, skipped). records carry a provisional stable id; dedupe may replace it."""
    prefix = (feed.get("id_prefix") or "bh").strip("-")
    source = feed.get("source") or "Council warm spaces"
    url = feed.get("url") or ""
    website = feed.get("website") or ""
    kept, skipped, used = [], [], set()
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
        lat, lng = _num(a.get("latitude")), _num(a.get("longitude"))
        if lat is None or lng is None or not (49.8 <= lat <= 61 and -8.7 <= lng <= 2):
            skipped.append({"objectid": oid, "name": name, "postcode": pc, "reason": "no UK coordinates"})
            continue
        sid = "%s-%s" % (prefix, _slug(name, pc))
        if sid in used:
            sid = "%s-%s" % (sid, oid if oid is not None else len(used))
        used.add(sid)
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
        kept.append({
            "id": sid,
            "name": name,
            "address": re.sub(r"\s+", " ", str(a.get("address") or "")).strip(),
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
            "source": source,
            "source_url": url,
            "last_verified": run_day,
            "stale": False,
            "arcgis_objectid": oid,
        })
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
    for rec in records:
        cur = by_id.get(rec["id"])
        fields = ("name", "address", "postcode", "lat", "lng", "hours", "website", "notes", "source", "source_url",
                  "booking", "provided", "scheme_end", "scheme_dates", "ended", "last_verified")
        if cur is None:
            row = {k: v for k, v in rec.items() if k not in ("hours_quote", "arcgis_objectid")}
            fresh.append(row)
            by_id[row["id"]] = row
            added.append(row["id"])
            continue
        for k in fields:
            if k == "website" and cur.get("website"):
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
    return added, skipped, status
