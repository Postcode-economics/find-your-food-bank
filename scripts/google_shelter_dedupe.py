#!/usr/bin/env python3
"""Build dedupe index from live shelters.js + shelters_manual.json."""
import json
import os
import re
import subprocess
import urllib.parse


def norm_url(u):
    u = (u or "").strip().lower().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u


def load_live():
    try:
        out = subprocess.check_output(
            ["curl", "-fsSL", "-A", "helpmap-build/1.0", "https://helpmap.uk/shelters.js"],
            timeout=120,
        )
    except subprocess.CalledProcessError:
        return []
    t = out.decode("utf-8", "replace")
    m = re.search(r"var SHELTERS=(\{.*\});", t, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    return data.get("items") or []


def load_manual():
    p = "overrides/shelters_manual.json"
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding="utf-8"))


def build_index():
    ids = set()
    urls = set()
    names = set()
    for src in load_live() + load_manual():
        ids.add(src.get("id", ""))
        urls.add(norm_url(src.get("website")))
        urls.add(norm_url(src.get("source_url")))
        n = re.sub(r"[^a-z0-9]+", " ", (src.get("name") or "").lower()).strip()
        if n:
            names.add(n)
    return {"ids": ids, "urls": urls, "names": names}


def is_dup(candidate_url, candidate_name, index):
    if norm_url(candidate_url) in index["urls"]:
        return "duplicate URL"
    n = re.sub(r"[^a-z0-9]+", " ", (candidate_name or "").lower()).strip()
    if n and n in index["names"]:
        return "duplicate name"
    return ""


if __name__ == "__main__":
    idx = build_index()
    print(json.dumps({"live_plus_manual": len(idx["ids"]), "urls": len(idx["urls"])}))
