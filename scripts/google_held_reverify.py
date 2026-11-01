#!/usr/bin/env python3
"""Re-verify held Google rows that failed only on auto-A gate or missing phone/postcode."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import google_serper_verify_town as gv  # noqa: E402
from google_shelter_dedupe import build_index, norm_url  # noqa: E402

TARGET_REASONS = {
    "auto-A disabled (strict manual A only)",
    "auto-A disabled (strict manual A only); no verbatim phone",
    "auto-A disabled (strict manual A only); no postcode",
}

SUPPORTED_ONLY = re.compile(
    r"\b(supported housing|supported accommodation|move[\s-]on (?:only|accommodation)|"
    r"general needs supported|floating support only|tenancy ready)\b",
    re.I,
)
EMERGENCY = re.compile(
    r"\b(hostel|night shelter|nightstop|night stop|emergency bed|emergency accommodation|"
    r"rough sleep|swep|direct access|sit[\s-]up|day centre|day center|foyer|16[\s\-–to]{1,3}25)\b",
    re.I,
)
COUNCIL_ADVICE = re.compile(
    r"\b(housing options|homelessness advice|if you are homeless contact|"
    r"preventing homelessness)\b",
    re.I,
)
NAMED_SERVICE = re.compile(
    r"\b(hostel|night shelter|day centre|day center|foyer|nightstop|lifehouse|emergency accommodation)\b",
    re.I,
)
REFERRAL = re.compile(
    r"\b(referral|refer you|self[\s-]refer|housing options|contact us|call us|drop[\s-]in)\b",
    re.I,
)
BAD_HOST = re.compile(
    r"(independenthostels\.co\.uk|alzheimers\.org\.uk|ageuk\.org\.uk|thejoyapp\.com|"
    r"refernet\.|indeed\.|carehome\.co\.uk|crash\.org\.uk/our-work|/news/|"
    r"christmas-food|other-agencies|adultcare\.|how-to-find-suitable|"
    r"sanctuary-supported-living\.co\.uk/support-se|livewell\.|1space\.|"
    r"connecttosupportsurrey\.org\.uk|familysupportni\.gov\.uk/Service/|"
    r"lewishamfamilyhubs\.org\.uk|fleetphoenix\.co\.uk/useful-contacts|"
    r"lichfielddc\.gov\.uk/homelessness/concerned|yourspaceonline\.net|"
    r"dioceseofstasaph\.org\.uk/.*/churches-to-open|thamesreach\.org\.uk/\d{4}/|"
    r"adullam\.org\.uk/\d{4}/|casws\.org\.uk/hidden-homelessness)",
    re.I,
)
NEWS_PATH = re.compile(r"/\d{4}/\d{2}/|set-to-open|opens-for-|news/", re.I)
HOSTEL_WORD = re.compile(
    r"\b(hostel|night shelter|nightstop|lifehouse|emergency accommodation|direct access bed)\b",
    re.I,
)
DAY_CENTRE_WORD = re.compile(r"\b(day centre|day center|drop[\s-]in)\b", re.I)
YOUTH_WORD = re.compile(
    r"\b(nightstop|night stop|foyer|16[\s\-–to]{1,3}25|young people.{0,30}(homeless|housing))\b",
    re.I,
)
HOMELESS_CTX = re.compile(
    r"\b(homeless|rough sleep|rough sleeper|vulnerably housed|street homeless|"
    r"no fixed abode|people sleeping rough)\b",
    re.I,
)
TEL_LINK = re.compile(r'href=["\']tel:([^"\']+)', re.I)


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if d.startswith("44") and len(d) > 10:
        d = "0" + d[2:]
    return d


def norm_name(n):
    return re.sub(r"[^a-z0-9]+", " ", (n or "").lower()).strip()


def build_rich_index():
    idx = build_index()
    phones = set()
    postcodes = set()
    import google_shelter_dedupe as gd

    live = gd.load_live()
    manual = gd.load_manual()
    chains = set()
    for src in live + manual:
        ph = norm_phone(src.get("phone") or "")
        if len(ph) >= 10:
            phones.add(ph)
        pc = (src.get("postcode") or "").upper().replace(" ", "")
        if pc:
            postcodes.add(pc)
        n = norm_name(src.get("name"))
        if n:
            idx["names"].add(n)
        w = norm_url(src.get("website"))
        if w:
            idx["urls"].add(w)
        op = (src.get("operator") or "").lower()
        if "salvation army" in op or "salvationarmy.org.uk" in w:
            chains.add("salvation_army")
    idx["phones"] = phones
    idx["postcodes"] = postcodes
    idx["chains"] = chains
    return idx


def load_live_manual_items():
    import google_shelter_dedupe as gd

    return gd.load_live() + gd.load_manual()


def is_duplicate(row, url, name, phone, postcode, index):
    if norm_url(url) in index["urls"]:
        return "duplicate URL"
    n = norm_name(name)
    if n and n in index["names"]:
        return "duplicate name"
    ph = norm_phone(phone)
    if ph and ph in index.get("phones", set()):
        return "duplicate phone"
    pc = (postcode or "").upper().replace(" ", "")
    if pc and pc in index.get("postcodes", set()):
        return "duplicate postcode"
    host = urllib.parse.urlparse(url).netloc.lower()
    if "salvationarmy.org.uk" in host and "salvation_army" in index.get("chains", set()):
        if re.search(r"lifehouse|night shelter", url, re.I):
            return "Salvation Army chain already listed"
    return ""


def extract_phones(raw_html, text):
    found = []
    for m in TEL_LINK.finditer(raw_html or ""):
        found.append(urllib.parse.unquote(m.group(1)))
    for m in gv.PHONE.finditer(text.replace("\u00a0", " ")):
        found.append(m.group(0))
    # de-dupe by normalized
    out = []
    seen = set()
    for p in found:
        n = norm_phone(p)
        if len(n) >= 10 and n not in seen:
            seen.add(n)
            out.append(re.sub(r"\s+", " ", p.strip()))
    return out


def extract_postcodes(text):
    pcs = []
    for m in gv.POSTCODE.finditer(text):
        pc = m.group(1).upper().replace("  ", " ")
        if not gv.FAKE_PC.match(pc.replace(" ", "")):
            pcs.append(pc)
    return pcs


def name_on_page(name, text):
    nt = [t for t in norm_name(name).split() if len(t) > 3]
    if not nt:
        nt = norm_name(name).split()
    blob = text.lower()
    hits = sum(1 for t in nt if t in blob)
    return hits >= max(1, len(nt) // 2)


def detect_kind(text, name):
    blob = f"{name} {text}"
    if re.search(r"nightstop|night stop", blob, re.I):
        return "young_people"
    if re.search(r"foyer|16[\s\-–to]{1,3}25|young people.{0,40}homeless", blob, re.I):
        return "young_people"
    if re.search(r"day centre|day center|daytime drop|drop[\s-]in centre", blob, re.I):
        return "day_centre"
    return "hostel"


def detect_season(kind, text):
    if kind == "day_centre":
        return "Daytime only"
    if re.search(r"swep|severe weather|winter only|nov.*mar", text, re.I):
        return "SWEP (severe weather only)" if "swep" in text.lower() else "Winter-only"
    return "Year-round"


def detect_access(text):
    low = text.lower()
    if "self-refer" in low or "self refer" in low or "no referral" in low:
        return "self_referral", "Self-referral"
    if "drop in" in low or "drop-in" in low:
        return "open_access", "Drop in"
    if REFERRAL.search(text):
        return "referral_only", "Referral via council or agencies (see operator page)"
    return "not_stated", "Not stated"


def geocode(postcode):
    if not postcode:
        return 0.0, 0.0
    q = urllib.parse.quote(postcode.replace(" ", ""))
    try:
        data = json.loads(
            urllib.request.urlopen(
                f"https://api.postcodes.io/postcodes/{q}", timeout=15
            ).read()
        )
        if data.get("status") == 200:
            r = data["result"]
            return r["latitude"], r["longitude"]
    except Exception:
        pass
    return 0.0, 0.0


def fetch_raw(url):
    gv.FETCH.mkdir(parents=True, exist_ok=True)
    import hashlib

    h = hashlib.md5(url.encode()).hexdigest()[:12]
    fp = gv.FETCH / f"{h}.html"
    raw = b""
    if fp.exists() and fp.stat().st_size > 400:
        raw = fp.read_bytes()
    else:
        try:
            r = subprocess.run(
                ["curl", "-fsSL", "-A", "helpmap-verify/1.0", "-L", "--max-time", "25", url],
                capture_output=True,
                timeout=30,
            )
            if r.returncode != 0:
                return None, None
            raw = r.stdout
            fp.write_bytes(raw)
        except (subprocess.TimeoutExpired, OSError):
            return None, None
    text = gv.strip_html(raw.decode("utf-8", errors="replace"))
    return raw.decode("utf-8", errors="replace"), text


def grade_row(row, index, a_ids):
    url = (row.get("url") or "").split("#")[0].strip()
    name = (row.get("name") or "").strip()
    town = row.get("town") or ""
    if gv.BAD_LINK.search(url) or BAD_HOST.search(url) or NEWS_PATH.search(url):
        return None, "directory or blocked URL pattern"
    raw, text = fetch_raw(url)
    if text is None:
        return None, "Fetch failed or blocked"
    if gv.EXCLUDE.search(text) or gv.CLOSED.search(text):
        return None, "excluded type or closed"
    if gv.REJECT_TEXT.search(text) or gv.REJECT_TEXT.search(name):
        return None, "not an accommodation operator page"
    if SUPPORTED_ONLY.search(text) and not EMERGENCY.search(text):
        return None, "general adult supported housing only"
    if not EMERGENCY.search(text):
        return None, "not a hostel/night shelter/day centre service page"
    if COUNCIL_ADVICE.search(text) and not NAMED_SERVICE.search(text):
        return None, "Council advice page only; no named service"
    if not name_on_page(name, text):
        return None, "service name not confirmed on page"

    phones = extract_phones(raw, text)
    if not phones:
        return None, "no verbatim phone"
    phone = phones[0]
    postcodes = extract_postcodes(text)
    postcode = postcodes[0] if postcodes else ""

    referral_text = "Not stated"
    access_type = "not_stated"
    card_type = None
    no_pin = False
    lat, lng = 0.0, 0.0
    address = ""

    if postcodes:
        lat, lng = geocode(postcodes[0])
        address = ""  # optional extract — leave blank if not clear
        postcode = postcodes[0]
    else:
        acc, referral_text = detect_access(text)
        access_type = acc
        if REFERRAL.search(text) and phone:
            card_type = "referral_hostel"
            no_pin = True
            postcode = ""
            lat = lng = None
        else:
            return None, "no postcode and no referral route for town card"

    dup = is_duplicate(row, url, name, phone, postcode, index)
    if dup:
        return None, dup

    kind = detect_kind(text, name)
    if kind == "day_centre" and not HOMELESS_CTX.search(text):
        return None, "day centre without homeless context"
    if kind == "hostel" and not HOSTEL_WORD.search(text):
        return None, "hostel without hostel/night shelter wording on page"
    if kind == "day_centre" and not DAY_CENTRE_WORD.search(text):
        return None, "day centre without day centre/drop-in wording on page"
    if kind == "young_people" and not YOUTH_WORD.search(text):
        return None, "young people without foyer/nightstop/16-25 wording on page"
    access_type, ref = detect_access(text)
    if referral_text == "Not stated":
        referral_text = ref

    slug = gv.slug(name)
    eid = f"man-google-{slug}"
    n = 2
    while eid in a_ids:
        eid = f"man-google-{slug}-{n}"
        n += 1
    entry = {
        "id": eid,
        "name": name[:120],
        "address": address,
        "postcode": postcode,
        "lat": lat,
        "lng": lng,
        "phone": phone,
        "website": url,
        "hours": "Not stated",
        "referral": referral_text[:500],
        "beds": "",
        "groups": [],
        "season": detect_season(kind, text),
        "operator": "",
        "flag_closed": False,
        "source": "Manual Google Serper Nov 2026",
        "source_url": url,
        "last_verified": "2026-11-01",
        "stale": False,
        "access_type": access_type,
        "facilities": "Not stated",
        "checked_on": "2026-11-01",
        "kind": kind,
        "who_for": "Not stated",
        "wheelchair": "Not stated",
        "last_checked": "2026-11-01",
        "town": town,
    }
    if card_type:
        entry["card_type"] = card_type
        entry["no_pin"] = True
        entry["town"] = town
        entry["area"] = town

    # quote for verified json
    idx = text.lower().find(phone[:6].replace(" ", ""))
    quote = text[max(0, idx - 80) : idx + 120] if idx >= 0 else text[:200]
    entry["_quote"] = quote.strip()
    entry["_evidence_name"] = urllib.parse.urlparse(url).netloc.replace("www.", "")
    return entry, ""


def spot_check(entries, n=20):
    import random

    random.seed(20261101)
    sample = random.sample(entries, min(n, len(entries)))
    fails = []
    for e in sample:
        why = _validate_entry(e)
        if why:
            fails.append((e["id"], why))
    return sample, fails


def _validate_entry(e):
    """Inline strict validate (shared with google_a_strict_regrade)."""
    url = e.get("source_url") or e.get("website") or ""
    if BAD_HOST.search(url) or NEWS_PATH.search(url):
        return "bad URL host/path"
    raw, text = fetch_raw(url)
    if not text:
        return "fetch failed"
    if gv.EXCLUDE.search(text) or gv.CLOSED.search(text):
        return "excluded or closed"
    if e.get("kind") == "day_centre" and not HOMELESS_CTX.search(text):
        return "day centre without homeless context"
    if e.get("kind") == "hostel" and not HOSTEL_WORD.search(text):
        return "hostel without hostel wording"
    if e.get("kind") == "day_centre" and not DAY_CENTRE_WORD.search(text):
        return "day centre without day centre/drop-in wording"
    if e.get("kind") == "young_people" and not YOUTH_WORD.search(text):
        return "young people without foyer/nightstop wording"
    if not name_on_page(e.get("name") or "", text):
        return "name not on page"
    phs = extract_phones(raw, text)
    want = norm_phone(e.get("phone"))
    if not want or "%" in (e.get("phone") or ""):
        return "invalid phone"
    if not any(norm_phone(p) == want for p in phs):
        return "phone not on page"
    if e.get("postcode"):
        pc = e["postcode"].replace(" ", "").upper()
        if pc not in text.upper().replace(" ", ""):
            return "postcode not on page"
    return ""


def main():
    held = json.load(open(ROOT / "held_google.json", encoding="utf-8"))["held"]
    targets = [r for r in held if r.get("reason") in TARGET_REASONS]
    print(f"Re-verify targets: {len(targets)}", file=sys.stderr)

    index = build_rich_index()
    a_items = json.load(open(ROOT / "logs" / "google_a_items.json", encoding="utf-8"))
    a_ids = {x["id"] for x in a_items}
    promoted = []
    still_b = []
    b_reasons = Counter()

    for i, row in enumerate(targets):
        entry, why = grade_row(row, index, a_ids)
        if entry:
            if entry["id"] in a_ids:
                still_b.append({**row, "reason": "duplicate id after reverify"})
                continue
            a_ids.add(entry["id"])
            index["urls"].add(norm_url(entry["website"]))
            index["names"].add(norm_name(entry["name"]))
            ph = norm_phone(entry.get("phone"))
            if ph:
                index.setdefault("phones", set()).add(ph)
            pc = (entry.get("postcode") or "").replace(" ", "")
            if pc:
                index.setdefault("postcodes", set()).add(pc)
            promoted.append(entry)
            if (i + 1) % 50 == 0:
                print(f"  processed {i+1}/{len(targets)}, A={len(promoted)}", file=sys.stderr)
        else:
            still_b.append({**row, "reason": why or "failed reverify"})
            b_reasons[why or "failed"] += 1

    # merge held: remove targets from held, add still_b for targets, keep others
    target_keys = {(r["town"], r.get("url")) for r in targets}
    other = [r for r in held if (r["town"], r.get("url")) not in target_keys]
    new_held = other + still_b

    # spot check
    sample, fails = spot_check(promoted, 20)
    if fails:
        print("SPOT CHECK FAILURES:", fails, file=sys.stderr)
        bad_ids = {f[0] for f in fails}
        promoted = [e for e in promoted if e["id"] not in bad_ids]
        for e in list(promoted):
            pass
        # demote failed spot checks back to held
        for fid, freason in fails:
            pe = next((x for x in promoted if x["id"] == fid), None)
            if pe:
                promoted.remove(pe)
                new_held.append(
                    {
                        "town": pe.get("town") or "",
                        "url": pe.get("source_url"),
                        "name": pe.get("name"),
                        "reason": f"spot-check failed: {freason}",
                    }
                )

    clean_a = []
    for e in promoted:
        c = {k: v for k, v in e.items() if not k.startswith("_")}
        clean_a.append(c)

    # extend existing A (keep nightstop)
    existing = json.load(open(ROOT / "logs/google_a_items.json", encoding="utf-8"))
    exist_ids = {x["id"] for x in existing}
    for c in clean_a:
        if c["id"] not in exist_ids:
            existing.append(c)
            exist_ids.add(c["id"])

    gv.save_a(existing)
    gv.save_held(new_held)

    out = {
        "promoted": len(clean_a),
        "by_kind": Counter(c["kind"] for c in clean_a),
        "b_reasons": dict(b_reasons.most_common(30)),
        "held_total": len(new_held),
        "spot_check_fails": fails,
    }
    (ROOT / "logs" / "google_held_reverify.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
