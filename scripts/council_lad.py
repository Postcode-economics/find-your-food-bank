"""Map council names (sweep_sources / scanner) to ONS LAD codes (same as postcodes.io codes.admin_district).

12 Nov 2026: council names such as "Arun District Council" or "Birmingham City Council" never matched before,
because only counties.json (ONS counties and unitary authorities) was searched and the word "council" was kept.
A district's rest centre then had no area code and the live note and card reached nobody. Names are now matched
first against scripts/lad_codes.json (every ONS local authority district, the same code a visitor gets from
postcodes.io admin_district), then against counties.json. Only exact matches of the normalised name, or one
unique first/last-word match, are returned; anything ambiguous or unknown gives None (shown to nobody).
"""
import json, os, re

ROOT = os.path.join(os.path.dirname(__file__), "..")
_AREAS = None
_LADS = None

# Council names whose short form differs from the ONS LAD name. Values are ONS LAD25NM names (scripts/lad_codes.json).
ALIASES = {
    "hull": "Kingston upon Hull, City of",
    "newcastle": "Newcastle upon Tyne",
    "comhairle nan eilean siar": "Na h-Eileanan Siar",
}


def _load():
    global _AREAS
    if _AREAS is None:
        p = os.path.join(ROOT, "counties.json")
        _AREAS = json.load(open(p, encoding="utf-8")).get("areas") or []
    return _AREAS


def _load_lads():
    global _LADS
    if _LADS is None:
        p = os.path.join(os.path.dirname(__file__), "lad_codes.json")
        _LADS = json.load(open(p, encoding="utf-8")).get("areas") or []
    return _LADS


_DROP = r"\b(council|corporation|city of|county of|county|borough|district|metropolitan|london borough of|royal borough of|city|and|the|of)\b"


def _norm(s):
    s = (s or "").lower().replace("&", " and ").replace("'", "").replace("\u2019", "")
    s = re.sub(r"[^a-z ]", " ", s)
    s = re.sub(_DROP, " ", s)
    return " ".join(s.split())


def _words(s):
    return [w for w in _norm(s).split() if w]


def _names(a):
    return [n for n in (a.get("name"), a.get("name_cy")) if n]


def lad_for_council(name):
    """Return GSS admin_district code for a council name, or None if ambiguous / unknown."""
    if not name:
        return None
    n = _norm(name)
    if not n:
        return None
    alias = ALIASES.get(n)
    if alias:
        n = _norm(alias)
    for group in (_load_lads(), _load()):
        hits = [a["code"] for a in group if any(_norm(x) == n for x in _names(a))]
        hits = list(dict.fromkeys(hits))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    w = n.split()
    if len(w) < 2:
        return None
    hits = []
    for a in _load_lads() + _load():
        aw = _words(a.get("name"))
        if len(aw) >= 2 and w[0] == aw[0] and w[-1] == aw[-1]:
            hits.append(a["code"])
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None
