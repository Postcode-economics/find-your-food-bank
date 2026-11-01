"""man-google-* rows publish only when their id is on the hand-check list.

The list is overrides/man_google_handcheck.json. A shelters refresh must not
put any other man-google row on the map, including one that is already live
or sitting in shelters_manual.json.
"""
import json
import os

FILE = "overrides/man_google_handcheck.json"
REASON = "man-google row is not on the hand-check list"


def allowed(root="."):
    path = os.path.join(root, FILE)
    if not os.path.exists(path):
        return set()
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("ids") or []
    return {x for x in data if isinstance(x, str) and x.startswith("man-google-")}


def held_reason(item, allow=None, root="."):
    iid = str((item or {}).get("id") or "")
    if not iid.startswith("man-google-"):
        return None
    if allow is None:
        allow = allowed(root)
    if iid in allow:
        return None
    return REASON


def keep(items, root="."):
    allow = allowed(root)
    out, held = [], []
    for item in items or []:
        (held if held_reason(item, allow, root) else out).append(item)
    return out, held
