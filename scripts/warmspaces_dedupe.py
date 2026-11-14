"""Warm space duplicates (14 Nov 2026).

Two parts:

1. apply_reviewed(): hand-reviewed merges. A row in overrides/warmspaces_exclude.json with "duplicate_of" names the
   card that is kept. Before the duplicate is left off, any field the kept card is missing is filled from the
   duplicate (website, Source link, notes, hours, wheelchair), and facility labels are combined. Phones, council
   lines, names, addresses and pins are never copied. A kept card from overrides/warmspaces_manual.json is never
   changed. If the kept card is not on the list this run, the duplicate is NOT left off, so a real place is never
   lost because its twin dropped out.

2. find(): record-only duplicate check (rule 104, shadow first). It lists likely duplicates on the built list so they
   can be reviewed; it never removes or changes a card.
"""
import difflib
import math
import re

NEVER_COPY = {"id", "name", "address", "postcode", "lat", "lng", "phone", "tel", "phone_label", "phone_source",
              "council_phone", "council_ooh", "council_label", "no_pin"}
FILL_IF_EMPTY = ("website", "evidence_url", "evidence_name", "source_label", "notes", "hours",
                 "wheelchair", "wheelchair_quote", "wheelchair_source")
STOP = set("the a an of and at in on saint church centre center hall community warm space spaces hub room rooms "
           "welcome cafe library parish club house trust project".split())


def _own_site(url):
    u = (url or "").strip().lower()
    return bool(u) and "warmwelcome.uk" not in u


def _blank(v):
    return v in (None, "", [], {}) or (isinstance(v, str) and v.strip().lower() == "not stated")


def reviewed_rows(rows):
    """Exclude-list rows that are reviewed duplicates: {loser_id: winner_id}."""
    out = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get("id") and r.get("duplicate_of") and r["id"] != r["duplicate_of"]:
            out[r["id"]] = r["duplicate_of"]
    return out


def apply_reviewed(items, rows, hand_ids=()):
    """Fill kept cards from their reviewed duplicates. Returns (ids to leave off this run, log)."""
    pairs = reviewed_rows(rows)
    by_id = {x.get("id"): x for x in items}
    hand_ids = set(hand_ids or ())
    drop, log = set(), []
    for loser_id, winner_id in sorted(pairs.items()):
        winner, loser = by_id.get(winner_id), by_id.get(loser_id)
        if winner is None:
            log.append({"id": loser_id, "duplicate_of": winner_id, "result": "kept: the card it duplicates is not on the list this run"})
            continue
        drop.add(loser_id)
        if loser is None:
            log.append({"id": loser_id, "duplicate_of": winner_id, "result": "not on the list this run"})
            continue
        if winner_id in hand_ids:
            log.append({"id": loser_id, "duplicate_of": winner_id, "result": "merged; kept card is hand-made, left unchanged"})
            continue
        filled = []
        for k in FILL_IF_EMPTY:
            if k in NEVER_COPY:
                continue
            if k == "website":
                if not _own_site(winner.get(k)) and _own_site(loser.get(k)):
                    winner[k] = loser[k]; filled.append(k)
                continue
            if _blank(winner.get(k)) and not _blank(loser.get(k)):
                winner[k] = loser[k]; filled.append(k)
        prov = list(winner.get("provided") or [])
        extra = [p for p in (loser.get("provided") or []) if p not in prov]
        if extra:
            winner["provided"] = prov + extra; filled.append("provided")
        log.append({"id": loser_id, "duplicate_of": winner_id, "result": "merged", "filled": filled})
    return drop, log


# ---------- record-only check ----------
def _norm(n):
    n = (n or "").lower().replace("&", " and ").replace("\u2019", "'")
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\bst\b", "saint", n)
    return re.sub(r"\s+", " ", n).strip()


def _tokens(n):
    return set(_norm(n).split()) - STOP


def _pc(x):
    return re.sub(r"\s", "", (x.get("postcode") or "")).upper()


def _phone(x):
    return re.sub(r"\D", "", x.get("phone") or "")


def _metres(a, b):
    try:
        return 6371000 * math.hypot(math.radians(b["lng"] - a["lng"]) * math.cos(math.radians(a["lat"])),
                                    math.radians(b["lat"] - a["lat"]))
    except Exception:
        return None


