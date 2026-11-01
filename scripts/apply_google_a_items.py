#!/usr/bin/env python3
"""Merge logs/google_a_items.json into overrides for PR (manual, verified, approved, phone)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A_FILE = ROOT / "logs" / "google_a_items.json"
MAN = ROOT / "overrides" / "shelters_manual.json"
VER = ROOT / "overrides" / "shelters_verified.json"
AP = ROOT / "overrides" / "approved_new_places.json"
PH = ROOT / "overrides" / "phone_baseline.json"

NOTE = "Dean blanket approval for verified items; Google Serper Nov 2026 own-page verification."


def norm_url(u):
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower().rstrip("/"))


def main():
    items = json.load(open(A_FILE, encoding="utf-8"))
    manual = json.load(open(MAN, encoding="utf-8"))
    by_id = {x["id"]: x for x in manual}
    urls = {norm_url(x.get("website")) for x in manual} | {norm_url(x.get("source_url")) for x in manual}

    ver = json.load(open(VER, encoding="utf-8"))
    ap = json.load(open(AP, encoding="utf-8"))
    ph = json.load(open(PH, encoding="utf-8"))
    sh_ap = ap.setdefault("shelters", {})

    added = 0
    for e in items:
        u = norm_url(e.get("website") or e.get("source_url"))
        if e["id"] in by_id or u in urls:
            continue
        row = {k: v for k, v in e.items() if not k.startswith("_")}
        if row.get("lat") == 0.0 and row.get("lng") == 0.0 and row.get("card_type"):
            row["lat"] = None
            row["lng"] = None
        manual.append(row)
        by_id[row["id"]] = row
        urls.add(u)
        quote = e.get("_quote") or row.get("name", "")
        ver[row["id"]] = {
            "name": row["name"],
            "access": row.get("referral") or "Not stated",
            "evidence_url": row.get("source_url") or row.get("website"),
            "quote": quote[:240],
            "phone": row.get("phone") or "",
            "address": row.get("address") or "",
            "postcode": row.get("postcode") or "",
            "verified_on": "2026-11-01",
            "evidence_name": e.get("_evidence_name") or "",
            "note": NOTE,
            "facilities": row.get("facilities") or "Not stated",
            "who_for": row.get("who_for") or "Not stated",
            "groups": row.get("groups") or [],
            "season": row.get("season") or "Year-round",
            "hours": row.get("hours") or "Not stated",
            "referral": row.get("referral") or "Not stated",
        }
        at = row.get("access_type")
        if at in ("open_access", "self_referral", "referral_only"):
            ver[row["id"]]["access_type"] = at
        sh_ap[row["id"]] = NOTE
        if row.get("phone"):
            ph.setdefault(row["id"], {"layer": "shelters", "phone": row["phone"]})
        added += 1

    MAN.write_text(json.dumps(manual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    VER.write_text(json.dumps(ver, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    AP.write_text(json.dumps(ap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PH.write_text(json.dumps(ph, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"added_to_manual": added, "manual_total": len(manual)}))


if __name__ == "__main__":
    main()
