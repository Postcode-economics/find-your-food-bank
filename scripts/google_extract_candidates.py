#!/usr/bin/env python3
"""Extract operator-page candidates from Serper raw log for hand/auto grading."""
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "logs" / "google_serper_raw.jsonl"
OUT = ROOT / "logs" / "google_candidates.json"

GENERIC_HOSTS = {
    "shelter.org.uk", "england.shelter.org.uk", "scotland.shelter.org.uk",
    "sheltercymru.org.uk", "homeless.org.uk", "homelesslink.org.uk",
    "salvationarmy.org.uk", "gov.uk", "wikipedia.org", "bbc.co.uk",
    "citizensadvice.org.uk", "nhs.uk", "police.uk",
}

LIST_PATH = re.compile(
    r"/(local-hostels|night-shelters|emergency-accommodation|homelessness-advice|"
    r"worried-about-becoming-homeless|directory_record|news/|press-release)",
    re.I,
)


def host(u):
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def town_tokens(town):
    t = re.sub(r"\([^)]+\)", "", town)
    parts = re.split(r"[\s\-/]+", t.lower())
    return [p for p in parts if len(p) > 2]


def score_row(town, title, snippet, link):
    tok = town_tokens(town)
    blob = f"{title} {snippet} {link}".lower()
    local = sum(1 for t in tok if t in blob)
    h = host(link)
    if h in GENERIC_HOSTS:
        return -5, "generic host"
    if LIST_PATH.search(link or ""):
        return -3, "list/news path"
    if h.endswith(".gov.uk") and local == 0:
        return -2, "non-local council"
    if local >= 1:
        return 3 + local, "local mention"
    if any(w in blob for w in ("hostel", "night shelter", "day centre", "foyer", "rough sleep")):
        return 1, "service keyword"
    return 0, "other"


def main():
    by_url = {}
    by_town = defaultdict(list)
    if not RAW.exists():
        print("no raw log")
        return
    for line in RAW.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        town = row["town"]
        for o in row.get("organic") or []:
            link = o.get("link") or ""
            if not link:
                continue
            sc, reason = score_row(town, o.get("title") or "", o.get("snippet") or "", link)
            if sc < 0:
                continue
            key = link.split("#")[0].rstrip("/")
            prev = by_url.get(key)
            if not prev or sc > prev["score"]:
                by_url[key] = {
                    "url": key,
                    "title": o.get("title"),
                    "snippet": o.get("snippet"),
                    "town": town,
                    "query": row.get("query"),
                    "score": sc,
                    "reason": reason,
                }
            by_town[town].append(key)
    candidates = sorted(by_url.values(), key=lambda x: (-x["score"], x["town"]))
    OUT.write_text(json.dumps({"candidates": candidates, "by_town_count": {k: len(set(v)) for k, v in by_town.items()}}, indent=2), encoding="utf-8")
    print("candidates", len(candidates))


if __name__ == "__main__":
    main()
