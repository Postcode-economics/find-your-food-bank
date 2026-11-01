#!/usr/bin/env python3
"""Strict re-grade of google_a_items; demote failures to held_google.json."""
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import google_held_reverify as gr  # noqa: E402
import google_serper_verify_town as gv  # noqa: E402

BAD_HOST = re.compile(
    r"(independenthostels\.co\.uk|alzheimers\.org\.uk|ageuk\.org\.uk|thejoyapp\.com|"
    r"refernet\.|homeless\.org\.uk|indeed\.|carehome\.co\.uk|"
    r"crash\.org\.uk/our-work|/news/|christmas-food|other-agencies|"
    r"adultcare\.|how-to-find-suitable|sanctuary-supported-living\.co\.uk/support-se|"
    r"connecttosupportsurrey\.org\.uk|familysupportni\.gov\.uk/Service/|"
    r"lewishamfamilyhubs\.org\.uk|fleetphoenix\.co\.uk/useful-contacts|"
    r"lichfielddc\.gov\.uk/homelessness/concerned|yourspaceonline\.net|"
    r"dioceseofstasaph\.org\.uk/.*churches-to-open|thamesreach\.org\.uk/\d{4}/|"
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
TOURISM = re.compile(r"\b(hotels?,?\s*b&b|self catering|tourist information)\b", re.I)
HOMELESS_CTX = re.compile(
    r"\b(homeless|rough sleep|rough sleeper|vulnerably housed|street homeless|"
    r"no fixed abode|people sleeping rough)\b",
    re.I,
)


def validate_entry(e):
    url = e.get("source_url") or e.get("website") or ""
    if BAD_HOST.search(url) or NEWS_PATH.search(url):
        return "directory, news, or non-homeless service URL"
    raw, text = gr.fetch_raw(url)
    if not text:
        return "fetch failed"
    if gv.BAD_LINK.search(url):
        return "blocked URL pattern"
    if gv.EXCLUDE.search(text) or gv.CLOSED.search(text):
        return "excluded or closed"
    if TOURISM.search(text) and not HOMELESS_CTX.search(text):
        return "tourism/accommodation listing not homeless service"
    if gr.SUPPORTED_ONLY.search(text) and not gr.EMERGENCY.search(text):
        return "supported housing only"
    if not gr.EMERGENCY.search(text):
        return "not emergency/hostel/day centre service"
    if e.get("kind") == "day_centre" and not HOMELESS_CTX.search(text):
        return "day centre without homeless context"
    if e.get("kind") == "hostel" and not HOSTEL_WORD.search(text):
        return "hostel kind without hostel/night shelter wording on page"
    if e.get("kind") == "day_centre" and not DAY_CENTRE_WORD.search(text):
        return "day centre kind without day centre/drop-in wording on page"
    if e.get("kind") == "young_people" and not YOUTH_WORD.search(text):
        return "young people kind without foyer/nightstop/16-25 wording on page"
    if not gr.name_on_page(e.get("name") or "", text):
        return "name not on page"
    phs = gr.extract_phones(raw, text)
    want = gr.norm_phone(e.get("phone"))
    if not want or "%" in (e.get("phone") or ""):
        return "invalid phone field"
    if not any(gr.norm_phone(p) == want for p in phs):
        return "phone not verbatim on page"
    if e.get("postcode"):
        pc = e["postcode"].replace(" ", "").upper()
        if pc not in text.upper().replace(" ", ""):
            return "postcode not on page"
    elif not e.get("card_type"):
        return "missing postcode and not referral card"
    if e.get("card_type") == "referral_hostel":
        if not gr.REFERRAL.search(text):
            return "referral card without referral route on page"
    return ""


def main():
    a_path = ROOT / "logs" / "google_a_items.json"
    items = json.load(open(a_path, encoding="utf-8"))
    held = json.load(open(ROOT / "held_google.json", encoding="utf-8"))["held"]
    kept = []
    demoted = []
    for e in items:
        why = validate_entry(e)
        if why:
            demoted.append(
                {
                    "town": e.get("town") or "",
                    "url": e.get("source_url") or e.get("website"),
                    "name": e.get("name"),
                    "reason": f"strict re-grade: {why}",
                }
            )
        else:
            kept.append(e)
    held.extend(demoted)
    gv.save_held(held)
    gv.save_a(kept)
    from collections import Counter

    print(
        json.dumps(
            {
                "kept": len(kept),
                "demoted": len(demoted),
                "by_kind": Counter(x.get("kind") for x in kept),
                "demote_reasons": Counter(d["reason"] for d in demoted).most_common(15),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
