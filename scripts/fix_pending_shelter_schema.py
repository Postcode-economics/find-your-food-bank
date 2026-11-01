#!/usr/bin/env python3
"""One-off data fixes for shelters stuck in logs/shelters_pending.json (schema / coords).

Does not weaken verification: only normalises wheelchair, referral wording, access_type,
and postcodes.io geocoding from a stated UK postcode on the manual row."""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAN = ROOT / "overrides" / "shelters_manual.json"
VER = ROOT / "overrides" / "shelters_verified.json"
REF_WORDS = ("referral", "refer", "application", "agencies")
VALID_ACCESS = {"open_access", "self_referral", "referral_only"}


def geocode_postcode(pc):
    pc = (pc or "").upper().strip()
    if not pc:
        return None
    url = "https://api.postcodes.io/postcodes/" + urllib.parse.quote(pc)
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=15).read().decode())["result"]
        return float(data["latitude"]), float(data["longitude"])
    except Exception:
        return None


def fix_referral_for_schema(referral, access_type):
    ref = (referral or "").strip()
    if access_type != "referral_only":
        return ref
    low = ref.lower()
    if any(w in low for w in REF_WORDS):
        return ref
    if ref:
        return "Referral: " + ref
    return "Referral route not stated on the page we checked"


def infer_access_type(referral, existing):
    if existing in VALID_ACCESS:
        return existing
    low = (referral or "").lower()
    if re.search(r"\b(self[- ]?referr|direct access|walk[- ]?in|drop[- ]?in)\b", low):
        return "self_referral"
    if re.search(r"\b(referr|housing options|council|agenc|application)\b", low):
        return "referral_only"
    if existing in (None, "", "not_stated"):
        return "open_access"
    return existing


def strip_bad_wheelchair(obj):
    if not isinstance(obj, dict):
        return False
    w = obj.get("wheelchair")
    if w in ("yes", "partial", "no"):
        return False
    if "wheelchair" in obj:
        obj.pop("wheelchair", None)
        obj.pop("wheelchair_quote", None)
        obj.pop("wheelchair_source", None)
        return True
    return False


def main():
    manual = json.load(open(MAN, encoding="utf-8"))
    ver = json.load(open(VER, encoding="utf-8"))
    stats = {"wheelchair_stripped_manual": 0, "wheelchair_stripped_ver": 0,
             "referral_fixed": 0, "access_type_fixed": 0, "geocoded": 0, "town_address": 0}

    for row in manual:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        if strip_bad_wheelchair(row):
            stats["wheelchair_stripped_manual"] += 1
        at = infer_access_type(row.get("referral"), row.get("access_type"))
        if at != row.get("access_type"):
            row["access_type"] = at
            stats["access_type_fixed"] += 1
        new_ref = fix_referral_for_schema(row.get("referral"), row.get("access_type"))
        if new_ref != (row.get("referral") or ""):
            row["referral"] = new_ref
            stats["referral_fixed"] += 1
        if row.get("card_type") == "referral_hostel" and row.get("no_pin"):
            if not (row.get("address") or "").strip() and (row.get("town") or row.get("area")):
                row["address"] = (row.get("town") or row.get("area")).strip()
                stats["town_address"] += 1
        lat, lng = row.get("lat"), row.get("lng")
        bad = not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or lat == 0.0 or lng == 0.0
        if bad and row.get("postcode"):
            g = geocode_postcode(row["postcode"])
            if g:
                row["lat"], row["lng"] = g
                stats["geocoded"] += 1
                vid = ver.get(row["id"])
                if isinstance(vid, dict):
                    vid["lat"], vid["lng"] = g

    for iid, v in list(ver.items()):
        if not isinstance(v, dict) or iid.startswith("_"):
            continue
        if strip_bad_wheelchair(v):
            stats["wheelchair_stripped_ver"] += 1
        if v.get("access_type") not in VALID_ACCESS and v.get("access_type"):
            v.pop("access_type", None)
        ref = v.get("referral") or v.get("access") or ""
        at = infer_access_type(ref, v.get("access_type"))
        if at in VALID_ACCESS and v.get("access_type") != at:
            v["access_type"] = at
        new_ref = fix_referral_for_schema(v.get("referral") or ref, v.get("access_type") or at)
        if new_ref and new_ref != v.get("referral"):
            v["referral"] = new_ref
        if v.get("access_type") == "referral_only":
            fixed = fix_referral_for_schema(v.get("access") or ref, "referral_only")
            if fixed and not v.get("referral"):
                v["referral"] = fixed
        if not v.get("lat") and v.get("postcode"):
            g = geocode_postcode(v["postcode"])
            if g:
                v["lat"], v["lng"] = g

    MAN.write_text(json.dumps(manual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    VER.write_text(json.dumps(ver, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