def _space_page(x):
    m = re.search(r"warmwelcome\.uk/space\?l=(\d+)", x.get("source_url") or "")
    return m.group(1) if m else ""


def _name_match(a, b):
    na, nb = _norm(a.get("name")), _norm(b.get("name"))
    if na and na == nb:
        return True
    if na and nb and difflib.SequenceMatcher(None, na, nb).ratio() >= 0.9:  # a misspelt copy, e.g. Willowbrun
        return True
    if na and nb and min(len(na), len(nb)) >= 8 and (na in nb or nb in na):  # 'The Dolphin' / 'The Dolphin Leisure Centre'
        return True
    ta, tb = _tokens(a.get("name")), _tokens(b.get("name"))
    shared = ta & tb
    # two or more distinctive words in common; one shared word (often just the town) is not enough
    return len(shared) >= 2 and len(shared) / min(len(ta), len(tb)) >= 0.8


def _addr(x):
    return re.sub(r"[^a-z0-9]", "", (x.get("address") or "").lower())


def _same_sessions(a, b):
    """Every shared day has the same times, and one card's days are all on the other card."""
    ha, hb = a.get("hours") or {}, b.get("hours") or {}
    if not ha or not hb:
        return False
    shared = set(ha) & set(hb)
    if not shared or any(ha[d] != hb[d] for d in shared):
        return False
    return set(ha) <= set(hb) or set(hb) <= set(ha)


def _shared_day(a, b):
    return bool(set(a.get("hours") or {}) & set(b.get("hours") or {}))


def find(items, reviewed=()):
    """Likely duplicates on the built list. Record only.
    certain: the same Warm Welcome space page under two ids; or the same (or misspelt) name within 300 m or in the
             same postcode, with the same phone and the same sessions.
    possible: the same name nearby with a different phone or different sessions; the same phone and postcode with a
              shared day; or the same street address at the same pin under a different name (two groups in one
              building, or one card carrying another venue's address)."""
    reviewed = set(reviewed or ())
    live = [x for x in items if x.get("id") not in reviewed]
    out, seen = [], set()
    by_page, by_pc = {}, {}
    for x in live:
        p = _space_page(x)
        if p:
            by_page.setdefault(p, []).append(x)
        if _pc(x):
            by_pc.setdefault(_pc(x), []).append(x)

    def add(a, b, kind, why):
        k = tuple(sorted((a["id"], b["id"])))
        if k in seen:
            return
        seen.add(k)
        d = _metres(a, b)
        out.append({"a": k[0], "b": k[1], "kind": kind, "why": why, "metres": None if d is None else round(d)})

    for v in by_page.values():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                add(v[i], v[j], "certain", "same Warm Welcome space page")
    grid = {}
    for x in live:
        if isinstance(x.get("lat"), (int, float)) and isinstance(x.get("lng"), (int, float)):
            grid.setdefault((round(x["lat"] * 100), round(x["lng"] * 100)), []).append(x)
    for (gx, gy), cell in grid.items():
        near = [y for dx in (-1, 0, 1) for dy in (-1, 0, 1) for y in grid.get((gx + dx, gy + dy), [])]
        for a in cell:
            for b in near:
                if a["id"] >= b["id"] or not _name_match(a, b):
                    continue
                d = _metres(a, b)
                if d is None or d > 300:
                    continue
                if _phone(a) and _phone(a) == _phone(b) and _same_sessions(a, b):
                    add(a, b, "certain", "same name within 300 m, same phone and sessions")
                elif _phone(a) and _phone(a) == _phone(b) or _shared_day(a, b):
                    add(a, b, "possible", "same name within 300 m")
    for v in by_pc.values():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                a, b = v[i], v[j]
                same_phone = bool(_phone(a)) and _phone(a) == _phone(b)
                if _name_match(a, b) and same_phone and _same_sessions(a, b):
                    add(a, b, "certain", "same name, postcode, phone and sessions")
                elif _name_match(a, b) and (same_phone or _shared_day(a, b)):
                    add(a, b, "possible", "same name and postcode")
                elif same_phone and _shared_day(a, b):
                    add(a, b, "possible", "same phone and postcode, shared day")
                elif _addr(a) and _addr(a) == _addr(b) and (_metres(a, b) or 0) <= 5:
                    add(a, b, "possible", "same address and pin, different name")
    return out
