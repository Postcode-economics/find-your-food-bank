"""Map council names (sweep_sources / scanner) to ONS LAD codes (same as postcodes.io codes.admin_district)."""
import json, os, re

ROOT = os.path.join(os.path.dirname(__file__), "..")
_AREAS = None


def _load():
    global _AREAS
    if _AREAS is None:
        p = os.path.join(ROOT, "counties.json")
        _AREAS = json.load(open(p, encoding="utf-8")).get("areas") or []
    return _AREAS


def _norm(s):
    s = re.sub(r"\b(city of|county|borough|district|metropolitan|london borough of|royal borough of|and|the)\b", " ", (s or "").lower())
    return re.sub(r"[^a-z ]", " ", s).strip()


def _words(s):
    return [w for w in _norm(s).split() if w]


def lad_for_council(name):
    """Return GSS admin_district code for a council name, or None if ambiguous / unknown."""
    if not name:
        return None
    n = _norm(name)
    for a in _load():
        if _norm(a.get("name")) == n:
            return a["code"]
    w = _words(name)
    if len(w) < 2:
        return None
    hits = []
    for a in _load():
        aw = _words(a.get("name"))
        if len(aw) >= 2 and w[0] == aw[0] and w[-1] == aw[-1]:
            hits.append(a["code"])
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None
