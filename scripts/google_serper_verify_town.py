#!/usr/bin/env python3
"""Strict A/B verify one town from google_serper_state.json organic results."""
import hashlib
import json
import re
import subprocess
import html as htmlmod
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "logs" / "google_fetch" / "batch3"
A_FILE = ROOT / "logs" / "google_a_items.json"
B_FILE = ROOT / "held_google.json"

BAD_LINK = re.compile(
    r"(homeless\.org\.uk|homelessuk\.org|communitydirectory|find-help|"
    r"thepavement\.org\.uk|housingjustice\.org\.uk|/news/|\.pdf$|"
    r"indeed\.|researchgate\.|wikipedia\.|citizensadvice\.|shelter\.org\.uk|"
    r"salvationarmy\.org\.uk/support-those|salvationarmy\.org\.uk/homelessness/night|"
    r"homelessnessimpact\.org|simplyconnect|moderngov|carehome\.co\.uk|"
    r"livewell\.|1space\.|turn2us\.org|neighbourly\.com|refernet\.co\.uk|"
    r"thebestof\.co\.uk|foodbank\.|safeguarding|homelesshostelstaff\.|"
    r"gov\.uk/.*/(rough-sleep|homeless|hostel|night-shelter|housing-advice))",
    re.I,
)
REJECT_TEXT = re.compile(
    r"(staffing agency|recruitment|concierge staff|we supply staff|"
    r"foodbank|safeguarding adults board|business guide|refernet|"
    r"elderly day care|dementia day|residential care home)",
    re.I,
)
CLOSED = re.compile(
    r"\b(closed permanently|has closed|no longer open|we are closed|service closed|"
    r"closed until further|not currently accepting)\b",
    re.I,
)
EXCLUDE = re.compile(
    r"\b(women'?s refuge|refuge for women|approved premises|probation hostel|"
    r"bail hostel)\b",
    re.I,
)
PHONE = re.compile(
    r"(?<!\d)(?:0\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}|0800[\s\-]?\d{3}[\s\-]?\d{4})(?!\d)"
)
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b", re.I)
SERVICE = re.compile(
    r"\b(hostel|night shelter|nightstop|night stop|day centre|day center|"
    r"emergency accommodation|rough sleep|homeless project)\b",
    re.I,
)
FAKE_PC = re.compile(r"^[a-f0-9]{6}$|^[a-zA-Z0-9]{6}$", re.I)


def strip_html(raw):
    raw = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", htmlmod.unescape(raw))


def norm_url(u):
    u = (u or "").strip().lower().rstrip("/")
    return re.sub(r"^https?://(www\.)?", "", u)


def load_index():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from google_shelter_dedupe import build_index, is_dup

    return build_index(), is_dup


def load_a():
    if A_FILE.exists():
        return json.load(open(A_FILE, encoding="utf-8"))
    return []


def load_held():
    if B_FILE.exists():
        return json.load(open(B_FILE, encoding="utf-8")).get("held") or []
    return []


