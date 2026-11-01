#!/usr/bin/env python3
"""Append graded A/B items during Google pass (does not commit secrets)."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A_FILE = ROOT / "logs" / "google_a_items.json"
B_FILE = ROOT / "held_google.json"

CLOSED = re.compile(
    r"\b(closed permanently|has closed|no longer open|we are closed|service closed|"
    r"closed until|not currently accepting)\b",
    re.I,
)
EXCLUDE = re.compile(
    r"\b(women'?s refuge|refuge for women|approved premises|probation hostel|"
    r"bail hostel|supported housing for adults|move on accommodation only)\b",
    re.I,
)
PHONE = re.compile(r"(?<!\d)(?:0\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}|0800[\s\-]?\d{3}[\s\-]?\d{4})(?!\d)")
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b", re.I)


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "place"


def load_a():
    if A_FILE.exists():
        return json.load(open(A_FILE, encoding="utf-8"))
    return []


def load_b():
    if B_FILE.exists():
        data = json.load(open(B_FILE, encoding="utf-8"))
        return data.get("held") or []
    return []


def save_a(items):
    A_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_b(held):
    B_FILE.write_text(
        json.dumps({"held": held, "meta": {"about": "B-grade Google/Serper candidates with reasons"}}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def add_b(entry):
    held = load_b()
    held.append(entry)
    save_b(held)


def add_a(entry):
    items = load_a()
    ids = {x["id"] for x in items}
    if entry["id"] in ids:
        return False
    items.append(entry)
    save_a(items)
    return True


def quick_reject(text, name):
    if EXCLUDE.search(text) or EXCLUDE.search(name or ""):
        return "excluded type (refuge/probation/supported housing)"
    if CLOSED.search(text):
        return "page says closed / not open"
    return ""


def find_phone(text):
    m = PHONE.search(text.replace("\u00a0", " "))
    return m.group(0).strip() if m else ""


def find_postcode(text):
    m = POSTCODE.search(text)
    return m.group(1).upper().replace("  ", " ") if m else ""
