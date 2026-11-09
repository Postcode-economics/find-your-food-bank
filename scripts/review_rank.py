"""Short, ranked food bank review list (plan 1.6, 9 Nov 2026). Reporting only: nothing here applies or publishes.

The daily review had ~1,300 items a day, mostly the same unclear pages every day. This builds a short list of the
items that are NEW or CHANGED since the last saved day, ranked by how much they matter, each with a suggested action.
Unchanged items are only counted by cause. If no earlier day is saved (run memory missing), it says so and ranks
everything, capped, so nothing is hidden: the full list stays below it in daily_review.md.
"""

# Fields that move every run without anything real changing (run counters, the note that repeats them).
VOLATILE = ("first_flagged", "failed_runs", "note")
CAP = 50

# Higher = look first. Unknown categories sit in the middle so a new kind of problem is never buried.
WEIGHT = {
    "phone fix held (confidence under the rules)": 9,
    "access now uncertain": 8,
    "Trussell site with walk-in wording": 8,
    "access mixed": 7,
    "dead or unreachable website": 6,
    "seasonal/holiday hours notice": 5,
    "phone number not on own site": 5,
    "opening times not read": 4,
    "opening times unclear": 3,
    "items-needed list published": 2,
    "not fetched, robots": 1,
}
DEFAULT_WEIGHT = 5

ACTION = {
    "phone fix held (confidence under the rules)": "check the number on the food bank's own page, then approve or undo",
    "access now uncertain": "read the access wording on the own site and pick voucher or walk-in",
    "Trussell site with walk-in wording": "check whether this centre really takes walk-ins",
    "access mixed": "decide voucher or walk-in from the own site",
    "dead or unreachable website": "check the site or phone; it may have moved or closed",
    "seasonal/holiday hours notice": "check the holiday times on the own site",
    "phone number not on own site": "confirm the phone on another official page",
    "opening times not read": "open the page and read the times",
    "opening times unclear": "read the times on the own page",
    "items-needed list published": "no data fault; optional",
    "not fetched, robots": "no data fault (site blocks robots, often Facebook); check by hand only if stale",
}


def _core(v):
    return {k: v[k] for k in v if k not in VOLATILE}


def previous_day(review, day):
    """Latest saved day before `day`, or None."""
    earlier = sorted(k for k in (review or {}) if k < day and isinstance(review[k], dict))
    return earlier[-1] if earlier else None


def short_list(today_items, prev_items, cap=CAP):
    """-> dict(rows=[...], new=n, changed=n, unchanged={category: n}, has_prev=bool, total=n).
    rows: ranked new/changed items (or everything when there is no earlier day), at most `cap`."""
    has_prev = prev_items is not None
    prev_items = prev_items or {}
    rows, unchanged, new, changed = [], {}, 0, 0
    for key, v in (today_items or {}).items():
        cat = v.get("category") or "other"
        if has_prev and key in prev_items and _core(prev_items[key]) == _core(v):
            unchanged[cat] = unchanged.get(cat, 0) + 1
            continue
        status = "changed" if key in prev_items else "new"
        if has_prev:
            if status == "new": new += 1
            else: changed += 1
        rows.append(dict(v, status=status if has_prev else "listed", action=ACTION.get(cat, "check the own site"),
                         weight=WEIGHT.get(cat, DEFAULT_WEIGHT)))
    rows.sort(key=lambda r: (-r["weight"], r.get("category") or "", (r.get("name") or "").lower()))
    return {"rows": rows[:cap], "more": max(0, len(rows) - cap), "new": new, "changed": changed,
            "unchanged": unchanged, "has_prev": has_prev, "total": len(today_items or {})}


def md_lines(s, auto_applied_count):
    L = ["", "## Today's short list (%d)" % len(s["rows"]), ""]
    if s["has_prev"]:
        L.append("New or changed since the last saved day: %d new, %d changed. Unchanged items are counted below, not re-listed." % (s["new"], s["changed"]))
    else:
        L.append("No earlier day saved (run memory missing), so this cannot tell new from old: everything is ranked, top %d shown." % CAP)
    L.append("Auto-applied this run: %d, every one listed in full under 'Auto-applied this run'." % auto_applied_count)
    L.append("")
    for r in s["rows"]:
        L.append("- [%s] **%s** %s (%s) - %s" % (r["status"], r.get("name") or r.get("id") or "", r.get("website") or "", r.get("category"), r["action"]))
    if not s["rows"]:
        L.append("- nothing new or changed")
    if s["more"]:
        L.append("- ... and %d more in the full list below" % s["more"])
    if s["unchanged"]:
        L += ["", "Unchanged since the last saved day (counted, not re-listed): " +
              ", ".join("%s %d" % (c, n) for c, n in sorted(s["unchanged"].items(), key=lambda x: -x[1]))]
    return L