def save_a(items):
    A_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_held(held):
    B_FILE.write_text(
        json.dumps(
            {"held": held, "meta": {"about": "B-grade Google/Serper candidates with reasons"}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def fetch(url):
    FETCH.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    fp = FETCH / f"{h}.html"
    if fp.exists() and fp.stat().st_size > 400:
        return strip_html(fp.read_text(encoding="utf-8", errors="replace")), url
    try:
        r = subprocess.run(
            ["curl", "-fsSL", "-A", "helpmap-verify/1.0", "-L", "--max-time", "22", url],
            capture_output=True,
            timeout=28,
        )
        if r.returncode != 0:
            return None, url
        fp.write_bytes(r.stdout)
        return strip_html(r.stdout.decode("utf-8", errors="replace")), url
    except (subprocess.TimeoutExpired, OSError):
        return None, url


def town_tokens(town):
    t = re.sub(r"\([^)]+\)", "", town)
    parts = re.split(r"[\s\-/':]+", t.lower())
    return [p for p in parts if len(p) > 3]


def score_link(town, title, snippet, link):
    if BAD_LINK.search(link or ""):
        return -1
    tok = town_tokens(town)
    blob = f"{title} {snippet} {link}".lower()
    local = sum(1 for t in tok if t in blob)
    host = urlparse(link).netloc.lower()
    if host.endswith(".gov.uk") and local == 0:
        return -1
    sc = local * 2
    if SERVICE.search(blob):
        sc += 2
    if local == 0 and sc < 2:
        return 0
    return sc


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "place").lower()).strip("-")
    return s[:50] or "place"


def try_grade_a(town, url, title, text, index, is_dup):
    # Batch loop is B-only; A rows are added manually after curl review.
    if not __import__("os").environ.get("GOOGLE_VERIFY_ALLOW_A"):
        return None, "auto-A disabled (strict manual A only)"
    if EXCLUDE.search(text) or CLOSED.search(text):
        return None, "excluded or closed"
    if REJECT_TEXT.search(text) or REJECT_TEXT.search(title or ""):
        return None, "not an accommodation operator page"
    if not SERVICE.search(text):
        return None, "not shelter/day centre/nightstop page"
    ph = PHONE.search(text.replace("\u00a0", " "))
    pc = POSTCODE.search(text)
    if not ph or not pc:
        return None, "missing phone or postcode"
    postcode = pc.group(1).upper().replace("  ", " ")
    if FAKE_PC.match(postcode.replace(" ", "")):
        return None, "invalid postcode token"
    phone = ph.group(0).strip()
    dup = is_dup(url, title, index)
    if dup:
        return None, dup
    name = title.split("|")[0].strip()[:120] or "Homeless service"
    entry = {
        "id": f"man-google-{slug(name)}",
        "name": name,
        "address": "",
        "postcode": postcode,
        "lat": 0.0,
        "lng": 0.0,
        "phone": phone,
        "website": url.split("#")[0],
        "hours": "Not stated",
        "referral": "Not stated",
        "beds": "",
        "groups": [],
        "season": "Year-round",
        "operator": "",
        "flag_closed": False,
        "source": "Manual Google Serper Nov 2026",
        "source_url": url.split("#")[0],
        "last_verified": "2026-11-01",
        "stale": False,
        "access_type": "not_stated",
        "facilities": "Not stated",
        "checked_on": "2026-11-01",
        "kind": "hostel",
        "who_for": "Not stated",
        "wheelchair": "Not stated",
        "verified": True,
        "evidence_url": url.split("#")[0],
        "verified_on": "2026-11-01",
        "access": "Not stated",
        "evidence_name": urlparse(url).netloc.replace("www.", ""),
        "tier": "verified",
        "first_verified_on": "2026-11-01",
    }
    if re.search(r"nightstop|night stop", text, re.I):
        entry["kind"] = "young_people"
    elif re.search(r"day centre|day center", text, re.I):
        entry["kind"] = "day_centre"
    elif re.search(r"night shelter", text, re.I):
        entry["kind"] = "night_shelter"
    return entry, ""


def verify_town(town, organic_blocks, max_links=4):
    """Returns dict: a_added, b_added, a_entry, b_rows."""
    index, is_dup = load_index()
    held = load_held()
    a_items = load_a()
    existing_b = {(h["town"], h.get("url", "")) for h in held}
    a_ids = {x["id"] for x in a_items}

    candidates = []
    seen = set()
    for block in organic_blocks:
        for o in block.get("organic") or []:
            link = (o.get("link") or "").split("#")[0].strip()
            if not link or link in seen:
                continue
            seen.add(link)
            sc = score_link(town, o.get("title") or "", o.get("snippet") or "", link)
            if sc < 1:
                continue
            candidates.append((sc, link, o.get("title") or link))
    candidates.sort(key=lambda x: -x[0])

    b_rows = []
    a_entry = None

    for _sc, link, title in candidates[: max_links + 2]:
        if len(b_rows) >= max_links and a_entry:
            break
        text, url = fetch(link)
        if text is None:
            row = {
                "town": town,
                "url": url,
                "name": title[:100],
                "reason": "Fetch failed or blocked",
            }
            if (town, url) not in existing_b:
                b_rows.append(row)
            continue

        graded, why = try_grade_a(town, url, title, text, index, is_dup)
        if graded:
            if graded["id"] not in a_ids:
                a_entry = graded
                a_ids.add(graded["id"])
            break

        reasons = []
        if why:
            reasons.append(why)
        if not SERVICE.search(text):
            reasons.append("not a hostel/night shelter/day centre service page")
        if not PHONE.search(text.replace("\u00a0", " ")):
            reasons.append("no verbatim phone")
        if not POSTCODE.search(text):
            reasons.append("no postcode")
        reason = "; ".join(dict.fromkeys(reasons)) or "failed strict A check"
        row = {"town": town, "url": url, "name": title[:100], "reason": reason}
        if (town, url) not in existing_b:
            b_rows.append(row)

    if a_entry:
        a_items.append(a_entry)
        save_a(a_items)
    if b_rows:
        held.extend(b_rows)
        save_held(held)

    return {
        "town": town,
        "a_added": 1 if a_entry else 0,
        "b_added": len(b_rows),
        "a_entry": a_entry,
    }


if __name__ == "__main__":
    import sys

    town = sys.argv[1]
    state = json.loads((ROOT / "logs" / "google_serper_state.json").read_text())
    blocks = state["towns"].get(town)
    if not blocks:
        print("no state for town")
        raise SystemExit(1)
    print(json.dumps(verify_town(town, blocks), indent=2))
